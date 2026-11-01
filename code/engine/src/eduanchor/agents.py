from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .config import Settings
from .embeddings import Embedder
from .llm import LLM
from .schemas import RetrievedChunk
from .utils import cosine, overlap_score, split_sentences, truncate

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 EduAnchor 的教材解读智能体。你只能依据给定的教材片段回答。
规则：
1. 每个事实性论断后必须标注引用编号，如 [1]。
2. 不得引入教材片段之外的知识。
3. 如果教材片段不足以回答问题，只输出：REFUSE
4. 使用简洁、准确的中文，必要时给出教材页码。"""


@dataclass(slots=True)
class Interpretation:
    text: str
    used_llm: bool


class Interpreter:
    def __init__(self, llm: LLM, settings: Settings) -> None:
        self.llm = llm
        self.settings = settings

    def _evidence_block(self, candidates: list[RetrievedChunk], limit: int = 4) -> str:
        lines: list[str] = []
        for index, candidate in enumerate(candidates[:limit], start=1):
            text = truncate(candidate.chunk.text, 520)
            lines.append(f"[{index}] (第{candidate.chunk.page}页) {text}")
        return "\n\n".join(lines)

    def describe(self, candidates: list[RetrievedChunk], limit: int = 3) -> str:
        parts: list[str] = []
        for candidate in candidates[:limit]:
            heading = candidate.chunk.heading or "相关段落"
            parts.append(f"第{candidate.chunk.page}页「{truncate(heading, 30)}」")
        return "、".join(parts) if parts else "教材中没有找到相关段落"

    def generate(
        self,
        question: str,
        candidates: list[RetrievedChunk],
        mode: str = "explain",
        strict: bool = False,
        previous: str | None = None,
    ) -> Interpretation:
        if self.llm.available and candidates:
            style = "用苏格拉底式提问引导学习者思考，不要直接给出完整结论" if mode == "socratic" else "给出清晰、分点的解释"
            extra = ""
            if strict and previous:
                extra = (
                    "\n\n上一次回答存在未被教材支撑的论断：\n"
                    f"{truncate(previous, 300)}\n请删除或改写这些论断，确保每一句都能被上述片段支撑。"
                )
            user = (
                f"问题：{question}\n\n教材片段：\n{self._evidence_block(candidates)}\n\n"
                f"要求：{style}；逐句标注引用编号；证据不足时输出 REFUSE。{extra}"
            )
            try:
                text = self.llm.chat(SYSTEM_PROMPT, user, temperature=0.15)
                if text:
                    return Interpretation(text=text, used_llm=True)
            except Exception as exc:  # noqa: BLE001 - fall back to extractive mode
                logger.warning("LLM generation failed, using extractive fallback: %s", exc)
        return Interpretation(text=self._extractive(question, candidates, mode), used_llm=False)

    def _extractive(self, question: str, candidates: list[RetrievedChunk], mode: str) -> str:
        if not candidates:
            return "教材中没有找到与该问题相关的段落，因此无法给出有依据的回答。"
        top = candidates[0]
        quote = truncate(top.chunk.text, 260)
        if mode == "socratic":
            points = split_sentences(top.chunk.text)[:3]
            prompts: list[str] = []
            for index, point in enumerate(points, start=1):
                stem = truncate(point, 50)
                prompts.append(f"{index}. 教材中提到“{stem}”，它成立的前提条件是什么？")
            prompts.append(f"{len(prompts) + 1}. 如果改变其中的关键条件，教材中的结论是否仍然成立？")
            return (
                f"教材第{top.chunk.page}页给出了相关线索 [1]：\n\n> {quote}\n\n"
                "可以沿着以下问题继续思考：\n" + "\n".join(prompts)
            )

        sentences = split_sentences(top.chunk.text)
        key_points = [truncate(sentence, 140) for sentence in sentences[:3]]
        bullets = "\n".join(f"- {point}（第{top.chunk.page}页，[1]）" for point in key_points)
        extra = ""
        if len(candidates) > 1:
            second = candidates[1]
            extra = (
                f"\n\n教材在第{second.chunk.page}页进一步指出 [2]：\n"
                f"> {truncate(second.chunk.text, 180)}"
            )
        return (
            f"根据教材第{top.chunk.page}页的原文 [1]：\n\n> {quote}\n\n"
            f"教材中的关键表述包括：\n{bullets}{extra}"
        )


class Verifier:
    """Claim-level faithfulness checker based on lexical and dense support."""

    def __init__(self, embedder: Embedder, settings: Settings) -> None:
        self.embedder = embedder
        self.settings = settings

    @staticmethod
    def claims(answer: str) -> list[str]:
        claims: list[str] = []
        for line in answer.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.、)])\s*", "", line).strip()
            cleaned = re.sub(r"\[\d+\]", "", cleaned)
            if len(cleaned) < 10:
                continue
            claims.extend(split_sentences(cleaned, min_len=10))
        seen: set[str] = set()
        unique: list[str] = []
        for claim in claims:
            if claim not in seen:
                unique.append(claim)
                seen.add(claim)
        return unique

    def support_rate(self, answer: str, candidates: list[RetrievedChunk]) -> float:
        claims = self.claims(answer)
        if not claims:
            return 0.0
        evidence: list[str] = []
        for candidate in candidates[:4]:
            evidence.extend(split_sentences(candidate.chunk.text, min_len=6))
        if not evidence:
            return 0.0
        claim_vectors = self.embedder.encode(claims)
        evidence_vectors = self.embedder.encode(evidence)
        supported = 0
        for index, claim in enumerate(claims):
            combined = [
                0.7 * overlap_score(claim, sentence)
                + 0.3 * max(0.0, cosine(claim_vectors[index], evidence_vectors[j]))
                for j, sentence in enumerate(evidence)
            ]
            if combined and max(combined) >= self.settings.support_threshold:
                supported += 1
        return supported / len(claims)

    def citation_rate(self, answer: str) -> float:
        claims = self.claims(answer)
        if not claims:
            return 0.0
        cited = sum(1 for claim in re.split(r"(?<=[。！？!?])", answer) if re.search(r"\[\d+\]", claim))
        return min(1.0, cited / max(len(claims), 1))
