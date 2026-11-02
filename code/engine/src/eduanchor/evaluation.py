from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from .pipeline import EduAnchorEngine
from .schemas import EvalMetrics, EvalRecord
from .utils import bootstrap_ci, cosine, overlap_score, tokenize


def load_dataset(path: str | Path) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        records.append(EvalRecord.model_validate_json(line))
    return records


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in text)


CONDITION_LABELS = {
    "C1": "C1 bare Qwen3-8B",
    "C2": "C2 dense RAG",
    "C2B": "C2b BM25 only",
    "C2C": "C2c hybrid, no rerank",
    "C3": "C3 hybrid + refusal prompt",
    "C4": "C4 coverage + verifier",
    "C5": "C5 full EduAnchor",
    "C6": "C6 verification-first",
    "C7": "C7 source-near prompt",
}


def _condition_table(rows: list[dict], caption: str, label: str) -> str:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{1.8pt}",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\begin{tabular}{@{}lcccccc@{}}",
        r"\toprule",
        r"Condition & Support$\uparrow$ & Support$_{\mathrm{ans}}\uparrow$ & Halluc.$\downarrow$ & False ref.$\downarrow$ & Out clear$\uparrow$ & Out border$\uparrow$ \\",
        r"\midrule",
    ]
    for row in rows:
        label_text = CONDITION_LABELS.get(row["condition"], row["condition"])
        lines.append(
            f"{label_text} & {100 * row['support_rate']:.1f} & "
            f"{100 * row.get('support_answered', row['support_rate']):.1f} & "
            f"{100 * row['hallucination_rate']:.1f} & "
            f"{100 * row['false_refusal_rate']:.1f} & "
            f"{100 * row['clear_refusal_accuracy']:.1f} & "
            f"{100 * row['borderline_refusal_accuracy']:.1f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _token_f1(prediction: str, gold: str) -> float:
    pred_tokens = tokenize(prediction)
    gold_tokens = tokenize(gold)
    if not pred_tokens or not gold_tokens:
        return 0.0
    pred_count: dict[str, int] = {}
    gold_count: dict[str, int] = {}
    for token in pred_tokens:
        pred_count[token] = pred_count.get(token, 0) + 1
    for token in gold_tokens:
        gold_count[token] = gold_count.get(token, 0) + 1
    overlap = sum(min(count, gold_count.get(token, 0)) for token, count in pred_count.items())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def _is_relevant(gold: str, text: str) -> bool:
    if not gold or not text:
        return False
    if _normalized(gold) in _normalized(text):
        return True
    return overlap_score(gold, text) >= 0.55


def _retrieval_metrics(gold: str, candidates: list) -> dict[str, float]:
    relevance = [_is_relevant(gold, candidate.chunk.text) for candidate in candidates]
    hit1 = float(bool(relevance[:1] and relevance[0]))
    hit4 = float(any(relevance[:4]))
    reciprocal_rank = 0.0
    for rank, relevant in enumerate(relevance, start=1):
        if relevant:
            reciprocal_rank = 1.0 / rank
            break
    dcg = sum(
        float(relevant) / math.log2(rank + 1)
        for rank, relevant in enumerate(relevance, start=1)
    )
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, sum(relevance) + 1))
    return {
        "hit1": hit1,
        "hit4": hit4,
        "rr": reciprocal_rank,
        "ndcg": dcg / ideal if ideal else 0.0,
    }


def _auroc(scores: list[float], labels: list[int]) -> float:
    positive = [score for score, label in zip(scores, labels) if label == 1]
    negative = [score for score, label in zip(scores, labels) if label == 0]
    if not positive or not negative:
        return 0.5
    wins = sum(
        (p > n) + 0.5 * (p == n)
        for p in positive
        for n in negative
    )
    return float(wins / (len(positive) * len(negative)))


def _auprc(scores: list[float], labels: list[int]) -> float:
    positives = sum(labels)
    if positives == 0:
        return 0.0
    order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    true_positive = 0
    false_positive = 0
    previous_recall = 0.0
    average_precision = 0.0
    for index in order:
        if labels[index] == 1:
            true_positive += 1
        else:
            false_positive += 1
        recall = true_positive / positives
        precision = true_positive / (true_positive + false_positive)
        average_precision += (recall - previous_recall) * precision
        previous_recall = recall
    return float(average_precision)


