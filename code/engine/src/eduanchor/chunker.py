from __future__ import annotations

import re

from .pdf_parser import Block
from .schemas import Chunk
from .utils import stable_id


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def chunk_blocks(
    blocks: list[Block],
    doc_id: str,
    target_chars: int = 520,
    overlap_chars: int = 80,
) -> list[Chunk]:
    """Layout-aware chunking that preserves headings, page and bbox anchors."""
    chunks: list[Chunk] = []
    heading: str | None = None
    buffer: list[str] = []
    first_page = blocks[0].page if blocks else 1
    first_bbox = blocks[0].bbox if blocks else None
    last_page = first_page
    last_bbox = first_bbox

    def flush() -> None:
        nonlocal buffer, first_page, first_bbox
        text = _clean("\n".join(buffer))
        if len(text) < 40:
            buffer = []
            return
        ordinal = len(chunks)
        chunks.append(
            Chunk(
                id=stable_id(doc_id, str(ordinal), text[:60]),
                doc_id=doc_id,
                ordinal=ordinal,
                text=text,
                page=first_page,
                bbox=first_bbox,
                heading=heading,
            )
        )
        if overlap_chars > 0:
            tail = text[-overlap_chars:]
            buffer = [tail]
            first_page = last_page
            first_bbox = last_bbox
        else:
            buffer = []

    for block in blocks:
        text = _clean(block.text)
        if not text:
            continue
        last_page = block.page
        last_bbox = block.bbox
        if block.heading:
            flush()
            heading = text
            buffer = [text]
            first_page = block.page
            first_bbox = block.bbox
            continue
        if not buffer:
            first_page = block.page
            first_bbox = block.bbox
        buffer.append(text)
        if sum(len(part) for part in buffer) >= target_chars:
            flush()
    flush()

    if not chunks and blocks:
        text = _clean("\n".join(block.text for block in blocks))
        chunks.append(
            Chunk(
                id=stable_id(doc_id, "0", text[:60]),
                doc_id=doc_id,
                ordinal=0,
                text=text,
                page=blocks[0].page,
                bbox=blocks[0].bbox,
                heading=None,
            )
        )
    return chunks
