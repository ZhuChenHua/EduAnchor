from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from .pipeline import EduAnchorEngine
from .schemas import EvalMetrics, EvalRecord
from .utils import bootstrap_ci, cosine


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


def _condition_table(rows: list[dict], caption: str, label: str) -> str:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"Condition & Support$\uparrow$ & Hallucination$\downarrow$ & False refusal$\downarrow$ & Out-of-scope refusal$\uparrow$ & Latency (ms)$\downarrow$ \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{row['condition']} & {row['support_rate']:.3f} & {row['hallucination_rate']:.3f} & "
            f"{row['false_refusal_rate']:.3f} & {row['refusal_accuracy']:.3f} & "
            f"{row['mean_latency_ms']:.0f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


class EvaluationRunner:
    def __init__(self, engine: EduAnchorEngine) -> None:
        self.engine = engine

    def run(
        self,
        records: list[EvalRecord],
        condition: str = "c5",
        mode: str = "explain",
        default_doc_id: str | None = None,
    ) -> dict:
        rows: list[dict] = []
        in_support: list[float] = []
        in_refused = 0
        in_total = 0
        out_refused = 0
        out_total = 0
        latencies: list[float] = []
        relevance: list[float] = []

        for record in records:
            doc_id = record.doc_id or default_doc_id
            if not doc_id:
                raise ValueError("evaluation record is missing doc_id")
            answer = self.engine.ask(doc_id, record.question, mode=mode, condition=condition)
            latencies.append(answer.latency_ms)
            if record.scope == "in":
                in_total += 1
                in_refused += int(answer.refused)
                in_support.append(0.0 if answer.refused else answer.support_rate)
                if record.gold_answer:
                    gold = self.engine.embedder.encode([record.gold_answer])[0]
                    pred = self.engine.embedder.encode([answer.answer])[0]
                    relevance.append(max(0.0, cosine(gold, pred)))
            else:
                out_total += 1
                out_refused += int(answer.refused)
            rows.append(
                {
                    "question": record.question,
                    "scope": record.scope,
                    "answer": answer.answer,
                    "refused": answer.refused,
                    "support_rate": answer.support_rate,
                    "coverage": answer.coverage,
                    "latency_ms": answer.latency_ms,
                    "citations": [citation.page for citation in answer.citations],
                    "session_id": answer.session_id,
                }
            )

        support_mean = float(np.mean(in_support)) if in_support else 0.0
        metrics = EvalMetrics(
            n_in=in_total,
            n_out=out_total,
            support_rate=support_mean,
            hallucination_rate=1.0 - support_mean,
            false_refusal_rate=in_refused / max(in_total, 1),
            refusal_accuracy=out_refused / max(out_total, 1),
            answer_rate_out=1.0 - out_refused / max(out_total, 1),
            relevance=float(np.mean(relevance)) if relevance else 0.0,
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
        conditions: Iterable[str] = ("c1", "c2", "c3", "c4", "c5"),
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
        "Ablation on the held-out textbook QA set (C1: bare Qwen; C2: dense RAG; "
        "C3: hybrid+rerank; C4: multi-agent; C5: full system with anchor constraints).",
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
