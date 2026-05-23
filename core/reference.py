"""core/reference.py — 跨 chat 实体共指消解（Cross-Chat Entity Coreference Resolution）。

架构理念：
  纯解析式只能"找到"字面匹配——「小张」命中 person 节点。
  但「小张离职了」「上次你推荐的方案有问题」「我想继续之前那个话题」
  这类语义需要真正的推理：理解状态变化、隐式指代、关系性质。
  只有让 LLM 参与思考，才是在构建数字生命，而不是解析器。

两阶段流水线：
    1. 本地预热（快，免费）
        - 轻量提取自我介绍 / 回指提示 / 主题锚点 → ExtractedSignals
    - FTS5 多锚点召回候选集（候选预算来自 config）
  2. LLM 推理（慢，有价值）
     - 将消息 + 候选节点摘要 → 专用小 prompt → LLM 判断实体关联
     - LLM 返回：哪些节点真正被引用、关联性质（引用/状态变化/隐式/自我介绍）
     - Provider 不可用时自动降级为本地评分（保留可用性）

理论依据：
  Wu et al. (2020)  Scalable Zero-shot Entity Linking — mention → KB entity
  Xu et al. (2021)  Beyond Goldfish Memory (MSC) — 跨 session 实体一致性
  Park et al. (2023) Generative Agents — importance 驱动记忆激活
  Anderson (1983)   ACT-R — 多锚点激活叠加
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.config import ThresholdsConfig

if TYPE_CHECKING:
    from memory.semantic import SemanticMemory
    from memory.episodic import EpisodicMemory
    from provider.base import Provider

_log = logging.getLogger("lingzhou.reference")

_TOPIC_PUNCT_PATTERN = re.compile(r"[，。！？；、,.!?]+")

# LLM 推理提示（专用小 prompt，与 judgment bundle 完全解耦）
_REASON_SYSTEM = """\
你是灵舟的记忆链接器，负责实体共指消解。

任务：分析用户消息，在候选记忆节点中找出与消息存在真实上下文关联的实体。

判断维度（任一满足即纳入）：
  direct    — 消息直接提及该实体名称或别名
  state     — 消息描述了该实体的状态变化（如"离职""完成""取消"）
  implicit  — 消息通过"上次的""你推荐的"等隐式引用该实体
  self_intro — 消息是自我介绍，与人物节点对应
    temporal  — 消息中的时间感知与候选节点 created_at / 最近叙事上下文吻合

可结合用户消息中的相对时间表达（如"昨天""刚才""上次"）自行判断 temporal 关联，
不要假定外部已经把这些时间词换算成固定小时窗口。

输出格式：JSON 数组，不加 markdown。每项字段：
  node_id          — 候选节点的 id（原样输出，不得修改）
  confidence       — 关联置信度 0.0~1.0（两位小数）
  relationship_note — 一句话说明关联性质（中文，≤20字）

