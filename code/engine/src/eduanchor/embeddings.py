from __future__ import annotations

import hashlib
import logging

import numpy as np

from .config import Settings
from .utils import normalize_rows, tokenize

logger = logging.getLogger(__name__)


class Embedder:
    name = "base"
    dim = 0

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        raise NotImplementedError


class HashEmbedder(Embedder):
    """Deterministic offline fallback.

    It hashes word/character n-grams into a fixed space. It is not a semantic
    model, but it makes the whole pipeline runnable without downloads and gives
    a meaningful lexical-similarity baseline for demos and tests.
    """

    name = "hash-512"
    dim = 512

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = tokenize(text)
            if not tokens:
                continue
            for token in tokens:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                matrix[row, index] += sign
        return normalize_rows(matrix)


class BGEM3Embedder(Embedder):
    name = "bge-m3"

    def __init__(self, model_path: str, use_fp16: bool = True) -> None:
        from FlagEmbedding import BGEM3FlagModel  # type: ignore

        self.model = BGEM3FlagModel(model_path, use_fp16=use_fp16)
        self.dim = 1024

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        output = self.model.encode(texts, batch_size=8, max_length=512)["dense_vecs"]
        return normalize_rows(np.asarray(output, dtype=np.float32))


def get_embedder(settings: Settings) -> Embedder:
    backend = settings.embed_backend.lower()
    if backend in {"hash", "hash-512", "fallback"}:
        return HashEmbedder()
    if backend in {"bge", "bge-m3", "auto"}:
        try:
            return BGEM3Embedder(settings.embed_model_path)
        except Exception as exc:  # noqa: BLE001 - optional heavy dependency
            logger.info("BGE-M3 unavailable, using hash embedder: %s", exc)
            return HashEmbedder()
    return HashEmbedder()
