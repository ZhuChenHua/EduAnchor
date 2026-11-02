from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code" / "engine" / "src"))

from eduanchor.config import Settings
from eduanchor.evaluation import (
    _auprc,
    _auroc,
    _is_relevant,
    _token_f1,
    load_dataset,
)
from eduanchor.pipeline import EduAnchorEngine
from eduanchor.utils import bootstrap_ci, cosine, tokenize

DATA = ROOT / "code" / "engine" / "src" / "eduanchor" / "data"
TMP = ROOT / ".tmp"
OUT = ROOT / "ICEIT2027" / "experiments"

SOURCES = {
    "A": {
        "dataset": DATA / "qa_dataset.jsonl",
        "book": "A",
        "results": {
            "c1": ROOT / "code" / "results-main0.json",
            "c2": ROOT / "code" / "results-main0.json",
            "c2b": ROOT / "code" / "results-main0.json",
            "c2c": ROOT / "code" / "results-main0.json",
            "c3": ROOT / "code" / "results-main0.json",
            "c4": ROOT / "code" / "results-main0.json",
            "c5": ROOT / "code" / "results-main0.json",
            "c6": TMP / "c6c7-a" / "results.json",
            "c7": TMP / "c7a-focused" / "results.json",
        },
    },
    "B": {
        "dataset": DATA / "qa_dataset2.jsonl",
        "book": "B",
        "results": {
            "c1": ROOT / "code" / "results-cross0.json",
            "c3": ROOT / "code" / "results-cross0.json",
            "c5": ROOT / "code" / "results-cross0.json",
            "c6": TMP / "c6c7-b" / "results.json",
            "c7": TMP / "c7b-focused" / "results.json",
        },
    },
}

LABELS = {
    "c1": "C1 bare",
    "c2": "C2 dense",
    "c2b": "C2b BM25",
    "c2c": "C2c hybrid-no-rerank",
    "c3": "C3 hybrid+prompt",
    "c4": "C4 coverage+verifier",
    "c5": "C5 full",
    "c6": "C6 verification-first",
    "c7": "C7 source-near",
}


def sign_test(diffs: list[float]) -> dict:
    nz = [value for value in diffs if not math.isclose(value, 0.0)]
    wins = sum(value > 0 for value in nz)
    n = len(nz)
    if n == 0:
        return {"n": 0, "wins": 0, "p": 1.0}
    tail = sum(math.comb(n, index) for index in range(min(wins, n - wins) + 1)) / 2**n
    return {"n": n, "wins": wins, "p": min(1.0, 2.0 * tail)}


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, index) for index in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2.0 * tail)


def bootstrap_diff_ci(left: list[float], right: list[float]) -> list[float]:
    left_array = np.asarray(left, dtype=float)
    right_array = np.asarray(right, dtype=float)
    if left_array.size == 0 or right_array.size == 0:
        return [0.0, 0.0]
    rng = np.random.default_rng(20270101)
    values = []
    for _ in range(10000):
        index = rng.integers(0, left_array.size, left_array.size)
        values.append(float(np.mean(left_array[index] - right_array[index])))
    low, high = np.quantile(values, [0.025, 0.975])
    return [round(float(low), 4), round(float(high), 4)]


