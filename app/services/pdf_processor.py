from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import pdfplumber

logger = logging.getLogger(__name__)

_PAGE_SEPARATOR = "\n\n"
_SEP_LEN = len(_PAGE_SEPARATOR)

_METADATA_KEYS = ("Title", "Author", "Subject", "Creator", "Producer", "CreationDate")


# ─────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────

class PDFProcessingError(Exception):
    """Raised when a PDF cannot be read or yields no extractable text."""


# ─────────────────────────────────────────
# Result types
# ─────────────────────────────────────────

@dataclass(frozen=True)
class PageBoundary:
    """Character range in `PDFDocument.text` that belongs to one PDF page."""
    page_number: int    # 1-based, matches pdfplumber convention
    char_start:  int
    char_end:    int


@dataclass(frozen=True)
class PDFDocument:
    """All extractable content from a PDF file."""
    text:            str
    page_count:      int
    page_boundaries: tuple[PageBoundary, ...]   # len == page_count, ordered by page_number
    metadata:        dict[str, str]

    def page_number_at(self, char_offset: int) -> Optional[int]:
        """Return the 1-based page number that contains *char_offset*, or None."""
        for boundary in self.page_boundaries:
            if boundary.char_start <= char_offset < boundary.char_end:
                return boundary.page_number
        return None


# ─────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────

def _clean(text: str) -> str:
    text = text.replace("\x00", "")                          # null bytes from some PDFs
    text = text.replace("\r\n", "\n").replace("\r", "\n")    # normalize line endings
    text = re.sub(r"\n{3,}", "\n\n", text)                   # collapse excessive blank lines
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


def _extract_metadata(pdf: pdfplumber.PDF) -> dict[str, str]:
    raw = pdf.metadata or {}
    return {
        key.lower(): str(value)
        for key in _METADATA_KEYS
        if (value := raw.get(key))
    }


# ─────────────────────────────────────────
# Public API
# ─────────────────────────────────────────

def extract(file_bytes: bytes) -> PDFDocument:
    """Extract text, page boundaries, and metadata from PDF bytes.

    Returns a :class:`PDFDocument` whose ``text`` field is the full document
    text with pages joined by ``"\\n\\n"``.  Each :class:`PageBoundary` maps a
    half-open char range ``[char_start, char_end)`` in that string back to its
    1-based page number, so downstream chunkers can record which page every
    chunk came from.

    Raises
    ------
    PDFProcessingError
        The file is empty, corrupt, password-protected, or contains no
        extractable text (e.g. a scanned image PDF).
    """
    if not file_bytes:
        raise PDFProcessingError("File is empty")

    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            if not pdf.pages:
                raise PDFProcessingError("PDF contains no pages")

            metadata = _extract_metadata(pdf)
            page_count = len(pdf.pages)
            pages: list[str] = []
            boundaries: list[PageBoundary] = []
            cursor = 0
            empty_pages: list[int] = []

            for i, page in enumerate(pdf.pages):
                raw = page.extract_text() or ""
                text = _clean(raw)

                if not text:
                    empty_pages.append(page.page_number)

                boundaries.append(PageBoundary(
                    page_number=page.page_number,
                    char_start=cursor,
                    char_end=cursor + len(text),
                ))
                pages.append(text)

                cursor += len(text)
                if i < page_count - 1:
                    cursor += _SEP_LEN   # account for the "\n\n" joining separator

    except PDFProcessingError:
        raise
    except Exception as exc:
        hint = " (the file may be password-protected)" if "password" in str(exc).lower() else ""
        raise PDFProcessingError(f"Could not read PDF{hint}: {exc}") from exc

    if empty_pages:
        logger.warning(
            "pdf_pages_without_text",
            extra={"empty_pages": empty_pages, "total_pages": page_count},
        )

    full_text = _PAGE_SEPARATOR.join(pages)

    if not full_text.strip():
        raise PDFProcessingError(
            "No extractable text found. "
            "The PDF may be a scanned image and would require OCR."
        )

    logger.info(
        "pdf_extracted",
        extra={
            "page_count": page_count,
            "char_count": len(full_text),
            "empty_pages": len(empty_pages),
            "metadata_keys": list(metadata.keys()),
        },
    )

    return PDFDocument(
        text=full_text,
        page_count=page_count,
        page_boundaries=tuple(boundaries),
        metadata=metadata,
    )