class EvaluationRunner:
    def __init__(self, engine: EduAnchorEngine) -> None:
        self.engine = engine
        self._vocab: dict[str, set[str]] = {}

    def _document_vocab(self, doc_id: str) -> set[str]:
        if doc_id not in self._vocab:
            vocabulary: set[str] = set()
            for chunk in self.engine.store.list_chunks(doc_id):
                vocabulary.update(tokenize(chunk.text))
            self._vocab[doc_id] = vocabulary
        return self._vocab[doc_id]

    def run(
        self,
        records: list[EvalRecord],
        condition: str = "c5",
        mode: str = "explain",
        default_doc_id: str | None = None,
    ) -> dict:
        rows: list[dict] = []
        in_support: list[float] = []
        answered_support: list[float] = []
        gold_f1: list[float] = []
        citation_rates: list[float] = []
        claim_counts: list[float] = []
        answer_chars: list[float] = []
        retrieval_hit1: list[float] = []
        retrieval_hit4: list[float] = []
        retrieval_rr: list[float] = []
        retrieval_ndcg: list[float] = []
        coverage_scores: list[float] = []
        coverage_labels: list[int] = []
        in_refused = 0
        in_total = 0
        in_answered = 0
        out_refused = 0
        out_total = 0
        out_clear = 0
        out_clear_refused = 0
        out_borderline = 0
        out_borderline_refused = 0
        latencies: list[float] = []
        relevance: list[float] = []

        for record in records:
            doc_id = record.doc_id or default_doc_id
            if record.doc_id and self.engine.store.get_document(record.doc_id) is None:
                doc_id = default_doc_id
            if not doc_id:
                raise ValueError("evaluation record is missing doc_id")
            answer = self.engine.ask(doc_id, record.question, mode=mode, condition=condition)
            latencies.append(answer.latency_ms)
            candidates = answer.evidence
            if not candidates:
                candidates = self.engine.retriever.retrieve(
                    doc_id,
                    record.question,
                    top_k=self.engine.settings.top_k,
                )
            coverage_scores.append(answer.coverage)
            coverage_labels.append(1 if record.scope == "out" else 0)
            features: dict[str, float] = {}
            if record.scope == "in" and record.gold_quote:
                retrieval = _retrieval_metrics(record.gold_quote, candidates)
                retrieval_hit1.append(retrieval["hit1"])
                retrieval_hit4.append(retrieval["hit4"])
                retrieval_rr.append(retrieval["rr"])
                retrieval_ndcg.append(retrieval["ndcg"])
            else:
                retrieval = {"hit1": 0.0, "hit4": 0.0, "rr": 0.0, "ndcg": 0.0}
            vocabulary = self._document_vocab(doc_id)
            query_tokens = set(tokenize(record.question))
            evidence_tokens: set[str] = set()
            for candidate in candidates:
                evidence_tokens.update(tokenize(candidate.chunk.text))
            features["oov"] = len(query_tokens - vocabulary) / max(len(query_tokens), 1)
            features["evidence_coverage"] = len(query_tokens & evidence_tokens) / max(
                len(query_tokens), 1
            )
            if record.scope == "in":
                in_total += 1
                in_refused += int(answer.refused)
                in_support.append(0.0 if answer.refused else answer.support_rate)
                if record.gold_answer:
                    f1 = 0.0 if answer.refused else _token_f1(answer.answer, record.gold_answer)
                    gold_f1.append(f1)
                    if not answer.refused:
                        gold = self.engine.embedder.encode([record.gold_answer])[0]
                        pred = self.engine.embedder.encode([answer.answer])[0]
                        relevance.append(max(0.0, cosine(gold, pred)))
                if not answer.refused:
                    in_answered += 1
                    answered_support.append(answer.support_rate)
                    citation_rates.append(self.engine.verifier.citation_rate(answer.answer))
                    claim_counts.append(float(len(self.engine.verifier.claims(answer.answer))))
                    answer_chars.append(float(len(answer.answer)))
            else:
                out_total += 1
                out_refused += int(answer.refused)
                labels = {item.get("type") for item in record.annotations}
                if "borderline" in labels:
                    out_borderline += 1
                    out_borderline_refused += int(answer.refused)
                else:
                    out_clear += 1
                    out_clear_refused += int(answer.refused)
            rows.append(
                {
                    "question": record.question,
                    "scope": record.scope,
                    "answer": answer.answer,
                    "refused": answer.refused,
                    "support_rate": answer.support_rate,
                    "coverage": answer.coverage,
                    "oov": features["oov"],
                    "evidence_coverage": features["evidence_coverage"],
                    "retrieval_hit1": retrieval["hit1"],
                    "retrieval_hit4": retrieval["hit4"],
                    "retrieval_rr": retrieval["rr"],
                    "retrieval_ndcg": retrieval["ndcg"],
                    "gold_token_f1": (
                        0.0
                        if record.scope != "in" or not record.gold_answer or answer.refused
                        else _token_f1(answer.answer, record.gold_answer)
                    ),
                    "citation_rate": self.engine.verifier.citation_rate(answer.answer),
                    "latency_ms": answer.latency_ms,
                    "citations": [citation.page for citation in answer.citations],
                    "session_id": answer.session_id,
                    "doc_id": doc_id,
                }
            )

        support_mean = float(np.mean(in_support)) if in_support else 0.0
        metrics = EvalMetrics(
            n_in=in_total,
            n_out=out_total,
            n_answered_in=in_answered,
            n_refused_in=in_refused,
            support_rate=support_mean,
            support_answered=float(np.mean(answered_support)) if answered_support else 0.0,
            hallucination_rate=1.0 - support_mean,
            false_refusal_rate=in_refused / max(in_total, 1),
            refusal_accuracy=out_refused / max(out_total, 1),
            clear_refusal_accuracy=out_clear_refused / max(out_clear, 1),
            borderline_refusal_accuracy=out_borderline_refused / max(out_borderline, 1),
            answer_rate_out=1.0 - out_refused / max(out_total, 1),
            relevance=float(np.mean(relevance)) if relevance else 0.0,
            gold_token_f1=float(np.mean(gold_f1)) if gold_f1 else 0.0,
            citation_rate=float(np.mean(citation_rates)) if citation_rates else 0.0,
            mean_claims=float(np.mean(claim_counts)) if claim_counts else 0.0,
            mean_answer_chars=float(np.mean(answer_chars)) if answer_chars else 0.0,
            retrieval_hit1=float(np.mean(retrieval_hit1)) if retrieval_hit1 else 0.0,
            retrieval_hit4=float(np.mean(retrieval_hit4)) if retrieval_hit4 else 0.0,
            retrieval_mrr=float(np.mean(retrieval_rr)) if retrieval_rr else 0.0,
            retrieval_ndcg=float(np.mean(retrieval_ndcg)) if retrieval_ndcg else 0.0,
            coverage_auroc=_auroc([-score for score in coverage_scores], coverage_labels),
            coverage_auprc=_auprc([-score for score in coverage_scores], coverage_labels),
            mean_latency_ms=float(np.mean(latencies)) if latencies else 0.0,
            support_ci=bootstrap_ci(in_support) if in_support else [0.0, 0.0],
        )
        return {
            "condition": condition,
            "metrics": metrics.model_dump(),
            "records": rows,
        }

    def run_conditions(
        self,
        records: list[EvalRecord],
        conditions: Iterable[str] = ("c1", "c2", "c2b", "c2c", "c3", "c4", "c5", "c6", "c7"),
        mode: str = "explain",
        default_doc_id: str | None = None,
    ) -> dict:
        results: dict[str, dict] = {}
        for condition in conditions:
            results[condition] = self.run(records, condition, mode, default_doc_id)
        return results


def export_latex(results: dict[str, dict], directory: str | Path) -> list[str]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for condition, payload in results.items():
        metrics = payload["metrics"]
        rows.append({"condition": condition.upper(), **metrics})
    table = _condition_table(
        rows,
        "Controlled comparison. C2/C3 use prompt-only refusal; C4 adds coverage and claim checking; C5 adds pre-gate anchoring; C6 removes the pre-gate; C7 adds the source-near, citation-strict prompt.",
        "tab:main-results",
    )
    main_path = directory / "main_results.tex"
    main_path.write_text(table, encoding="utf-8")

    ablation = _condition_table(rows[1:] if len(rows) > 1 else rows, "Component ablation.", "tab:ablation")
    ablation_path = directory / "ablation.tex"
    ablation_path.write_text(ablation, encoding="utf-8")
    return [str(main_path), str(ablation_path)]


def write_json(results: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
