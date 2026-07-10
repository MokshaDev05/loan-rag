"""Tests for POST /api/v1/documents/upload and POST /api/v1/documents/search.

Requires PostgreSQL (docker compose up -d db).
Ollama is not used by these endpoints.
"""

from __future__ import annotations

import pytest

from tests.conftest import make_pdf


# ─────────────────────────────────────────
# Upload — happy path
# ─────────────────────────────────────────

async def test_upload_returns_201(client):
    pdf = make_pdf("Loan Amount: $485,000. Interest Rate: 6.875%.")
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 201


async def test_upload_response_contains_document_id(client):
    pdf = make_pdf("Borrower: James Patterson.")
    body = (await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )).json()
    assert "document_id" in body
    assert body["document_id"]  # non-empty


async def test_upload_reports_chunk_count(client):
    # Provide enough text to produce at least one chunk
    pdf = make_pdf("The borrower agrees to repay the principal amount of $250,000.")
    body = (await client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", pdf, "application/pdf")},
    )).json()
    assert body["chunk_count"] >= 1


async def test_upload_reports_page_count(client):
    pdf = make_pdf("Page 1 text.", "Page 2 text.", "Page 3 text.")
    body = (await client.post(
        "/api/v1/documents/upload",
        files={"file": ("multi.pdf", pdf, "application/pdf")},
    )).json()
    assert body["page_count"] == 3


async def test_upload_includes_text_preview(client):
    pdf = make_pdf("Loan Number: RML-2024-00847. Borrower: James Patterson.")
    body = (await client.post(
        "/api/v1/documents/upload",
        files={"file": ("preview.pdf", pdf, "application/pdf")},
    )).json()
    assert "text_preview" in body
    assert len(body["text_preview"]) > 0


# ─────────────────────────────────────────
# Upload — error cases
# ─────────────────────────────────────────

async def test_upload_non_pdf_returns_415(client):
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("not_a_pdf.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 415


async def test_upload_non_pdf_bytes_returns_415(client):
    # Correct MIME type but not actually a PDF (no %PDF- header)
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("fake.pdf", b"definitely not a pdf", "application/pdf")},
    )
    assert resp.status_code == 415


async def test_upload_duplicate_returns_409(client):
    pdf = make_pdf("Identical content that will be hashed to detect duplicates.")
    files = {"file": ("dup.pdf", pdf, "application/pdf")}

    first = await client.post("/api/v1/documents/upload", files=files)
    assert first.status_code == 201

    # Re-upload the same bytes — sha256 collision guard kicks in
    files = {"file": ("dup.pdf", pdf, "application/pdf")}
    second = await client.post("/api/v1/documents/upload", files=files)
    assert second.status_code == 409


# ─────────────────────────────────────────
# Search
# ─────────────────────────────────────────

async def test_search_returns_results_after_upload(client):
    pdf = make_pdf("The interest rate is 6.875 percent per annum fixed.")
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    resp = await client.post(
        "/api/v1/documents/search",
        json={"query": "interest rate", "top_k": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert len(body["results"]) >= 1


async def test_search_result_has_required_fields(client):
    pdf = make_pdf("Borrower credit score is 742. Monthly income is $14,200.")
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    body = (await client.post(
        "/api/v1/documents/search",
        json={"query": "credit score"},
    )).json()

    result = body["results"][0]
    assert "chunk_id" in result
    assert "document_id" in result
    assert "content" in result
    assert "similarity_score" in result


async def test_search_respects_top_k(client):
    pdf = make_pdf(
        "Loan amount is four hundred thousand dollars.",
        "Interest rate is six point eight seven five percent.",
        "Monthly payment is three thousand dollars.",
    )
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    body = (await client.post(
        "/api/v1/documents/search",
        json={"query": "payment", "top_k": 2},
    )).json()

    assert len(body["results"]) <= 2


async def test_search_restricted_to_document_id(client):
    pdf_a = make_pdf("Document A: loan terms and conditions apply.")
    pdf_b = make_pdf("Document B: separate agreement for property insurance.")

    id_a = (await client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.pdf", pdf_a, "application/pdf")},
    )).json()["document_id"]

    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("b.pdf", pdf_b, "application/pdf")},
    )

    body = (await client.post(
        "/api/v1/documents/search",
        json={"query": "loan", "document_id": id_a, "top_k": 5},
    )).json()

    # Every result must belong to document A
    for r in body["results"]:
        assert r["document_id"] == id_a


async def test_search_no_documents_returns_empty(client):
    # Tables were truncated by clean_tables; no documents exist
    body = (await client.post(
        "/api/v1/documents/search",
        json={"query": "anything at all"},
    )).json()
    assert body["results"] == []
