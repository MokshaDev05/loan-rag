"""Shared pytest fixtures and helpers for all test suites."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, Base, engine
from app.main import app
from app.services.embedder import Embedder

# ─────────────────────────────────────────
# Constants
# ─────────────────────────────────────────

_DIMS = 384  # must match Vector(384) in models.py


# ─────────────────────────────────────────
# Minimal PDF builder
# ─────────────────────────────────────────

def make_pdf(*page_texts: str) -> bytes:
    """Build a valid PDF in memory from one or more page text strings.

    Uses only standard Type1 fonts so no font data needs to be embedded.
    The resulting bytes pass pdfplumber's parser and yield extractable text.
    """
    if not page_texts:
        page_texts = ("Test loan document.",)

    parts: list[bytes] = [b"%PDF-1.4\n"]
    offsets: list[int] = []
    obj = 1

    # Font object
    font_obj = obj
    offsets.append(len(b"".join(parts)))
    parts.append(f"{obj} 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n".encode())
    obj += 1

    # Content stream per page
    content_objs: list[int] = []
    for text_str in page_texts:
        safe = text_str.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 11 Tf 50 750 Td ({safe}) Tj ET".encode()
        content_objs.append(obj)
        offsets.append(len(b"".join(parts)))
        parts.append(f"{obj} 0 obj<</Length {len(stream)}>>\nstream\n".encode())
        parts.append(stream)
        parts.append(b"\nendstream\nendobj\n")
        obj += 1

    # Page objects — parent object number is known ahead of time
    pages_parent_num = obj + len(page_texts)
    page_objs: list[int] = []
    for co in content_objs:
        page_objs.append(obj)
        offsets.append(len(b"".join(parts)))
        parts.append((
            f"{obj} 0 obj<</Type/Page/MediaBox[0 0 612 792]"
            f"/Parent {pages_parent_num} 0 R"
            f"/Contents {co} 0 R"
            f"/Resources<</Font<</F1 {font_obj} 0 R>>>>>>"
            f">>endobj\n"
        ).encode())
        obj += 1

    # Pages (parent) object
    kids = " ".join(f"{o} 0 R" for o in page_objs)
    offsets.append(len(b"".join(parts)))
    parts.append(
        f"{obj} 0 obj<</Type/Pages/Kids[{kids}]/Count {len(page_texts)}>>endobj\n".encode()
    )
    obj += 1

    # Catalog
    catalog_num = obj
    offsets.append(len(b"".join(parts)))
    parts.append(f"{obj} 0 obj<</Type/Catalog/Pages {obj - 1} 0 R>>endobj\n".encode())
    obj += 1

    # Cross-reference table + trailer
    xref_offset = len(b"".join(parts))
    xref = f"xref\n0 {obj}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n"
    parts.append(xref.encode())
    parts.append(
        f"trailer<</Size {obj}/Root {catalog_num} 0 R>>\nstartxref\n{xref_offset}\n%%EOF".encode()
    )
    return b"".join(parts)


# ─────────────────────────────────────────
# Fake embedder
# ─────────────────────────────────────────

def _unit_vector(seed: int) -> list[float]:
    """Return a deterministic unit vector so cosine distances are meaningful."""
    v = [math.sin(i * 0.1 + seed) for i in range(_DIMS)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


class FakeEmbedder(Embedder):
    """Drop-in Embedder replacement: no model loading, deterministic outputs."""

    def __init__(self) -> None:
        super().__init__("fake-model")
        self._model = True  # mark as initialised so embed_batch takes the real path

    async def initialize(self) -> None:
        pass

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Different seed per position so stored chunks are distinguishable
        return [_unit_vector(i) for i in range(len(texts))]

    async def embed_text(self, text: str) -> list[float]:
        # Query vector matches the vector for position 0 exactly
        return _unit_vector(0)

    async def close(self) -> None:
        pass


# ─────────────────────────────────────────
# Session-level SentenceTransformer patch
# ─────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def _patch_sentence_transformer():
    """Prevent any test from downloading or loading the real 90 MB model."""
    import numpy as np  # numpy is a transitive dep of sentence-transformers

    with patch("sentence_transformers.SentenceTransformer") as mock_cls:
        mock_model = MagicMock()
        # encode() must return a numpy array because the embedder calls .tolist() on it
        mock_model.encode.side_effect = (
            lambda texts, **kw: np.full((len(texts), _DIMS), 0.1)
        )
        mock_cls.return_value = mock_model
        yield


# ─────────────────────────────────────────
# Database fixtures (skip when DB is down)
# ─────────────────────────────────────────

@pytest_asyncio.fixture
async def _db_ready():
    """Skip the current test if PostgreSQL is not reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not available — start with: docker compose up -d db")


@pytest_asyncio.fixture
async def db_session(_db_ready):
    """Yield a live AsyncSession.  Tables are created once; truncated per test."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await session.execute(text(
            "TRUNCATE citations, messages, conversations, "
            "document_fields, chunks, documents RESTART IDENTITY CASCADE"
        ))
        await session.commit()
        yield session


# ─────────────────────────────────────────
# HTTP client fixture (API tests)
# ─────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_session):
    """AsyncClient wired to the FastAPI ASGI app.

    The lifespan does NOT run (ASGITransport does not send lifespan events),
    so we set app.state manually here instead.
    """
    app.state.embedder = FakeEmbedder()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as http_client:
        yield http_client
