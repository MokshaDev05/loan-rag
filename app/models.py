from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DocStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    READY      = "ready"
    FAILED     = "failed"


class MessageRole(str, enum.Enum):
    USER      = "user"
    ASSISTANT = "assistant"


class Document(Base):
    __tablename__ = "documents"

    id:               Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename:         Mapped[str]             = mapped_column(Text, nullable=False)
    original_name:    Mapped[str]             = mapped_column(Text, nullable=False)
    file_size_bytes:  Mapped[int]             = mapped_column(BigInteger, nullable=False)
    mime_type:        Mapped[str]             = mapped_column(Text, nullable=False, default="application/pdf")
    sha256:           Mapped[str]             = mapped_column(String(64), nullable=False, unique=True)
    page_count:       Mapped[Optional[int]]   = mapped_column(Integer)
    status:           Mapped[DocStatus]       = mapped_column(
                          Enum(DocStatus, name="doc_status", values_callable=lambda x: [e.value for e in x]),
                          nullable=False,
                          default=DocStatus.PENDING,
                          server_default=DocStatus.PENDING.value,
                      )
    error_message:    Mapped[Optional[str]]   = mapped_column(Text)
    uploaded_at:      Mapped[datetime]        = mapped_column(nullable=False, server_default=func.now())
    processed_at:     Mapped[Optional[datetime]]
    raw_text:         Mapped[Optional[str]]   = mapped_column(Text)

    chunks:        Mapped[list["Chunk"]]         = relationship(back_populates="document", cascade="all, delete-orphan", lazy="selectin")
    conversations: Mapped[list["Conversation"]]  = relationship(back_populates="document", cascade="all, delete-orphan", lazy="noload")
    fields:        Mapped[list["DocumentField"]] = relationship(back_populates="document", cascade="all, delete-orphan", lazy="noload")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
        CheckConstraint("char_end > char_start", name="ck_chunks_char_range"),
    )

    id:          Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int]            = mapped_column(Integer, nullable=False)
    content:     Mapped[str]            = mapped_column(Text, nullable=False)
    embedding:   Mapped[Optional[list]] = mapped_column(Vector(384))
    char_start:  Mapped[int]            = mapped_column(Integer, nullable=False)
    char_end:    Mapped[int]            = mapped_column(Integer, nullable=False)
    page_number: Mapped[Optional[int]]  = mapped_column(Integer)
    token_count: Mapped[Optional[int]]  = mapped_column(Integer)
    created_at:  Mapped[datetime]       = mapped_column(nullable=False, server_default=func.now())

    document:  Mapped["Document"]       = relationship(back_populates="chunks", lazy="noload")
    citations: Mapped[list["Citation"]] = relationship(back_populates="chunk", cascade="all, delete-orphan", lazy="noload")


class Conversation(Base):
    __tablename__ = "conversations"

    id:          Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    title:       Mapped[Optional[str]] = mapped_column(Text)
    created_at:  Mapped[datetime]      = mapped_column(nullable=False, server_default=func.now())
    updated_at:  Mapped[datetime]      = mapped_column(nullable=False, server_default=func.now())

    document: Mapped["Document"]      = relationship(back_populates="conversations", lazy="noload")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Message.sequence_number", lazy="selectin")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_number", name="uq_messages_conversation_seq"),
    )

    id:              Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role:            Mapped[MessageRole]    = mapped_column(Enum(MessageRole, name="message_role", values_callable=lambda x: [e.value for e in x]), nullable=False)
    content:         Mapped[str]            = mapped_column(Text, nullable=False)
    sequence_number: Mapped[int]            = mapped_column(Integer, nullable=False)
    latency_ms:      Mapped[Optional[dict]] = mapped_column(JSON)
    created_at:      Mapped[datetime]       = mapped_column(nullable=False, server_default=func.now())

    conversation: Mapped["Conversation"]  = relationship(back_populates="messages", lazy="noload")
    citations:    Mapped[list["Citation"]] = relationship(back_populates="message", cascade="all, delete-orphan", order_by="Citation.rank", lazy="selectin")


class Citation(Base):
    __tablename__ = "citations"
    __table_args__ = (
        UniqueConstraint("message_id", "chunk_id", name="uq_citations_message_chunk"),
        CheckConstraint("similarity_score BETWEEN 0 AND 1", name="ck_citations_score_range"),
        CheckConstraint("rank >= 1", name="ck_citations_rank_positive"),
    )

    id:               Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id",   ondelete="CASCADE"), nullable=False, index=True)
    similarity_score: Mapped[float]     = mapped_column(Float, nullable=False)
    rank:             Mapped[int]       = mapped_column(Integer, nullable=False)

    message: Mapped["Message"] = relationship(back_populates="citations", lazy="noload")
    chunk:   Mapped["Chunk"]   = relationship(back_populates="citations", lazy="noload")


class DocumentField(Base):
    __tablename__ = "document_fields"
    __table_args__ = (
        UniqueConstraint("document_id", "field_name", name="uq_fields_document_name"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_fields_confidence_range"),
    )

    id:              Mapped[uuid.UUID]             = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id:     Mapped[uuid.UUID]             = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    source_chunk_id: Mapped[Optional[uuid.UUID]]   = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"))
    field_name:      Mapped[str]                   = mapped_column(Text, nullable=False)
    field_value:     Mapped[str]                   = mapped_column(Text, nullable=False)
    confidence:      Mapped[Optional[float]]       = mapped_column(Float)
    created_at:      Mapped[datetime]              = mapped_column(nullable=False, server_default=func.now())

    document:     Mapped["Document"]        = relationship(back_populates="fields", lazy="noload")
    source_chunk: Mapped[Optional["Chunk"]] = relationship(lazy="noload")
