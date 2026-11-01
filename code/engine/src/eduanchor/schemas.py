from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceSpan(BaseModel):
    page: int = 1
    bbox: list[float] | None = None
    quote: str = ""


class Document(BaseModel):
    id: str
    title: str
    path: str | None = None
    created_at: str
    pages: int = 1
    chunk_count: int = 0
    card_count: int = 0
    embed_backend: str = "hash-512"


class Chunk(BaseModel):
    id: str
    doc_id: str
    ordinal: int
    text: str
    page: int = 1
    bbox: list[float] | None = None
    heading: str | None = None


class KnowledgeCard(BaseModel):
    id: str
    doc_id: str
    title: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    source: SourceSpan
    tags: list[str] = Field(default_factory=list)
    kind: Literal["definition", "principle", "procedure", "example", "concept"] = "concept"


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float = 0.0
    bm25: float = 0.0
    dense: float = 0.0
    rerank: float = 0.0


class TraceStep(BaseModel):
    agent: str
    action: str
    detail: str = ""
    elapsed_ms: float = 0.0


class Citation(BaseModel):
    chunk_id: str
    page: int
    quote: str
    bbox: list[float] | None = None
    score: float = 0.0


class Answer(BaseModel):
    question: str
    doc_id: str
    created_at: str = ""
    mode: Literal["explain", "socratic"] = "explain"
    answer: str
    refused: bool = False
    reason: str = ""
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[RetrievedChunk] = Field(default_factory=list)
    support_rate: float = 0.0
    coverage: float = 0.0
    condition: str = "c5"
    trace: list[TraceStep] = Field(default_factory=list)
    latency_ms: float = 0.0
    session_id: str | None = None
    llm: str = "extractive"


class EvalRecord(BaseModel):
    question: str
    scope: Literal["in", "out"] = "in"
    gold_answer: str | None = None
    gold_quote: str | None = None
    doc_id: str | None = None
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class EvalMetrics(BaseModel):
    n_in: int = 0
    n_out: int = 0
    support_rate: float = 0.0
    hallucination_rate: float = 0.0
    false_refusal_rate: float = 0.0
    refusal_accuracy: float = 0.0
    clear_refusal_accuracy: float = 0.0
    borderline_refusal_accuracy: float = 0.0
    answer_rate_out: float = 0.0
    relevance: float = 0.0
    mean_latency_ms: float = 0.0
    support_ci: list[float] = Field(default_factory=list)
