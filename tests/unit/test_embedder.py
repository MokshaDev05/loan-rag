"""Unit tests for app.services.embedder.

The session-level _patch_sentence_transformer fixture in conftest.py
ensures SentenceTransformer is never actually loaded during tests.
"""

from __future__ import annotations

import pytest

from app.services.embedder import Embedder

_DIMS = 384


# ─────────────────────────────────────────
# Initialisation
# ─────────────────────────────────────────

async def test_initialize_sets_model():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")
    assert emb._model is None  # not yet loaded

    await emb.initialize()

    assert emb._model is not None  # SentenceTransformer mock was called


async def test_close_clears_model():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")
    await emb.initialize()
    await emb.close()

    assert emb._model is None


# ─────────────────────────────────────────
# embed_text
# ─────────────────────────────────────────

async def test_embed_text_returns_list_of_floats():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")
    await emb.initialize()

    vector = await emb.embed_text("What is the interest rate?")

    assert isinstance(vector, list)
    assert len(vector) == _DIMS
    assert all(isinstance(x, float) for x in vector)


async def test_embed_text_same_input_same_output():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")
    await emb.initialize()

    v1 = await emb.embed_text("hello")
    v2 = await emb.embed_text("hello")

    assert v1 == v2


# ─────────────────────────────────────────
# embed_batch
# ─────────────────────────────────────────

async def test_embed_batch_returns_one_vector_per_input():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")
    await emb.initialize()

    texts = ["loan amount", "interest rate", "borrower name"]
    vectors = await emb.embed_batch(texts)

    assert len(vectors) == len(texts)
    for v in vectors:
        assert len(v) == _DIMS


async def test_embed_batch_empty_list_returns_empty():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")
    await emb.initialize()

    result = await emb.embed_batch([])
    assert result == []


# ─────────────────────────────────────────
# Uninitialized fallback
# ─────────────────────────────────────────

async def test_uninitialized_embed_batch_returns_zero_vectors():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")
    # Do NOT call initialize()

    vectors = await emb.embed_batch(["test"])

    assert len(vectors) == 1
    assert len(vectors[0]) == _DIMS
    assert all(x == 0.0 for x in vectors[0])


async def test_uninitialized_embed_text_returns_zero_vector():
    emb = Embedder("sentence-transformers/all-MiniLM-L6-v2")

    v = await emb.embed_text("anything")
    assert len(v) == _DIMS
    assert all(x == 0.0 for x in v)
