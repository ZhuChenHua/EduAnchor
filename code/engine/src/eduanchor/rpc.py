from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from .config import get_settings, package_data_dir
from .evaluation import EvaluationRunner, export_latex, load_dataset, write_json
from .pipeline import EduAnchorEngine


def _dispatch(engine: EduAnchorEngine, method: str, params: dict[str, Any]) -> Any:
    if method == "system.ping":
        return {"pong": True}
    if method == "system.status":
        return engine.status()
    if method == "settings.getModel":
        return engine.get_model_config()
    if method == "settings.setModel":
        return engine.set_model_config(params)
    if method == "settings.testModel":
        return engine.test_model_config(params)
    if method == "library.list":
        return [document.model_dump() for document in engine.list_documents()]
    if method == "library.importFile":
        document = engine.import_file(params["path"], title=params.get("title"))
        return document.model_dump()
    if method == "library.importText":
        document = engine.import_text(
            params.get("name", "未命名教材"), params["text"], title=params.get("title")
        )
        return document.model_dump()
    if method == "library.seedSample":
        return engine.import_sample().model_dump()
    if method == "library.delete":
        engine.delete_document(params["docId"])
        return {"deleted": params["docId"]}
    if method == "cards.list":
        return [card.model_dump() for card in engine.get_cards(params["docId"])]
    if method == "qa.ask":
        answer = engine.ask(
            params["docId"],
            params["question"],
            mode=params.get("mode", "explain"),
            condition=params.get("condition", "c5"),
        )
        return answer.model_dump()
    if method == "session.list":
        return [answer.model_dump() for answer in engine.store.list_sessions(params.get("docId"))]
    if method == "eval.run":
        dataset_path = params.get("dataset") or str(
            package_data_dir() / "qa_dataset.jsonl"
        )
        dataset = load_dataset(dataset_path)
        default_doc = params.get("docId")
        if not default_doc:
            documents = engine.list_documents()
            if not documents:
                raise ValueError("no document available; import a textbook first")
            default_doc = documents[0].id
        runner = EvaluationRunner(engine)
        if params.get("allConditions", True):
            results = runner.run_conditions(
                dataset, mode=params.get("mode", "explain"), default_doc_id=default_doc
            )
        else:
            condition = params.get("condition", "c5")
            results = {
                condition: runner.run(
                    dataset,
                    condition=condition,
                    mode=params.get("mode", "explain"),
                    default_doc_id=default_doc,
                )
            }
        if params.get("out"):
            write_json(results, params["out"])
        latex_files: list[str] = []
        if params.get("latexDir"):
            latex_files = export_latex(results, params["latexDir"])
        return {
            "results": results,
            "latex": latex_files,
            "n": len(dataset),
        }
    raise ValueError(f"unknown method: {method}")


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    engine = EduAnchorEngine(get_settings())
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params") or {}
            result = _dispatch(engine, method, params)
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32000, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
