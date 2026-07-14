from __future__ import annotations

import asyncio
import json
import logging
from typing import List

import httpx

from app.config import settings
from app.models import Chunk

logger = logging.getLogger(__name__)

_OLLAMA_TIMEOUT = 120.0

_PROMPT = """\
You are a loan document analysis assistant. Answer the question using only the \
context provided below. If the answer is not present in the context, say \
"I cannot find this information in the document." Be concise and precise.

Context:
{context}

Question: {question}

Answer:"""


class LLMUnavailableError(Exception):
    """Raised when the configured LLM backend is unreachable or returns an error."""


# Keep old name as alias so existing callers don't break.
OllamaUnavailableError = LLMUnavailableError


def _build_context(chunks: List[Chunk]) -> str:
    parts = []
    for c in chunks:
        page = f" (Page {c.page_number})" if c.page_number else ""
        parts.append(f"[Chunk {c.chunk_index}{page}]\n{c.content}")
    return "\n\n---\n\n".join(parts)


async def _generate_ollama(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": settings.LLM_MODEL, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMUnavailableError("Ollama request timed out after 120 s.") from exc
    except httpx.NetworkError as exc:
        raise LLMUnavailableError(
            f"Ollama network error at {settings.OLLAMA_BASE_URL}: {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise LLMUnavailableError(
            f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc

    try:
        return resp.json().get("response", "").strip()
    except Exception as exc:
        raise LLMUnavailableError(f"Ollama returned non-JSON response: {exc}") from exc


async def _generate_bedrock(prompt: str) -> str:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    body = json.dumps({
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 1024},
    })

    def _invoke() -> str:
        client = boto3.client("bedrock-runtime", region_name=settings.BEDROCK_REGION)
        resp = client.invoke_model(
            modelId=settings.BEDROCK_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        try:
            result = json.loads(resp["body"].read())
            return result["output"]["message"]["content"][0]["text"].strip()
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMUnavailableError(f"Unexpected Bedrock response shape: {exc}") from exc

    try:
        return await asyncio.to_thread(_invoke)
    except ClientError as exc:
        raise LLMUnavailableError(
            f"Bedrock error: {exc.response['Error']['Code']}: {exc.response['Error']['Message']}"
        ) from exc
    except BotoCoreError as exc:
        raise LLMUnavailableError(f"Bedrock connection error: {exc}") from exc


async def generate_answer(question: str, chunks: List[Chunk]) -> str:
    """Generate a grounded answer from retrieved chunks using the configured LLM."""
    context = _build_context(chunks)
    prompt = _PROMPT.format(context=context, question=question)

    logger.info(
        "llm_request",
        extra={
            "provider": settings.LLM_PROVIDER,
            "chunk_count": len(chunks),
            "prompt_chars": len(prompt),
        },
    )

    if settings.LLM_PROVIDER == "bedrock":
        answer = await _generate_bedrock(prompt)
    else:
        answer = await _generate_ollama(prompt)

    logger.info("llm_response", extra={"answer_chars": len(answer)})
    return answer
