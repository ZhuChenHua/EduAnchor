from __future__ import annotations

from eduanchor.chunker import chunk_blocks
from eduanchor.pdf_parser import Block


def test_chunker_preserves_heading_and_page() -> None:
    blocks = [
        Block(text="第一章 概述", page=1, heading=True),
        Block(text="机器学习是研究如何从数据中学习规律的一门学科。" * 3, page=1),
        Block(text="第二章 方法", page=2, heading=True),
        Block(text="监督学习使用带标签的数据进行训练。" * 4, page=2),
    ]
    chunks = chunk_blocks(blocks, "doc", target_chars=80, overlap_chars=10)
    assert len(chunks) >= 2
    assert chunks[0].heading == "第一章 概述"
    assert chunks[0].page == 1
    assert any(chunk.heading == "第二章 方法" for chunk in chunks)
    assert all(chunk.doc_id == "doc" for chunk in chunks)
    assert all(chunk.text for chunk in chunks)
