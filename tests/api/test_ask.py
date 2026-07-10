"""Tests for POST /api/v1/ask.

Requires PostgreSQL (docker compose up -d db).
Ollama is fully mocked — no LLM needs to be running.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_pdf

_OLLAMA_PATH = "app.services.answer_generator.httpx.AsyncClient"
_FAKE_ANSWER = "The loan amount is $485,000 at an interest rate of 6.875%."


def _mock_ollama(answer: str = _FAKE_ANSWER):
    """Context manager that patches the Ollama HTTP call."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": answer}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response

    return patch(_OLLAMA_PATH, return_value=mock_client)


# ─────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────

async def test_ask_returns_200(client):
    pdf = make_pdf("Loan Amount: $485,000. Interest Rate: 6.875% per annum.")
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    with _mock_ollama():
        resp = await client.post(
            "/api/v1/ask",
            json={"question": "What is the loan amount?", "top_k": 3},
        )

    assert resp.status_code == 200


async def test_ask_returns_answer_string(client):
    pdf = make_pdf("Loan Amount: $485,000. Interest Rate: 6.875% per annum.")
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    with _mock_ollama(_FAKE_ANSWER):
        body = (await client.post(
            "/api/v1/ask",
            json={"question": "What is the loan amount?"},
        )).json()

    assert body["answer"] == _FAKE_ANSWER


async def test_ask_returns_citations(client):
    pdf = make_pdf("Loan Amount: $485,000. Monthly Payment: $3,186.")
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    with _mock_ollama():
        body = (await client.post(
            "/api/v1/ask",
            json={"question": "What is the monthly payment?"},
        )).json()

    assert "citations" in body
    assert len(body["citations"]) >= 1


async def test_ask_citation_has_required_fields(client):
    pdf = make_pdf("Borrower: James Patterson. Credit Score: 742.")
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    with _mock_ollama():
        body = (await client.post(
            "/api/v1/ask",
            json={"question": "Who is the borrower?"},
        )).json()

    citation = body["citations"][0]
    assert "chunk_id" in citation
    assert "document_id" in citation
    assert "content" in citation


async def test_ask_restricted_to_document_id(client):
    pdf_a = make_pdf("Document A has a loan of $100,000.")
    pdf_b = make_pdf("Document B has a loan of $999,999.")

    id_a = (await client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.pdf", pdf_a, "application/pdf")},
    )).json()["document_id"]

    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("b.pdf", pdf_b, "application/pdf")},
    )

    with _mock_ollama():
        body = (await client.post(
            "/api/v1/ask",
            json={"question": "What is the loan amount?", "document_id": id_a},
        )).json()

    # All citations must come from document A
    for citation in body["citations"]:
        assert citation["document_id"] == id_a


# ─────────────────────────────────────────
# Error cases
# ─────────────────────────────────────────

async def test_ask_no_documents_returns_404(client):
    # Tables truncated; no documents uploaded
    with _mock_ollama():
        resp = await client.post(
            "/api/v1/ask",
            json={"question": "What is the interest rate?"},
        )
    assert resp.status_code == 404


async def test_ask_ollama_unavailable_returns_503(client):
    import httpx

    pdf = make_pdf("Loan Amount: $100,000.")
    await client.post(
        "/api/v1/documents/upload",
        files={"file": ("loan.pdf", pdf, "application/pdf")},
    )

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch(_OLLAMA_PATH, return_value=mock_client):
        resp = await client.post(
            "/api/v1/ask",
            json={"question": "What is the rate?"},
        )

    assert resp.status_code == 503


async def test_ask_missing_question_returns_422(client):
    resp = await client.post("/api/v1/ask", json={})
    assert resp.status_code == 422


async def test_ask_top_k_out_of_range_returns_422(client):
    resp = await client.post(
        "/api/v1/ask",
        json={"question": "test", "top_k": 0},  # minimum is 1
    )
    assert resp.status_code == 422
