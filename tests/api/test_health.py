"""Tests for GET /api/v1/health.

No database or embedder required — the health endpoint only reads config.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def http():
    """Lightweight client — no DB fixtures, no lifespan."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def test_health_returns_200(http):
    resp = await http.get("/api/v1/health")
    assert resp.status_code == 200


async def test_health_status_is_ok(http):
    body = (await http.get("/api/v1/health")).json()
    assert body["status"] == "ok"


async def test_health_contains_required_fields(http):
    body = (await http.get("/api/v1/health")).json()
    assert "status" in body
    assert "app_name" in body
    assert "environment" in body
    assert "version" in body


async def test_health_app_name_matches_config(http):
    body = (await http.get("/api/v1/health")).json()
    assert body["app_name"] == "Loan Document Review"
