from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Block:
    text: str
    page: int
    bbox: list[float] | None = None
    heading: bool = False
    size: float = 0.0


def _median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 10.0


def parse_pdf(path: str | Path) -> list[Block]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required to parse PDF files: uv add pymupdf") from exc

    blocks: list[Block] = []
    with fitz.open(str(path)) as doc:
        for page_number, page in enumerate(doc, start=1):
            data = page.get_text("dict")
            raw_blocks = data.get("blocks", [])
            sizes: list[float] = []
            for block in raw_blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip():
                            sizes.append(float(span.get("size", 0.0)))
            body_size = _median(sizes)
            for block in raw_blocks:
                if block.get("type") != 0:
                    continue
                lines = block.get("lines", [])
                text = "\n".join(
                    "".join(span.get("text", "") for span in line.get("spans", []))
                    for line in lines
                ).strip()
                if not text:
                    continue
                block_sizes = [
                    float(span.get("size", 0.0))
                    for line in lines
                    for span in line.get("spans", [])
                    if span.get("text", "").strip()
                ]
                size = _median(block_sizes)
                heading = len(text) <= 60 and size >= body_size * 1.12
                blocks.append(
                    Block(
                        text=text,
                        page=page_number,
                        bbox=[round(float(v), 2) for v in block.get("bbox", [])] or None,
                        heading=heading,
                        size=size,
                    )
                )
    return blocks


def parse_markdown(path: str | Path) -> list[Block]:
    text = Path(path).read_text(encoding="utf-8")
    return parse_plain_text(text, page_mode="markdown")


def parse_plain_text(text: str, page_mode: str = "single") -> list[Block]:
    """Convert markdown/plain text to blocks.

    ``<!-- page: N -->`` markers are honoured when present; otherwise headings
    are used to break sections and a synthetic page number is assigned.
    """
    blocks: list[Block] = []
    page = 1
    synthetic_page_size = 1800
    consumed = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        marker = re.match(r"<!--\s*page:\s*(\d+)\s*-->", line)
        if marker:
            page = int(marker.group(1))
            continue
        heading = bool(re.match(r"^#{1,4}\s+", line))
        if heading and page_mode != "markdown":
            page = 1 + consumed // synthetic_page_size
        content = re.sub(r"^#{1,4}\s+", "", line)
        if not content:
            continue
        blocks.append(Block(text=content, page=page, heading=heading))
        consumed += len(content)
        if page_mode != "markdown" and not heading:
            page = 1 + consumed // synthetic_page_size
    return blocks
