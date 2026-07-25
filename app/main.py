import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text as sa_text
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models  # noqa: F401 — registers all ORM models with Base before create_all
from app.api.v1.router import router as api_v1_router
from app.config import settings
from app.core.database import Base, engine
from app.docs import get_docs_html
from app.services.embedder import Embedder


class _JsonFormatter(logging.Formatter):
    _SKIP = frozenset({
        "args", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "message", "module", "msecs", "msg",
        "name", "pathname", "process", "processName", "relativeCreated",
        "stack_info", "thread", "threadName",
    })

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.message,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update({k: v for k, v in record.__dict__.items() if k not in self._SKIP})
        return json.dumps(payload, default=str)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())
    for noisy in ("httpx", "httpcore", "sentence_transformers", "transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("startup", extra={"model": settings.EMBEDDING_MODEL})

    async with engine.begin() as conn:
        await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_ready")

    app.state.embedder = Embedder(settings.EMBEDDING_MODEL)
    await app.state.embedder.initialize()
    logger.info("embedding_model_ready", extra={"model": settings.EMBEDDING_MODEL})

    yield

    logger.info("shutdown")
    await app.state.embedder.close()
    await engine.dispose()


_DESCRIPTION = """\
**Loan Document Review RAG** is an AI-powered document analysis platform that
helps loan officers, underwriters, and risk analysts extract insights from
complex loan packages in seconds.

## Capabilities

- **Document ingestion** — Upload PDFs; text is extracted, chunked, and indexed automatically.
- **Semantic search** — Retrieve the most relevant passages from any uploaded document.
- **AI-generated answers** — Ask natural-language questions; receive cited, grounded responses.
- **Audit trail** — Every answer records which chunks and pages it was derived from.

## Authentication

All write endpoints require a bearer token.  Pass it in the `Authorization` header:

```
Authorization: Bearer <token>
```

## Rate limits

| Tier | Requests / minute |
|------|------------------|
| Free | 20 |
| Pro  | 200 |
"""

_TAGS_METADATA = [
    {
        "name": "system",
        "description": "Health and readiness probes.",
    },
    {
        "name": "documents",
        "description": "Upload and manage loan PDF documents.",
    },
    {
        "name": "conversations",
        "description": "Create and retrieve Q&A conversations tied to a document.",
    },
    {
        "name": "messages",
        "description": "Ask questions and receive AI-generated, cited answers.",
    },
]


app = FastAPI(
    title="Loan Document Review",
    description=_DESCRIPTION,
    version="0.1.0",
    openapi_tags=_TAGS_METADATA,
    contact={
        "name": "Platform Engineering",
        "email": "api@loandocreview.internal",
    },
    license_info={
        "name": "Proprietary",
    },
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_context(request: Request, call_next: Any) -> Any:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "http_request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": elapsed_ms,
            "request_id": request_id,
        },
    )
    return response


def _error_body(message: str, detail: Any, request: Request) -> dict[str, Any]:
    return {
        "success":    False,
        "error":      message,
        "detail":     detail,
        "request_id": getattr(request.state, "request_id", None),
    }


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning(
        "validation_error",
        extra={
            "path": request.url.path,
            "errors": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body("Validation error", exc.errors(), request),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    logger.warning(
        "http_error",
        extra={
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.detail, None, request),
    )


@app.exception_handler(Exception)
async def handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        exc_info=True,
        extra={
            "exc_type": type(exc).__name__,
            "path": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("Internal server error", None, request),
    )


@app.get("/docs", include_in_schema=False)
async def custom_docs() -> HTMLResponse:
    return get_docs_html(
        openapi_url="/openapi.json",
        title="Loan Document Review",
        version="0.1.0",
        environment=settings.ENVIRONMENT,
    )


app.include_router(api_v1_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_config=None,   # suppress uvicorn's default config; use ours
        access_log=False,  # our middleware already logs every request
    )
