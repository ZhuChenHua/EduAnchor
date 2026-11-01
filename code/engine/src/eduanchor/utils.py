from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

import numpy as np

_CJK = r"\u4e00-\u9fff"
_TOKEN_RE = re.compile(rf"[a-zA-Z0-9]+|[{_CJK}]+")
_SENT_RE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
_EN_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "do", "does",
    "for", "from", "had", "has", "have", "he", "her", "his", "how", "i", "in",
    "is", "it", "its", "may", "me", "might", "my", "no", "not", "of", "on",
    "or", "our", "she", "should", "that", "the", "their", "them", "they",
    "this", "to", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "yes", "you", "your",
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def stable_id(*parts: str, length: int = 16) -> str:
    digest = hashlib.blake2b("::".join(parts).encode("utf-8"), digest_size=12).hexdigest()
    return digest[:length]


def tokenize(text: str) -> list[str]:
    """Tokenize Chinese with unigrams+bigrams and Latin with words."""
    text = text.lower()
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        piece = match.group()
        if piece[0].isascii():
            if piece not in _EN_STOP:
                tokens.append(piece)
        else:
            tokens.extend(piece)
            tokens.extend(piece[i : i + 2] for i in range(len(piece) - 1))
    return tokens


def split_sentences(text: str, min_len: int = 6) -> list[str]:
    parts = [p.strip(" \t\r\n-•") for p in _SENT_RE.split(text)]
    return [p for p in parts if len(p) >= min_len]


def truncate(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def minmax(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low, high = float(values.min()), float(values.max())
    if math.isclose(low, high):
        return np.zeros_like(values)
    return (values - low) / (high - low)


def overlap_score(query: str, text: str) -> float:
    q = set(tokenize(query))
    if not q:
        return 0.0
    t = set(tokenize(text))
    return len(q & t) / len(q)


def rrf_fuse(rankings: Sequence[Sequence[int]], k: int = 60) -> np.ndarray:
    """Reciprocal rank fusion over integer id rankings."""
    if not rankings:
        return np.zeros(0, dtype=float)
    size = max((max(r) for r in rankings if len(r)), default=-1) + 1
    scores = np.zeros(size, dtype=float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (k + rank + 1)
    return scores


def bootstrap_ci(values: Iterable[float], n_boot: int = 2000, alpha: float = 0.05) -> list[float]:
    data = np.asarray(list(values), dtype=float)
    if data.size == 0:
        return [0.0, 0.0]
    rng = np.random.default_rng(20270101)
    means = np.array([rng.choice(data, size=data.size, replace=True).mean() for _ in range(n_boot)])
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return [round(float(lo), 4), round(float(hi), 4)]


def cohen_kappa(a: Sequence[int], b: Sequence[int]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    labels = sorted(set(a) | set(b))
    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    expected = sum((a.count(label) / n) * (b.count(label) / n) for label in labels)
    if math.isclose(expected, 1.0):
        return 1.0
    return float((observed - expected) / (1.0 - expected))
