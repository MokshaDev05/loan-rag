import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Chunk, DocStatus, Document
from app.services.chunker import chunk_document
from app.services.embedder import Embedder
from app.services.pdf_processor import PDFProcessingError, extract

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_PREVIEW_CHARS = 500
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


def get_embedder(request: Request) -> Embedder:
    return request.app.state.embedder


class UploadResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    page_count: int
    char_count: int
    chunk_count: int
    text_preview: str


class SearchRequest(BaseModel):
    query: str
    document_id: Optional[uuid.UUID] = None
    top_k: int = Field(default=5, ge=1, le=20)


class ChunkResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    page_number: Optional[int]
    content: str
    similarity_score: Optional[float]


class SearchResponse(BaseModel):
    results: List[ChunkResult]


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF and extract its text",
)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
) -> UploadResponse:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are accepted.",
        )

    # Read at most _MAX_BYTES + 1 bytes so we never load more than ~20 MB into
    # memory, regardless of how large the upload actually is.  If the result is
    # longer than _MAX_BYTES we know the file is oversized and reject it — we
    # do not need to read (or allocate) the remaining bytes.
    data = await file.read(_MAX_BYTES + 1)

    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {_MAX_BYTES // (1024 * 1024)} MB limit.",
        )

    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File does not appear to be a valid PDF.",
        )

    try:
        pdf_doc = extract(data)
    except PDFProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    original_name = file.filename or "unknown.pdf"
    sha256 = hashlib.sha256(data).hexdigest()

    doc = Document(
        filename=original_name,
        original_name=original_name,
        file_size_bytes=len(data),
        mime_type="application/pdf",
        sha256=sha256,
        page_count=pdf_doc.page_count,
        raw_text=pdf_doc.text,
        status=DocStatus.READY,
        processed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    try:
        db.add(doc)
        await db.flush()  # materialise doc.id before creating chunks
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document with this content has already been uploaded.",
        )

    chunk_data = chunk_document(pdf_doc)
    vectors = await embedder.embed_batch([cd.content for cd in chunk_data])

    db.add_all([
        Chunk(
            document_id=doc.id,
            chunk_index=i,
            content=cd.content,
            char_start=cd.char_start,
            char_end=cd.char_end,
            page_number=cd.page_number,
            embedding=vectors[i],
        )
        for i, cd in enumerate(chunk_data)
    ])

    logger.info(
        "document_saved",
        extra={
            "document_id": str(doc.id),
            "uploaded_filename": original_name,
            "page_count": doc.page_count,
            "char_count": len(pdf_doc.text),
            "chunk_count": len(chunk_data),
        },
    )

    return UploadResponse(
        document_id=doc.id,
        filename=doc.filename,
        page_count=doc.page_count,
        char_count=len(pdf_doc.text),
        chunk_count=len(chunk_data),
        text_preview=pdf_doc.text[:_PREVIEW_CHARS],
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search chunks by semantic similarity",
)
async def search_chunks(
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
) -> SearchResponse:
    query_vec = await embedder.embed_text(body.query)

    distance_col = Chunk.embedding.cosine_distance(query_vec)

    stmt = (
        select(Chunk, (1 - distance_col).label("similarity"))
        .where(Chunk.embedding.isnot(None))
        .order_by(distance_col)
        .limit(body.top_k)
    )

    if body.document_id is not None:
        stmt = stmt.where(Chunk.document_id == body.document_id)

    rows = (await db.execute(stmt)).all()

    return SearchResponse(
        results=[
            ChunkResult(
                chunk_id=row.Chunk.id,
                document_id=row.Chunk.document_id,
                chunk_index=row.Chunk.chunk_index,
                page_number=row.Chunk.page_number,
                content=row.Chunk.content,
                # similarity is NULL when both vectors are zero (stub embedder)
                similarity_score=(
                    round(float(row.similarity), 4)
                    if row.similarity is not None else None
                ),
            )
            for row in rows
        ]
    )
