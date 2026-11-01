from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .agents import Interpreter, Verifier
from .cards import extract_cards
from .chunker import chunk_blocks
from .config import Settings, get_settings, package_data_dir
from .embeddings import Embedder, get_embedder
from .llm import LLM, build_llm, test_model_config
from .model_config import PROVIDERS, ModelConfig
from .pdf_parser import Block, parse_markdown, parse_pdf, parse_plain_text
from .retriever import Retriever
from .schemas import Answer, Citation, Document, TraceStep
from .store import Store
from .utils import now_iso, stable_id, truncate


@dataclass(slots=True)
class Conditions:
    name: str
    retrieval: bool = True
    bm25: bool = True
    dense: bool = True
    rerank: bool = True
    agents: bool = True
    anchor: bool = True


CONDITIONS: dict[str, Conditions] = {
    "c1": Conditions("c1", retrieval=False, bm25=False, dense=False, rerank=False, agents=False, anchor=False),
    "c2": Conditions("c2", retrieval=True, bm25=False, dense=True, rerank=False, agents=False, anchor=False),
    "c2b": Conditions("c2b", retrieval=True, bm25=True, dense=False, rerank=False, agents=False, anchor=False),
    "c2c": Conditions("c2c", retrieval=True, bm25=True, dense=True, rerank=False, agents=False, anchor=False),
    "c3": Conditions("c3", retrieval=True, bm25=True, dense=True, rerank=True, agents=False, anchor=False),
    "c4": Conditions("c4", retrieval=True, bm25=True, dense=True, rerank=True, agents=True, anchor=False),
    "c5": Conditions("c5", retrieval=True, bm25=True, dense=True, rerank=True, agents=True, anchor=True),
}


class EduAnchorEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = Store(self.settings)
        self.embedder: Embedder = get_embedder(self.settings)
        self.model = ModelConfig.load(self.settings.data_dir)
        self.llm: LLM = build_llm(self.model)
        self.retriever = Retriever(self.store, self.embedder, self.settings)
        self.interpreter = Interpreter(self.llm, self.settings)
        self.verifier = Verifier(self.embedder, self.settings)

    # ------------------------------------------------------------------ import
    def _register(
        self,
        title: str,
        blocks: list[Block],
        path: str | None,
        pages: int,
    ) -> Document:
        seed = title + "::" + "".join(block.text[:20] for block in blocks[:8])
        doc_id = stable_id(seed, length=12)
        chunks = chunk_blocks(
            blocks,
            doc_id,
            target_chars=self.settings.chunk_chars,
            overlap_chars=self.settings.chunk_overlap,
        )
        cards = extract_cards(doc_id, chunks)
        document = Document(
            id=doc_id,
            title=title,
            path=path,
            created_at=now_iso(),
            pages=pages,
            chunk_count=len(chunks),
            card_count=len(cards),
            embed_backend=self.embedder.name,
        )
        self.store.save_document(document, chunks, cards)
        return document

    def import_pdf(self, path: str | Path, title: str | None = None) -> Document:
        path = Path(path)
        blocks = parse_pdf(path)
        if not blocks:
            raise ValueError("PDF 中没有可解析的文本层，可能是扫描版教材")
        pages = max(block.page for block in blocks)
        return self._register(title or path.stem, blocks, str(path), pages)

    def import_text(self, name: str, text: str, title: str | None = None) -> Document:
        page_mode = "markdown" if text.lstrip().startswith("#") else "single"
        blocks = parse_plain_text(text, page_mode=page_mode)
        if not blocks:
            raise ValueError("文本为空")
        pages = max(block.page for block in blocks)
        return self._register(title or name, blocks, None, pages)

    def import_file(self, path: str | Path, title: str | None = None) -> Document:
        path = Path(path)
        if path.suffix.lower() == ".pdf":
            return self.import_pdf(path, title=title)
        if path.suffix.lower() in {".md", ".markdown"}:
            return self.import_markdown(path, title=title)
        text = path.read_text(encoding="utf-8")
        return self.import_text(path.stem, text, title=title)

    def import_markdown(self, path: str | Path, title: str | None = None) -> Document:
        path = Path(path)
        blocks = parse_markdown(path)
        if not blocks:
            raise ValueError("Markdown 为空")
        pages = max(block.page for block in blocks)
        return self._register(title or path.stem, blocks, str(path), pages)

    def import_sample(self) -> Document:
        sample = package_data_dir() / "sample_textbook.md"
        return self.import_markdown(sample, title="机器学习基础（示例教材）")

    # ------------------------------------------------------------------ query
    def list_documents(self) -> list[Document]:
        return self.store.list_documents()

    def get_cards(self, doc_id: str) -> list:
        return self.store.list_cards(doc_id)

    def delete_document(self, doc_id: str) -> None:
        self.store.delete_document(doc_id)

    def status(self) -> dict:
        self._refresh_llm()
        return {
            "engine": "eduanchor",
            "llm": {
                "available": self.llm.available,
                "name": self.llm.name,
                **self.model.public(),
            },
            "embedder": {"name": self.embedder.name, "dim": self.embedder.dim},
            "settings": self.settings.describe(),
            "counts": self.store.count(),
        }

    def get_model_config(self) -> dict:
        return {
            "config": self.model.public(),
            "providers": PROVIDERS,
        }

    def set_model_config(self, payload: dict) -> dict:
        current = self.model.public()
        current["api_key"] = self.model.api_key
        merged = {**current, **{key: value for key, value in payload.items() if value is not None}}
        if not merged.get("api_key"):
            merged["api_key"] = self.model.api_key
        self.model = ModelConfig.from_mapping(merged)
        self.model.save(self.settings.data_dir)
        self.llm = build_llm(self.model)
        self.interpreter = Interpreter(self.llm, self.settings)
        return self.get_model_config()

    def test_model_config(self, payload: dict | None = None) -> dict:
        current = self.model.public()
        current["api_key"] = self.model.api_key
        merged = {**current, **{key: value for key, value in (payload or {}).items() if value is not None}}
        if not merged.get("api_key"):
            merged["api_key"] = self.model.api_key
        return test_model_config(ModelConfig.from_mapping(merged))

    def _refresh_llm(self) -> None:
        """Pick up a model server that became ready after engine startup."""
        if self.llm.available:
            return
        refreshed = build_llm(self.model)
        if refreshed.available:
            self.llm = refreshed
            self.interpreter = Interpreter(self.llm, self.settings)

    def ask(self, doc_id: str, question: str, mode: str = "explain", condition: str = "c5") -> Answer:
        if mode not in {"explain", "socratic"}:
            raise ValueError("mode must be explain or socratic")
        self._refresh_llm()
        condition = condition if condition in CONDITIONS else "c5"
        flags = CONDITIONS[condition]
        started = time.perf_counter()
        trace: list[TraceStep] = []
        answer = Answer(
            question=question,
            doc_id=doc_id,
            mode=mode,  # type: ignore[arg-type]
            answer="",
            condition=condition,
            llm=self.llm.name,
            created_at=now_iso(),
            session_id=uuid.uuid4().hex,
        )

        def step(agent: str, action: str, detail: str = "", at: float | None = None) -> None:
            trace.append(
                TraceStep(
                    agent=agent,
                    action=action,
                    detail=detail,
                    elapsed_ms=round(((at or time.perf_counter()) - started) * 1000, 2),
                )
            )

        step("Planner", "plan", f"意图=课程问答；模式={mode}；条件={condition}")

        if not flags.retrieval:
            step("Interpreter", "bare_llm", "不使用教材检索（C1 基线）")
            if self.llm.available:
                text = self.llm.chat(
                    "你是一个通用的教学助手，请直接回答问题。",
                    question,
                    temperature=self.settings.temperature,
                )
                answer.answer = text
                # C1 does not retrieve for generation. We still retrieve the
                # textbook evidence only to score fidelity on the same scale as
                # the other conditions; these passages are never shown to the
                # generator and are not returned as citations.
                scoring_evidence = self.retriever.retrieve(
                    doc_id,
                    question,
                    top_k=self.settings.top_k,
                )
                answer.support_rate = round(
                    self.verifier.support_rate(text, scoring_evidence), 4
                )
                step(
                    "Verifier",
                    "score_only",
                    f"仅用于评分的教材支持度={answer.support_rate:.3f}（未参与生成）",
                )
            else:
                answer.answer = "C1 基线需要连接本地 Qwen3 模型；当前处于离线抽取模式，未生成模型回答"
                answer.refused = True
                answer.reason = "llm_unavailable"
            answer.trace = trace
            answer.latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.store.save_session(answer)
            return answer

        candidates = self.retriever.retrieve(
            doc_id,
            question,
            top_k=self.settings.top_k,
            use_bm25=flags.bm25,
            use_dense=flags.dense,
            use_rerank=flags.rerank,
        )
        coverage = self.retriever.coverage_for_query(question, candidates)
        answer.coverage = round(coverage, 4)
        threshold = self.settings.coverage_threshold
        if self.embedder.name != "hash-512":
            threshold = max(threshold, 0.36)
        answer.evidence = candidates[:4]
        step(
            "Retriever",
            "hybrid_retrieve" if flags.bm25 and flags.dense else "dense_retrieve",
            f"候选={len(candidates)}；覆盖率={coverage:.3f}；"
            + (f"首条=第{candidates[0].chunk.page}页" if candidates else "无候选"),
        )

        if not candidates:
            answer.refused = True
            answer.reason = "教材中没有检索到相关段落"
            answer.answer = "教材中没有找到与该问题相关的段落，因此无法给出有依据的回答。"
            step("Interpreter", "refuse", answer.reason)
            answer.trace = trace
            answer.latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.store.save_session(answer)
            return answer

        if flags.agents and coverage < threshold:
            answer.refused = True
            answer.reason = f"检索覆盖率 {coverage:.2f} 低于阈值 {threshold:.2f}"
            answer.answer = (
                "教材未覆盖该问题。最接近的内容是"
                f"{self.interpreter.describe(candidates)}，但不足以支撑可靠回答。"
                "建议回到教材相关章节，或提出教材范围内的追问。"
            )
            step("Verifier", "refuse_out_of_scope", answer.reason)
            answer.trace = trace
            answer.latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.store.save_session(answer)
            return answer

        interpretation = self.interpreter.generate(question, candidates, mode=mode)
        answer.answer = interpretation.text
        answer.llm = self.llm.name if interpretation.used_llm else "extractive"
        step(
            "Interpreter",
            "llm_generate" if interpretation.used_llm else "extractive_generate",
            f"模式={mode}；证据={min(len(candidates), 4)} 条",
        )

        if answer.answer.strip().upper().startswith("REFUSE"):
            answer.refused = True
            answer.reason = "模型判定教材证据不足"
            answer.answer = (
                "教材中现有片段不足以回答该问题。"
                f"{self.interpreter.describe(candidates)} 的内容与此问题关联有限。"
            )
            step("Verifier", "refuse_by_model", answer.reason)
        else:
            support = self.verifier.support_rate(answer.answer, candidates)
            citations = self.verifier.citation_rate(answer.answer)
            step(
                "Verifier",
                "check_support",
                f"支撑率={support:.3f}；引用率={citations:.3f}",
            )

            if flags.anchor and interpretation.used_llm and support < self.settings.support_threshold:
                step("Verifier", "regenerate", "支撑率不足，触发一次严格重生成")
                retry = self.interpreter.generate(
                    question, candidates, mode=mode, strict=True, previous=answer.answer
                )
                if retry.used_llm and retry.text and not retry.text.strip().upper().startswith("REFUSE"):
                    answer.answer = retry.text
                    support = self.verifier.support_rate(answer.answer, candidates)
                    citations = self.verifier.citation_rate(answer.answer)
                    step("Verifier", "recheck", f"重生成后支撑率={support:.3f}")

            answer.support_rate = round(support, 4)
            if flags.anchor and support < 0.3:
                answer.refused = True
                answer.reason = f"回答支撑率 {support:.2f} 过低，按教材边界拒答"
                answer.answer = (
                    "教材中的证据不足以支撑一个可靠回答，因此不作推测。"
                    f"可参考{self.interpreter.describe(candidates)}。"
                )
                step("Verifier", "refuse_low_support", answer.reason)

        answer.citations = [
            Citation(
                chunk_id=candidate.chunk.id,
                page=candidate.chunk.page,
                quote=truncate(candidate.chunk.text, 300),
                bbox=candidate.chunk.bbox,
                score=round(candidate.score, 4),
            )
            for candidate in candidates[:4]
        ]
        answer.trace = trace
        answer.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        self.store.save_session(answer)
        return answer