def records_for(path: Path, condition: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload[condition]["records"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    engine = EduAnchorEngine(Settings(data_dir=TMP / "final-analysis", embed_backend="hash"))
    for document in engine.list_documents():
        engine.delete_document(document.id)
    docs = {
        "A": engine.import_markdown(DATA / "sample_textbook.md", title="A"),
        "B": engine.import_markdown(DATA / "sample_textbook2.md", title="B"),
    }
    books: dict[str, dict] = {}
    all_records: dict[str, dict[str, dict]] = {}
    retrieval_cache: dict[tuple[str, str], list] = {}
    vocab_cache: dict[str, set[str]] = {}

    for book, source in SOURCES.items():
        doc = docs[book]
        dataset = {record.question: record for record in load_dataset(source["dataset"])}
        chunks = engine.store.list_chunks(doc.id)
        if book not in vocab_cache:
            vocab_cache[book] = set().union(*(set(tokenize(chunk.text)) for chunk in chunks))
        book_records: dict[str, list[dict]] = {}
        for condition, path in source["results"].items():
            raw_rows = records_for(path, condition)
            enriched = []
            for raw in raw_rows:
                record = dataset[raw["question"]]
                key = (book, raw["question"])
                if key not in retrieval_cache:
                    retrieval_cache[key] = engine.retriever.retrieve(
                        doc.id, raw["question"], top_k=6
                    )
                candidates = retrieval_cache[key]
                relevance = [_is_relevant(record.gold_quote or "", item.chunk.text) for item in candidates]
                hit1 = float(bool(relevance[:1] and relevance[0]))
                hit4 = float(any(relevance[:4]))
                rr = next((1.0 / rank for rank, rel in enumerate(relevance, 1) if rel), 0.0)
                dcg = sum(float(rel) / math.log2(rank + 1) for rank, rel in enumerate(relevance, 1))
                ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, sum(relevance) + 1))
                refused = bool(raw["refused"])
                answer = raw["answer"]
                support = 0.0 if refused else float(raw["support_rate"])
                gold_f1 = 0.0
                if record.scope == "in" and record.gold_answer and not refused:
                    gold_f1 = _token_f1(answer, record.gold_answer)
                relevance_score = 0.0
                if record.scope == "in" and record.gold_answer and not refused:
                    gold = engine.embedder.encode([record.gold_answer])[0]
                    pred = engine.embedder.encode([answer])[0]
                    relevance_score = max(0.0, cosine(gold, pred))
                enriched.append(
                    {
                        **raw,
                        "question": record.question,
                        "scope": record.scope,
                        "label": (
                            "in"
                            if record.scope == "in"
                            else (record.annotations[0].get("type") if record.annotations else "clear")
                        ),
                        "support_rate": support,
                        "gold_token_f1": gold_f1,
                        "relevance": relevance_score,
                        "citation_rate": engine.verifier.citation_rate(answer),
                        "claims": len(engine.verifier.claims(answer)),
                        "answer_chars": len(answer),
                        "retrieval_hit1": hit1,
                        "retrieval_hit4": hit4,
                        "retrieval_rr": rr,
                        "retrieval_ndcg": dcg / ideal if ideal else 0.0,
                        "oov": len(set(tokenize(record.question)) - vocab_cache[book])
                        / max(len(set(tokenize(record.question))), 1),
                        "evidence_coverage": len(
                            set(tokenize(record.question))
                            & set().union(*(set(tokenize(item.chunk.text)) for item in candidates))
                        )
                        / max(len(set(tokenize(record.question))), 1),
                    }
                )
            book_records[condition] = enriched
        all_records[book] = book_records
        books[book] = summarize(book_records, doc.id)

    common = sorted(set.intersection(*(set(all_records[book]) for book in all_records)))
    pooled_records = {
        condition: [row for book in ("A", "B") for row in all_records[book][condition]]
        for condition in common
    }
    pooled = summarize(pooled_records, "pooled")

    paired = {}
    for baseline in ("c3", "c5", "c6"):
        left: list[float] = []
        right: list[float] = []
        for book in ("A", "B"):
            left.extend(
                row["support_rate"] for row in all_records[book]["c7"] if row["scope"] == "in"
            )
            right.extend(
                row["support_rate"]
                for row in all_records[book][baseline]
                if row["scope"] == "in"
            )
        paired[f"c7_vs_{baseline}"] = {
            "mean_diff": round(float(np.mean(np.asarray(left) - np.asarray(right))), 4),
            "ci": bootstrap_diff_ci(left, right),
            "sign": sign_test([a - b for a, b in zip(left, right)]),
        }
    border = {}
    for baseline in ("c3", "c5"):
        b = c = 0
        for book in ("A", "B"):
            for left, right in zip(all_records[book]["c7"], all_records[book][baseline]):
                if left["label"] != "borderline":
                    continue
                if left["refused"] and not right["refused"]:
                    b += 1
                elif right["refused"] and not left["refused"]:
                    c += 1
        border[f"c7_vs_{baseline}"] = {"c7_only_refused": b, "baseline_only_refused": c, "p": mcnemar(b, c)}

    risk = {}
    for label, rows in (("A", all_records["A"]["c7"]), ("B", all_records["B"]["c7"]), ("pooled", pooled_records["c7"])):
        curve = []
        for threshold in np.arange(0.0, 0.301, 0.01):
            answered = [
                row for row in rows if row["scope"] == "in" and row["coverage"] >= threshold
            ]
            out_refused = sum(
                1
                for row in rows
                if row["scope"] == "out" and (row["refused"] or row["coverage"] < threshold)
            )
            curve.append(
                {
                    "threshold": round(float(threshold), 2),
                    "answer_rate_in": round(len(answered) / max(sum(row["scope"] == "in" for row in rows), 1), 4),
                    "risk": round(
                        float(np.mean([1.0 - row["support_rate"] for row in answered]))
                        if answered
                        else 0.0,
                        4,
                    ),
                    "boundary_refusal": round(
                        out_refused / max(sum(row["scope"] == "out" for row in rows), 1), 4
                    ),
                }
            )
        risk[label] = curve

    payload = {
        "books": books,
        "pooled": pooled,
        "paired": paired,
        "border": border,
        "risk_coverage": risk,
    }
    (OUT / "final_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def summarize(records: dict[str, list[dict]], doc_id: str) -> dict:
    summary: dict[str, dict] = {}
    for condition, rows in records.items():
        in_rows = [row for row in rows if row["scope"] == "in"]
        answered = [row for row in in_rows if not row["refused"]]
        out_rows = [row for row in rows if row["scope"] == "out"]
        border = [row for row in out_rows if row["label"] == "borderline"]
        clear = [row for row in out_rows if row["label"] != "borderline"]
        support = [row["support_rate"] for row in in_rows]
        summary[condition] = {
            "n_in": len(in_rows),
            "n_out": len(out_rows),
            "n_answered_in": len(answered),
            "n_refused_in": len(in_rows) - len(answered),
            "support": round(float(np.mean(support)) if support else 0.0, 4),
            "support_ci": bootstrap_ci(support),
            "support_answered": round(
                float(np.mean([row["support_rate"] for row in answered])) if answered else 0.0, 4
            ),
            "false_refusal": round((len(in_rows) - len(answered)) / max(len(in_rows), 1), 4),
            "borderline_refusal": round(
                sum(row["refused"] for row in border) / max(len(border), 1), 4
            ),
            "clear_refusal": round(sum(row["refused"] for row in clear) / max(len(clear), 1), 4),
            "gold_f1": round(float(np.mean([row["gold_token_f1"] for row in answered])) if answered else 0.0, 4),
            "citation": round(float(np.mean([row["citation_rate"] for row in answered])) if answered else 0.0, 4),
            "claims": round(float(np.mean([row["claims"] for row in answered])) if answered else 0.0, 4),
            "answer_chars": round(float(np.mean([row["answer_chars"] for row in answered])) if answered else 0.0, 4),
            "hit1": round(float(np.mean([row["retrieval_hit1"] for row in in_rows])), 4),
            "hit4": round(float(np.mean([row["retrieval_hit4"] for row in in_rows])), 4),
            "mrr": round(float(np.mean([row["retrieval_rr"] for row in in_rows])), 4),
            "ndcg": round(float(np.mean([row["retrieval_ndcg"] for row in in_rows])), 4),
            "coverage_auroc": round(_auroc([-row["coverage"] for row in rows], [1 if row["scope"] == "out" else 0 for row in rows]), 4),
            "coverage_auprc": round(_auprc([-row["coverage"] for row in rows], [1 if row["scope"] == "out" else 0 for row in rows]), 4),
            "latency_ms": round(float(np.mean([row["latency_ms"] for row in rows])), 1),
            "doc_id": doc_id,
        }
    return summary


if __name__ == "__main__":
    main()