无关候选不输出。无相关实体时输出 []。\
"""


@dataclass
class ExtractedSignals:
    """轻量预热阶段提取的检索信号。"""
    topic_anchors: list[str] = field(default_factory=list[str])


@dataclass
class ResolvedEntity:
    """经 LLM 推理确认的实体链接结果。"""
    node_id: str
    title: str
    kind: str
    confidence: float
    snippet: str                    # body 前若干字（由 config 控制）
    signal_types: list[str]         # 本地检索路径（调试用）
    relationship_note: str = ""     # LLM 推理给出的关联说明


class ReferenceResolver:
    """实体共指消解器：本地候选收窄 + LLM 推理判断。

    JudgmentLayer 持有单例，跨 tick 复用。
    Provider 不可用时自动降级为纯本地评分。
    """

    def __init__(
        self,
        provider: "Provider | None" = None,
        *,
        thresholds: ThresholdsConfig | None = None,
        reason_temperature: float | None = None,
    ) -> None:
        self._provider = provider
        self._last_llm_error: str = ""
        self._last_llm_error_code: str = ""
        self._thresholds = thresholds or ThresholdsConfig()
        self._reason_temperature = reason_temperature

    @property
    def last_llm_error(self) -> str:
        return self._last_llm_error

    @property
    def last_llm_error_code(self) -> str:
        return self._last_llm_error_code

    @property
    def llm_available(self) -> bool:
        return self._provider is not None and not self._last_llm_error

    def _classify_error_code(self, err_text: str) -> str:
        text = (err_text or "").lower()
        if " 429 " in f" {text} " or "too many requests" in text:
            return "429"
        if " 401 " in f" {text} " or "unauthorized" in text:
            return "401"
        if " 403 " in f" {text} " or "forbidden" in text:
            return "403"
        if " 400 " in f" {text} " or "bad request" in text:
            return "400"
        if "readtimeout" in text or "timeout" in text:
            return "timeout"
        return "other"

    # ── 阶段一：轻量信号提取（< 1ms）────────────────────────────────────────

    def extract_signals(self, message: str) -> ExtractedSignals:
        sigs = ExtractedSignals()
        cleaned = re.sub(r"\s+", " ", message).strip()
        cleaned = _TOPIC_PUNCT_PATTERN.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) >= self._thresholds.reference_topic_anchor_min_chars:
            sigs.topic_anchors.append(cleaned[: self._thresholds.reference_anchor_text_chars])
        return sigs

    # ── 阶段二：本地候选召回（FTS5，O(log n)）────────────────────────────────

    def _retrieve_candidates(
        self,
        message: str,
        sigs: ExtractedSignals,
        semantic: "SemanticMemory",
        episodic: "EpisodicMemory",
        source: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """返回 {node_id: node_dict}，最多 reference_candidate_cap 个候选节点。"""
        seen: set[str] = set()
        candidates: dict[str, dict[str, Any]] = {}

        def _add(nodes: list[dict[str, Any]], sig: str) -> None:
            for nd in nodes:
                nid = nd.get("id", "")
                if nid and nid not in seen:
                    seen.add(nid)
                    nd["_sig"] = nd.get("_sig", []) + [sig]
                    candidates[nid] = nd

        # 话题 + 整条消息 → 多锚点召回
        anchors: list[str] = []
        for anchor in [message[: self._thresholds.reference_anchor_text_chars], *sigs.topic_anchors]:
            if anchor and anchor not in anchors:
                anchors.append(anchor)
            if len(anchors) >= self._thresholds.reference_max_anchors:
                break
        _add(semantic.retrieve_multi_anchor(anchors, top_k=self._thresholds.reference_topic_top_k, source=source), "topic")

        # 最近叙事预热 → 只提供最近上下文，不替用户解释时间词
        recent_rows = episodic.list_recent_narrative(limit=self._thresholds.reference_recent_narrative_limit)
        for row in recent_rows:
            content = row.get("content", "")[: self._thresholds.reference_anchor_text_chars]
            if content:
                _add(semantic.retrieve(content, top_k=self._thresholds.reference_recent_semantic_top_k, source=source), "recent")

        return dict(list(candidates.items())[: self._thresholds.reference_candidate_cap])

    # ── 阶段三：LLM 推理（核心思考）────────────────────────────────────────

    async def _llm_reason(
        self,
        message: str,
        candidates: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """让 LLM 从候选集中判断哪些实体真正被引用，以及关联性质。"""
        if self._provider is None:
            self._last_llm_error = ""
            self._last_llm_error_code = ""
            return []
        from provider.base import Message as LLMMessage

        # 构造候选节点摘要（控制 token 数）
        cand_lines: list[str] = []
        for nid, nd in candidates.items():
            body_snippet = nd.get("body", "")[: self._thresholds.reference_candidate_body_chars].replace("\n", " ")
            created_at = str(nd.get("created_at", ""))
            cand_lines.append(
                f'  {{"id":"{nid}","kind":"{nd.get("kind","")}","title":"{nd.get("title","")}","created_at":"{created_at}","body":"{body_snippet}"}}'
            )
        cand_block = "[\n" + ",\n".join(cand_lines) + "\n]"

        user_content = f'用户消息："{message}"\n\n候选节点：\n{cand_block}'

        try:
            raw = await self._provider.chat(
                [
                    LLMMessage(role="system", content=_REASON_SYSTEM),
                    LLMMessage(role="user", content=user_content),
                ],
                temperature=self._reason_temperature,
            )
        except Exception as exc:
            err_text = str(exc) or repr(exc)
            self._last_llm_error = err_text
            self._last_llm_error_code = self._classify_error_code(err_text)
            _log.warning("[reference] LLM 推理失败，降级为本地评分: %s", exc)
            return []
        self._last_llm_error = ""
        self._last_llm_error_code = ""

        # 解析 JSON 数组
        raw = raw.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            return json.loads(raw[start: end + 1])
        except json.JSONDecodeError:
            return []

    # ── 主入口（异步）───────────────────────────────────────────────────────

    async def resolve(
        self,
        message: str,
        semantic: "SemanticMemory",
        episodic: "EpisodicMemory",
    ) -> list["ResolvedEntity"]:
        """两阶段：本地召回候选 → LLM 推理判断 → ResolvedEntity 列表。

        Provider 不可用时：自动降级为本地评分，保持可用性。
        """
        if not message or not message.strip():
            return []

        sigs = self.extract_signals(message)
        candidates = self._retrieve_candidates(message, sigs, semantic, episodic)
        if not candidates:
            return []

        # LLM 推理
        llm_results: list[dict[str, Any]] = []
        if self._provider is not None:
            llm_results = await self._llm_reason(message, candidates)

        # 构造 ResolvedEntity 列表
        entities: list[ResolvedEntity] = []

        if llm_results:
            # LLM 推理路径
            for item in llm_results:
                nid = str(item.get("node_id", ""))
                if nid not in candidates:
                    continue
                confidence = float(item.get("confidence", 0.0))
                if confidence < self._thresholds.reference_min_confidence:
                    continue
                nd = candidates[nid]
                entities.append(ResolvedEntity(
                    node_id=nid,
                    title=nd.get("title", nid),
                    kind=nd.get("kind", "unknown"),
                    confidence=round(confidence, 2),
                    snippet=nd.get("body", "")[: self._thresholds.reference_entity_snippet_chars],
                    signal_types=nd.get("_sig", []),
                    relationship_note=str(item.get("relationship_note", "")),
                ))
        else:
            # 降级路径：本地评分（简单计数信号数）
            for nid, nd in candidates.items():
                sigs_hit = nd.get("_sig", [])
                base = self._thresholds.reference_local_signal_base + len(set(sigs_hit)) * self._thresholds.reference_local_signal_step
                if base < self._thresholds.reference_min_confidence:
                    continue
                entities.append(ResolvedEntity(
                    node_id=nid,
                    title=nd.get("title", nid),
                    kind=nd.get("kind", "unknown"),
                    confidence=round(min(base, self._thresholds.reference_local_confidence_cap), 2),
                    snippet=nd.get("body", "")[: self._thresholds.reference_entity_snippet_chars],
                    signal_types=sigs_hit,
                    relationship_note="（本地评分，LLM 不可用）",
                ))

        entities.sort(key=lambda e: e.confidence, reverse=True)
        return entities[: self._thresholds.reference_entity_section_limit]

    # ── 格式化注入 entity_section ────────────────────────────────────────────

    @staticmethod
    def format_section(entities: list["ResolvedEntity"]) -> str:
        if not entities:
            return "（无可链接的历史实体）"
        lines = ["从记忆中识别到以下相关实体（LLM 推理确认，按置信度排列）："]
        for e in entities:
            note = f" — {e.relationship_note}" if e.relationship_note and "本地评分" not in e.relationship_note else ""
            lines.append(
                f"- [{e.kind}] {e.title}（confidence:{e.confidence:.2f}{note}）"
            )
            if e.snippet:
                lines.append(f"  {e.snippet}")
        return "\n".join(lines)
