from __future__ import annotations

import numpy as np

from eduanchor.bm25 import BM25
from eduanchor.utils import cohen_kappa, rrf_fuse, tokenize


def test_bm25_ranks_relevant_chunk_first() -> None:
    docs = [
        "机器学习是从数据中自动获取规律的方法。",
        "决策树使用信息增益选择划分特征。",
        "自然语言处理包括分词和词向量。",
    ]
    index = BM25(docs)
    scores = index.scores("信息增益 决策树")
    assert int(np.argmax(scores)) == 1


def test_tokenize_handles_chinese_and_latin() -> None:
    tokens = tokenize("RAG 检索增强")
    assert "rag" in tokens
    assert "检索" in tokens


def test_rrf_fusion_prefers_consistent_items() -> None:
    fused = rrf_fuse([[0, 1, 2], [0, 2, 1]])
    assert int(np.argmax(fused)) == 0


def test_cohen_kappa() -> None:
    assert cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
