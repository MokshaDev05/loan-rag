from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.services.pdf_processor import PDFDocument

logger = logging.getLogger(__name__)

_MAX_CHARS = 800
_MIN_CHARS = 50   # fragments shorter than this are absorbed into the previous chunk


@dataclass
class ChunkData:
    content:     str
    char_start:  int
    char_end:    int
    page_number: Optional[int]


def chunk_document(doc: PDFDocument) -> List[ChunkData]:
    """Split full document text into character-level chunks.

    Looks for clean split points in this order:
    1. Paragraph break (\\n\\n)
    2. Sentence end (. / ! / ? followed by space or newline)
    3. Word boundary (space)
    4. Hard cut at _MAX_CHARS

    Each chunk is at most _MAX_CHARS characters.  Fragments shorter than
    _MIN_CHARS at the tail of the document are merged into the preceding
    chunk so we don't store near-empty rows.
    """
    text = doc.text
    total = len(text)
    results: List[ChunkData] = []
    start = 0

    while start < total:
        end = min(start + _MAX_CHARS, total)

        if end < total:
            # 1. paragraph break
            pos = text.rfind("\n\n", start + _MIN_CHARS, end)
            if pos != -1:
                end = pos + 2
            else:
                # 2. sentence break
                best = -1
                for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
                    p = text.rfind(sep, start + _MIN_CHARS, end)
                    if p > best:
                        best = p
                if best != -1:
                    end = best + 2
                else:
                    # 3. word break
                    p = text.rfind(" ", start + _MIN_CHARS, end)
                    if p != -1:
                        end = p + 1
                    # 4. hard cut — end stays at start + _MAX_CHARS

        content = text[start:end].strip()

        if content:
            if len(content) < _MIN_CHARS and results:
                # merge tiny tail into previous chunk
                prev = results[-1]
                results[-1] = ChunkData(
                    content=prev.content + " " + content,
                    char_start=prev.char_start,
                    char_end=end,
                    page_number=prev.page_number,
                )
            else:
                results.append(ChunkData(
                    content=content,
                    char_start=start,
                    char_end=end,
                    page_number=doc.page_number_at(start),
                ))

        start = max(end, start + 1)  # always advance to prevent infinite loop

    logger.info(
        "document_chunked",
        extra={
            "chunk_count": len(results),
            "total_chars": total,
        },
    )
    return results
