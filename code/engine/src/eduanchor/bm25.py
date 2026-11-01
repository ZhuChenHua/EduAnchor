from __future__ import annotations

import math

import numpy as np

from .utils import tokenize


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = [tokenize(doc) for doc in documents]
        self.doc_len = np.array([len(doc) for doc in self.docs], dtype=float)
        self.avgdl = float(self.doc_len.mean()) if len(self.docs) else 0.0
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for doc in self.docs:
            counts: dict[str, int] = {}
            for token in doc:
                counts[token] = counts.get(token, 0) + 1
            self.tf.append(counts)
            for token in counts:
                df[token] = df.get(token, 0) + 1
        n = len(self.docs)
        self.idf = {
            token: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)) for token, freq in df.items()
        }

    def scores(self, query: str) -> np.ndarray:
        query_tokens = tokenize(query)
        scores = np.zeros(len(self.docs), dtype=float)
        if not query_tokens or not self.docs:
            return scores
        for token in query_tokens:
            idf = self.idf.get(token)
            if idf is None:
                continue
            for index, counts in enumerate(self.tf):
                freq = counts.get(token)
                if not freq:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * self.doc_len[index] / max(self.avgdl, 1e-6))
                scores[index] += idf * (freq * (self.k1 + 1)) / denom
        return scores
