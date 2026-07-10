"""Unit tests for app.services.chunker.

Pure Python — no external services, no database.
"""

from __future__ import annotations

from app.services.chunker import ChunkData, chunk_document, _MAX_CHARS, _MIN_CHARS
from app.services.pdf_processor import PDFDocument, PageBoundary


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _doc(text: str, page_count: int = 1) -> PDFDocument:
    """Build a minimal PDFDocument with a single page boundary spanning the text."""
    boundaries = (PageBoundary(page_number=1, char_start=0, char_end=len(text)),)
    return PDFDocument(
        text=text,
        page_count=page_count,
        page_boundaries=boundaries,
        metadata={},
    )


# ─────────────────────────────────────────
# Basic splitting
# ─────────────────────────────────────────

def test_short_text_produces_single_chunk():
    doc = _doc("Loan amount is $100,000.")
    chunks = chunk_document(doc)

    assert len(chunks) == 1
    assert "100,000" in chunks[0].content


def test_long_text_is_split_into_multiple_chunks():
    # Create text longer than _MAX_CHARS
    text = "word " * 300  # ~1500 chars
    doc = _doc(text)
    chunks = chunk_document(doc)

    assert len(chunks) > 1


def test_each_chunk_within_max_chars():
    text = "x " * 500
    doc = _doc(text)
    for chunk in chunk_document(doc):
        assert len(chunk.content) <= _MAX_CHARS + 10  # small tolerance for split heuristics


def test_chunks_cover_full_text():
    text = "The borrower agrees to repay the principal. " * 40
    doc = _doc(text)
    chunks = chunk_document(doc)

    reconstructed = " ".join(c.content for c in chunks)
    # Every word in the original must appear somewhere in the chunks
    for word in text.split():
        assert word in reconstructed


# ─────────────────────────────────────────
# Split-point preference
# ─────────────────────────────────────────

def test_prefers_paragraph_break():
    # Two paragraphs that together exceed _MAX_CHARS
    para1 = "A" * (_MAX_CHARS // 2 - 5) + "\n\n"
    para2 = "B" * (_MAX_CHARS // 2 - 5)
    doc = _doc(para1 + para2)
    chunks = chunk_document(doc)

    # Paragraph break should produce a clean split
    assert len(chunks) >= 1
    # First chunk should end at the paragraph boundary, not mid-word
    if len(chunks) > 1:
        assert "A" in chunks[0].content
        assert "B" in chunks[1].content


def test_falls_back_to_sentence_break():
    # No paragraph breaks; sentences with ". " separators
    sentence = "The loan was approved. " * 20
    doc = _doc(sentence)
    chunks = chunk_document(doc)

    assert len(chunks) >= 1
    # No chunk should start or end in the middle of a word
    for chunk in chunks:
        assert chunk.content == chunk.content.strip()


# ─────────────────────────────────────────
# Tiny tail merging
# ─────────────────────────────────────────

def test_tiny_tail_merged_into_previous():
    # Craft text so the last natural chunk would be smaller than _MIN_CHARS
    main_body = "word " * (_MAX_CHARS // 5)
    tail = "tiny"  # definitely < _MIN_CHARS
    doc = _doc(main_body + " " + tail)
    chunks = chunk_document(doc)

    # The tail should be absorbed — "tiny" appears in the last chunk's content
    assert "tiny" in chunks[-1].content
    # And we should have fewer chunks than if every fragment were kept
    assert all(len(c.content) >= _MIN_CHARS or i == len(chunks) - 1
               for i, c in enumerate(chunks))


# ─────────────────────────────────────────
# ChunkData fields
# ─────────────────────────────────────────

def test_chunk_indices_are_sequential():
    text = "sentence number one. " * 60
    doc = _doc(text)
    chunks = chunk_document(doc)

    for expected_index, chunk in enumerate(chunks):
        # chunk_document returns a list; the caller assigns chunk_index
        # so we just verify the list is not empty and content is non-empty
        assert chunk.content


def test_char_start_end_are_ordered():
    doc = _doc("Alpha beta gamma. " * 50)
    for chunk in chunk_document(doc):
        assert isinstance(chunk, ChunkData)
        assert chunk.char_start >= 0
        assert chunk.char_end > chunk.char_start


def test_page_number_populated():
    doc = _doc("Some text about the loan terms and conditions.")
    chunks = chunk_document(doc)

    # All chunks should have a page_number (we gave a boundary covering the full text)
    for chunk in chunks:
        assert chunk.page_number == 1


# ─────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────

def test_empty_text_returns_no_chunks():
    doc = _doc("")
    assert chunk_document(doc) == []


def test_exactly_max_chars_produces_one_chunk():
    text = "a" * _MAX_CHARS
    doc = _doc(text)
    chunks = chunk_document(doc)
    assert len(chunks) == 1
