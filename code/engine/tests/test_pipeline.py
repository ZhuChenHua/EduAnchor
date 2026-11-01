from __future__ import annotations

from pathlib import Path

from eduanchor.config import Settings
from eduanchor.evaluation import EvaluationRunner, load_dataset
from eduanchor.pipeline import EduAnchorEngine

DATA = Path(__file__).resolve().parents[1] / "src" / "eduanchor" / "data"


def make_engine(tmp_path: Path) -> EduAnchorEngine:
    settings = Settings(data_dir=tmp_path, embed_backend="hash")
    engine = EduAnchorEngine(settings)
    engine.import_markdown(DATA / "sample_textbook.md", title="机器学习基础")
    return engine


def test_import_creates_documents_cards_and_chunks(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    documents = engine.list_documents()
    assert len(documents) == 1
    assert documents[0].chunk_count > 5
    cards = engine.get_cards(documents[0].id)
    assert len(cards) > 5
    assert all(card.source.quote for card in cards)
    assert any(card.kind == "definition" for card in cards)


def test_in_scope_answer_is_grounded(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    doc_id = engine.list_documents()[0].id
    answer = engine.ask(doc_id, "什么是机器学习？")
    assert not answer.refused
    assert answer.citations
    assert answer.citations[0].page >= 1
    assert answer.support_rate > 0.5
    assert "[1]" in answer.answer


def test_out_of_scope_question_is_refused(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    doc_id = engine.list_documents()[0].id
    answer = engine.ask(doc_id, "如何治疗糖尿病？")
    assert answer.refused
    assert answer.reason


def test_socratic_mode(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    doc_id = engine.list_documents()[0].id
    answer = engine.ask(doc_id, "什么是过拟合？", mode="socratic")
    assert "思考" in answer.answer or "？" in answer.answer


def test_ablation_conditions_run(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    doc_id = engine.list_documents()[0].id
    for condition in ("c2", "c3", "c4", "c5"):
        answer = engine.ask(doc_id, "什么是交叉验证？", condition=condition)
        assert answer.condition == condition


def test_evaluation_pipeline(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    doc_id = engine.list_documents()[0].id
    records = load_dataset(DATA / "qa_dataset.jsonl")[:5]
    results = EvaluationRunner(engine).run(records, condition="c5", default_doc_id=doc_id)
    metrics = results["metrics"]
    assert metrics["n_in"] + metrics["n_out"] == 5
    assert 0.0 <= metrics["support_rate"] <= 1.0
    assert 0.0 <= metrics["refusal_accuracy"] <= 1.0
