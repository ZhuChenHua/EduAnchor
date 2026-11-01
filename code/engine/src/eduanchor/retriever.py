from __future__ import annotations

import numpy as np

from .bm25 import BM25
from .config import Settings
from .embeddings import Embedder
from .schemas import Chunk, RetrievedChunk
from .store import Store
from .utils import minmax, overlap_score


class Retriever:
    def __init__(self, store: Store, embedder: Embedder, settings: Settings) -> None:
        self.store = store
        self.embedder = embedder
        self.settings = settings

    def _vectors(self, doc_id: str, chunks: list[Chunk]) -> np.ndarray:
        saved = self.store.load_vectors(doc_id)
        if saved:
            ids, vectors, backend = saved
            compatible = (
                backend == self.embedder.name
                and [chunk.id for chunk in chunks] == ids
                and len(vectors) == len(chunks)
                and vectors.shape[1] == self.embedder.dim
            )
            if compatible:
                return vectors
        vectors = self.embedder.encode([chunk.text for chunk in chunks])
        self.store.save_vectors(
            doc_id, [chunk.id for chunk in chunks], vectors, self.embedder.name
        )
        return vectors

    def retrieve(
        self,
        doc_id: str,
        query: str,
        top_k: int | None = None,
        use_bm25: bool = True,
        use_dense: bool = True,
        use_rerank: bool = True,
    ) -> list[RetrievedChunk]:
        chunks = self.store.list_chunks(doc_id)
        if not chunks:
            return []
        top_k = top_k or self.settings.top_k
        candidate_pool = min(max(top_k * 4, top_k), len(chunks))

        rankings: list[list[int]] = []
        bm25_scores = np.zeros(len(chunks), dtype=float)
        dense_scores = np.zeros(len(chunks), dtype=float)

        if use_bm25:
            bm25 = BM25([chunk.text for chunk in chunks])
            bm25_scores = bm25.scores(query)
            rankings.append(np.argsort(-bm25_scores)[:candidate_pool].tolist())

        if use_dense:
            vectors = self._vectors(doc_id, chunks)
            query_vector = self.embedder.encode([query], is_query=True)[0]
            dense_scores = vectors @ query_vector
            rankings.append(np.argsort(-dense_scores)[:candidate_pool].tolist())

        if not rankings:
            indices = list(range(min(candidate_pool, len(chunks))))
        else:
            fused = np.zeros(len(chunks), dtype=float)
            for ranking in rankings:
                for rank, index in enumerate(ranking):
                    fused[index] += 1.0 / (60 + rank + 1)
            indices = np.argsort(-fused)[: candidate_pool * 2].tolist()

        bm25_norm = minmax(bm25_scores)
        dense_norm = minmax(dense_scores)
        candidates: list[RetrievedChunk] = []
        for index in indices:
            chunk = chunks[index]
            lexical = overlap_score(query, chunk.text)
            rerank = 0.6 * lexical + 0.25 * dense_norm[index] + 0.15 * bm25_norm[index]
            if not use_rerank:
                rerank = 0.5 * dense_norm[index] + 0.5 * bm25_norm[index]
            score = 0.5 * rerank + 0.3 * dense_norm[index] + 0.2 * bm25_norm[index]
            candidates.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=float(score),
                    bm25=float(bm25_scores[index]),
                    dense=float(dense_scores[index]),
                    rerank=float(rerank),
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:top_k]

    def coverage_for_query(self, query: str, candidates: list[RetrievedChunk]) -> float:
        if not candidates:
            return 0.0
        top = candidates[0]
        dense_values = np.array([candidate.dense for candidate in candidates], dtype=float)
        margin = top.dense - float(dense_values.mean())
        lexical = overlap_score(query, top.chunk.text)
        return float(
            0.55 * max(0.0, top.dense) + 0.30 * max(0.0, margin) + 0.15 * lexical
        )
