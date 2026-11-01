from __future__ import annotations

import re

from .schemas import Chunk, KnowledgeCard, SourceSpan
from .utils import split_sentences, stable_id, tokenize, truncate

_DEFINITION_CUES = ("是指", "定义为", "称为", "指的是", "是一种", "是研究", "定义是")
_PROCEDURE_CUES = ("步骤", "首先", "其次", "然后", "最后", "流程", "算法")
_PRINCIPLE_CUES = ("原理", "规律", "定理", "性质", "机制", "意味着", "因此")
_EXAMPLE_CUES = ("例如", "比如", "例如说", "举例")


def _kind(text: str) -> str:
    if any(cue in text for cue in _DEFINITION_CUES):
        return "definition"
    if any(cue in text for cue in _PROCEDURE_CUES):
        return "procedure"
    if any(cue in text for cue in _PRINCIPLE_CUES):
        return "principle"
    if any(cue in text for cue in _EXAMPLE_CUES):
        return "example"
    return "concept"


def _title(chunk: Chunk) -> str:
    if chunk.heading:
        return truncate(chunk.heading, 40)
    sentences = split_sentences(chunk.text)
    candidate = sentences[0] if sentences else chunk.text
    candidate = re.split(r"[，,。；;：:]", candidate)[0]
    return truncate(candidate, 40) or f"知识点 {chunk.ordinal + 1}"


def _key_points(text: str, limit: int = 4) -> list[str]:
    sentences = split_sentences(text)
    scored: list[tuple[float, str]] = []
    cues = _DEFINITION_CUES + _PROCEDURE_CUES + _PRINCIPLE_CUES + _EXAMPLE_CUES
    for sentence in sentences:
        score = 0.0
        if any(cue in sentence for cue in cues):
            score += 2.0
        if re.search(r"\d", sentence):
            score += 0.3
        score += min(len(sentence), 80) / 160
        scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    picked: list[str] = []
    used_tokens: set[str] = set()
    for _, sentence in scored:
        tokens = set(tokenize(sentence))
        novelty = 1.0 - (len(tokens & used_tokens) / max(len(tokens), 1))
        if novelty < 0.35:
            continue
        picked.append(truncate(sentence, 120))
        used_tokens |= tokens
        if len(picked) >= limit:
            break
    return picked


def _tags(text: str, limit: int = 6) -> list[str]:
    tokens = [t for t in tokenize(text) if len(t) >= 2 and not t.isascii()]
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (item[1], len(item[0])), reverse=True)
    tags: list[str] = []
    for token, _ in ranked:
        if any(token in existing for existing in tags):
            continue
        tags.append(token)
        if len(tags) >= limit:
            break
    return tags


def extract_cards(doc_id: str, chunks: list[Chunk], max_cards: int = 120) -> list[KnowledgeCard]:
    cards: list[KnowledgeCard] = []
    for chunk in chunks:
        if len(chunk.text) < 60:
            continue
        text = chunk.text
        summary = "；".join(_key_points(text, limit=2)) or truncate(text, 160)
        quote = truncate(text, 220)
        cards.append(
            KnowledgeCard(
                id=stable_id(doc_id, "card", str(chunk.ordinal)),
                doc_id=doc_id,
                title=_title(chunk),
                summary=truncate(summary, 260),
                key_points=_key_points(text),
                source=SourceSpan(page=chunk.page, bbox=chunk.bbox, quote=quote),
                tags=_tags(text),
                kind=_kind(text),  # type: ignore[arg-type]
            )
        )
        if len(cards) >= max_cards:
            break
    return cards
