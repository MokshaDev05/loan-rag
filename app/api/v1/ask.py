from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Chunk
from app.services.answer_generator import OllamaUnavailableError, generate_answer
from app.services.embedder import Embedder

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])


def _get_embedder(request: Request) -> Embedder:
    return request.app.state.embedder


class AskRequest(BaseModel):
    question: str
    document_id: Optional[uuid.UUID] = None
    top_k: int = Field(default=5, ge=1, le=20)


class Citation(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    page_number: Optional[int]
    content: str


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question and get a cited answer",
)
async def ask(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    embedder: Embedder = Depends(_get_embedder),
) -> AskResponse:
    query_vec = await embedder.embed_text(body.question)

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

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No relevant chunks found. Upload a document first.",
        )

    chunks = [row.Chunk for row in rows]

    try:
        answer = await generate_answer(body.question, chunks)
    except OllamaUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    logger.info(
        "question_answered",
        extra={
            "chunk_count": len(chunks),
            "answer_chars": len(answer),
            "document_id": str(body.document_id) if body.document_id else None,
        },
    )

    return AskResponse(
        answer=answer,
        citations=[
            Citation(
                chunk_id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                content=c.content,
            )
            for c in chunks
        ],
    )
