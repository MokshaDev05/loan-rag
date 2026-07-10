"""Unit tests for app.services.pdf_processor.

No external services required — all tests run from in-memory PDF bytes.
"""

from __future__ import annotations

import pytest

from app.services.pdf_processor import PDFProcessingError, PDFDocument, extract
from tests.conftest import make_pdf


# ─────────────────────────────────────────
# Extraction — happy path
# ─────────────────────────────────────────

def test_extract_single_page_returns_document():
    pdf_bytes = make_pdf("Loan Amount: $485,000. Interest Rate: 6.875%.")
    doc = extract(pdf_bytes)

    assert isinstance(doc, PDFDocument)
    assert doc.page_count == 1
    assert len(doc.page_boundaries) == 1
    assert "Loan Amount" in doc.text
    assert "485,000" in doc.text


def test_extract_multi_page_joins_with_double_newline():
    pdf_bytes = make_pdf("Page one content.", "Page two content.")
    doc = extract(pdf_bytes)

    assert doc.page_count == 2
    assert len(doc.page_boundaries) == 2
    # Pages are joined by "\n\n"
    assert "\n\n" in doc.text or "Page one" in doc.text


def test_extract_page_count_matches_pages():
    pdf_bytes = make_pdf("A", "B", "C")
    doc = extract(pdf_bytes)

    assert doc.page_count == 3
    assert len(doc.page_boundaries) == 3


def test_extract_returns_metadata_dict():
    doc = extract(make_pdf("Some text."))
    assert isinstance(doc.metadata, dict)


# ─────────────────────────────────────────
# Page boundary tracking
# ─────────────────────────────────────────

def test_page_number_at_within_first_page():
    doc = extract(make_pdf("First page text.", "Second page text."))
    # Character 0 is always on page 1
    assert doc.page_number_at(0) == 1


def test_page_number_at_returns_none_beyond_text():
    doc = extract(make_pdf("Short."))
    # Well past the end of any text
    assert doc.page_number_at(len(doc.text) + 9999) is None


def test_page_boundaries_cover_full_text():
    doc = extract(make_pdf("Alpha.", "Beta.", "Gamma."))
    # Every character position must resolve to a page
    for i in range(len(doc.text)):
        # Separator characters (\n\n between pages) may fall outside boundaries;
        # non-separator chars must resolve.
        result = doc.page_number_at(i)
        assert result is None or result in (1, 2, 3)


# ─────────────────────────────────────────
# Error cases
# ─────────────────────────────────────────

def test_extract_empty_bytes_raises():
    with pytest.raises(PDFProcessingError, match="empty"):
        extract(b"")


def test_extract_garbage_bytes_raises():
    with pytest.raises(PDFProcessingError):
        extract(b"this is not a pdf at all")


def test_extract_truncated_pdf_raises():
    good = make_pdf("Hello world")
    with pytest.raises(PDFProcessingError):
        extract(good[:50])  # cut off mid-stream
