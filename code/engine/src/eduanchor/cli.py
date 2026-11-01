from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import get_settings, package_data_dir
from .evaluation import EvaluationRunner, export_latex, load_dataset, write_json
from .pipeline import EduAnchorEngine


def _data_file(name: str) -> Path:
    return package_data_dir() / name


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _first_doc(engine: EduAnchorEngine) -> str:
    documents = engine.list_documents()
    if not documents:
        raise SystemExit("没有教材，请先运行：uv run eduanchor seed")
    return documents[0].id


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="eduanchor", description="EduAnchor local engine")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="show engine and data directory status")
    sub.add_parser("serve", help="run the stdio JSON-RPC server")
    sub.add_parser("list", help="list imported textbooks")

    seed = sub.add_parser("seed", help="import the bundled sample textbook")
    seed.add_argument("--reset", action="store_true")
    seed.add_argument("--textbook", choices=["ml", "stats", "all"], default="ml")

    imp = sub.add_parser("import", help="import a PDF/Markdown/text textbook")
    imp.add_argument("path")
    imp.add_argument("--title")

    cards = sub.add_parser("cards", help="list knowledge cards")
    cards.add_argument("doc_id", nargs="?")

    ask = sub.add_parser("ask", help="ask a textbook-grounded question")
    ask.add_argument("question")
    ask.add_argument("--doc-id")
    ask.add_argument("--mode", choices=["explain", "socratic"], default="explain")
    ask.add_argument("--condition", default="c5")

    model = sub.add_parser("model", help="show, set, or test the model provider")
    model.add_argument("action", choices=["show", "set", "test"], nargs="?", default="show")
    model.add_argument("--provider")
    model.add_argument("--base-url")
    model.add_argument("--name", dest="model_name")
    model.add_argument("--api-key")
    model.add_argument("--temperature", type=float)
    model.add_argument("--max-tokens", type=int)

    evaluation = sub.add_parser("eval", help="run the textbook QA evaluation")
    evaluation.add_argument("--dataset", default=str(_data_file("qa_dataset.jsonl")))
    evaluation.add_argument("--doc-id")
    evaluation.add_argument("--condition", default="c5")
    evaluation.add_argument("--all-conditions", action="store_true")
    evaluation.add_argument("--conditions", help="comma-separated condition names, e.g. c3,c5")
    evaluation.add_argument("--mode", choices=["explain", "socratic"], default="explain")
    evaluation.add_argument("--out")
    evaluation.add_argument("--latex-dir")

    args = parser.parse_args()
    settings = get_settings()

    if args.command == "doctor":
        engine = EduAnchorEngine(settings)
        _print(engine.status())
        _print({"data_dir_exists": settings.data_dir.exists()})
        return

    if args.command == "serve":
        from .rpc import main as serve_main

        serve_main()
        return

    engine = EduAnchorEngine(settings)

    if args.command == "seed":
        if args.reset:
            for document in engine.list_documents():
                engine.delete_document(document.id)
            for path in settings.index_dir.glob("*.npz"):
                path.unlink()
        seeded = []
        if args.textbook in {"ml", "all"}:
            seeded.append(engine.import_sample().model_dump())
        if args.textbook in {"stats", "all"}:
            stats = package_data_dir() / "sample_textbook2.md"
            seeded.append(
                engine.import_markdown(stats, title="概率统计与模型评估示例教材").model_dump()
            )
        _print({"seeded": seeded})
        return

    if args.command == "list":
        _print([document.model_dump() for document in engine.list_documents()])
        return

    if args.command == "import":
        document = engine.import_file(args.path, title=args.title)
        _print(document.model_dump())
        return

    if args.command == "model":
        if args.action == "show":
            _print(engine.get_model_config())
            return
        payload = {
            "provider": args.provider,
            "base_url": args.base_url,
            "model": args.model_name,
            "api_key": args.api_key,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        if args.action == "test":
            _print(engine.test_model_config(payload))
            return
        _print(engine.set_model_config(payload))
        return

    if args.command == "cards":
        doc_id = args.doc_id or _first_doc(engine)
        _print([card.model_dump() for card in engine.get_cards(doc_id)])
        return

    if args.command == "ask":
        doc_id = args.doc_id or _first_doc(engine)
        answer = engine.ask(doc_id, args.question, mode=args.mode, condition=args.condition)
        _print(answer.model_dump())
        return

    if args.command == "eval":
        dataset = load_dataset(args.dataset)
        doc_id = args.doc_id or _first_doc(engine)
        runner = EvaluationRunner(engine)
        if args.conditions:
            names = [name.strip().lower() for name in args.conditions.split(",") if name.strip()]
            results = runner.run_conditions(
                dataset, conditions=names, mode=args.mode, default_doc_id=doc_id
            )
        elif args.all_conditions:
            results = runner.run_conditions(dataset, mode=args.mode, default_doc_id=doc_id)
        else:
            results = {
                args.condition: runner.run(
                    dataset,
                    condition=args.condition,
                    mode=args.mode,
                    default_doc_id=doc_id,
                )
            }
        if args.out:
            write_json(results, args.out)
        if args.latex_dir:
            export_latex(results, args.latex_dir)
        summary = {name: payload["metrics"] for name, payload in results.items()}
        _print({"summary": summary, "n": len(dataset)})
        return

    parser.error("unknown command")


if __name__ == "__main__":
    main()
