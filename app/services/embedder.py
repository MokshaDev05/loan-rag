from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class Embedder:
    """Generates 384-dim embeddings using sentence-transformers/all-MiniLM-L6-v2.

    Model loading is deferred to initialize() so the FastAPI lifespan controls
    when the blocking download/load happens.  encode() is CPU-bound, so it runs
    in a thread-pool executor to keep the async event loop free.
    """

    _DIMS: int = 384  # must match VECTOR(n) in the chunks table

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        logger.info("embedder_created", extra={"model": model_name})

    async def initialize(self) -> None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        logger.info("embedder_loading", extra={"model": self._model_name})
        loop = asyncio.get_running_loop()
        self._model = await loop.run_in_executor(
            None, SentenceTransformer, self._model_name
        )
        logger.info("embedder_ready", extra={"model": self._model_name, "dims": self._DIMS})

    async def close(self) -> None:
        self._model = None
        logger.info("embedder_closed", extra={"model": self._model_name})

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self._model is None:
            logger.warning(
                "embedder_not_initialized",
                extra={"model": self._model_name, "note": "returning zero vectors"},
            )
            return [[0.0] * self._DIMS for _ in texts]

        loop = asyncio.get_running_loop()
        vectors: list[list[float]] = await loop.run_in_executor(
            None,
            lambda: self._model.encode(texts, show_progress_bar=False).tolist(),
        )
        return vectors

    async def embed_text(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]
