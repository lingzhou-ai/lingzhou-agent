"""core/judgment/assembler.py — 判断层上下文组装器。

职责：
- 组装 bundle（运行时状态 → 结构化 context）
- 管理 skills、prompts、identity 等静态配置
- 构建 LLM 消息列表（system + user）

JudgmentLayer 只保留 decide / decide_continue 编排逻辑。
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from provider.catalog import lookup_model
from core.self_model import fmt_self_model
from .output import (
    JudgmentOutput,
    _structured_tool_history_window,
    _build_team_view_from_cfg,
    tool_tier_mapping,
)
from .context import (
    _fmt_chat_continuity,
    _fill_template,
    _fmt_chat_history,
    _fmt_chat_memories,
    _fmt_interlocutor_continuity,
    _fmt_cognitive_signals,
    _fmt_context_facts,
    _fmt_current_time,
    _fmt_durable_failures,
    _fmt_ethos,
    _fmt_failures,
    _fmt_hard_boundaries,
    _fmt_judgment_signals,
    _fmt_memories,
    _fmt_memory_recall,
    _fmt_memory_system,
    _fmt_perception_replay,
    _fmt_percept,
    _fmt_probe_sensors,
    _fmt_blind_spots,
    _fmt_recent_runs,
    _fmt_runnable_tasks,
    _fmt_shell_capabilities,
    _fmt_similar_tasks,
    _fmt_skill_catalog,
    _fmt_skills,
    _fmt_config_snapshot,
    _fmt_primary_skill,
    _fmt_soul,
    _fmt_task,
    _fmt_tools,
    _fmt_waiting_tasks,
    _fmt_wm,
    _load_context_facts_snapshot,
    _load_durable_failure_snapshot,
    _validate_context_schema,
    apply_context_budget,
)

from core.execution import action_key_param
from store.task import RUNNABLE_TASK_STATUSES
from tools.registry import tool_has_capability

_log = logging.getLogger("lingzhou.judgment")


def _chat_memory_tag(chat_id: str) -> str:
    return f"chat:{str(chat_id or '').strip()}"


async def _resolve_context_chat_id(task_store: Any, task: Any, explicit_chat_id: str | None) -> str | None:
    normalized = str(explicit_chat_id or "").strip()
    if normalized:
        return normalized
    if task is None:
        return None
    try:
        value, found = await task_store.get_fact(f"task:{task.id}:chat_id")
    except Exception:
        value, found = "", False
    if found and str(value or "").strip():
        return str(value).strip()
    source = str(getattr(task, "source", "") or "").strip()
    if source.startswith("chat:"):
        resolved = source[5:].strip()
        return resolved or None
    return None


async def _load_runnable_tasks_snapshot(task_store: Any, *, limit: int = 8) -> list[Any]:
    list_runnable = getattr(task_store, "list_runnable_tasks", None)
    if callable(list_runnable):
        return await list_runnable(limit=limit)
    list_tasks = getattr(task_store, "list_tasks", None)
    if not callable(list_tasks):
        return []
    tasks = await list_tasks(limit=limit)
    return [task for task in tasks if getattr(task, "status", "") in RUNNABLE_TASK_STATUSES][:limit]


async def _load_similar_tasks_snapshot(
    task_store: Any,
    query: str,
    *,
    active_task: Any = None,
    limit: int = 5,
    min_score: float = 0.45,
) -> list[tuple[Any, float]]:
    finder = getattr(task_store, "find_similar_open_tasks", None)
    if not callable(finder) or not str(query or "").strip():
        return []
    exclude_task_ids = [active_task.id] if active_task is not None else None
    return await finder(
        query,
        limit=limit,
        min_score=min_score,
        exclude_task_ids=exclude_task_ids,
    )


if TYPE_CHECKING:
    from core.config import Config
    from core.perception import (
        Percept, EmotionState, EthosState, JudgmentSignals, PerceptionReplaySummary,
        CognitiveSignals,
    )
    from core.skill import Skill
    from memory.working import WorkingMemory
    from store.task import TaskStore
    from store.episodic import EpisodicMemory
    from store.semantic import SemanticMemory
    from tools.registry import ToolRegistry
    from provider.base import Provider
    from .executor import JudgmentExecutor


class JudgmentContextAssembler:
    """组装判断层的上下文：skills、prompts、感知状态 → LLM 消息。"""

    def __init__(
        self,
        provider: Provider,
        registry: ToolRegistry,
        cfg: Config,
        executor: JudgmentExecutor,
    ) -> None:
        from core.skill import SkillRegistry
        from core.reference import ReferenceResolver
        self._registry = registry
        self._cfg = cfg
        self._executor = executor
        self._system_prompt = cfg.load_prompt("system")
        self._identity_prefix: str = ""   # bootstrap 注入的永久身份前缀（不随 WM 驱逐）
        self._judgment_template = cfg.load_prompt("judgment")
        _skills_dir = Path(cfg.loop.workspace_dir).expanduser() / "skills"
        self._skills = SkillRegistry(skills_dir=_skills_dir)
        self._ref_resolver = ReferenceResolver(
            provider=provider,
            thresholds=cfg.thresholds,
            reason_temperature=cfg.temperature,
        )
        # 内层工具循环用：缓存上一次 decide() 组装的完整上下文，由 decide_continue() 复用
        self._last_context_text: str = ""
        # 上下文缓存：key=(section_name, tick)，value=计算好的文本片段
        self._context_cache: dict[str, str] = {}
        # 探针系统引用：由 CognitionLoop.__init__ 在创建 ProbeManager 后注入
        self._probe_manager: Any = None
        self._last_selected_skills: list[Skill] = []
        # 上轮 LLM 实际应用的技能名（用于下轮 match_for_context 优先注入）
        self._last_applied_skill_names: list[str] = []

    def reload_skills(self) -> None:
        from core.skill import SkillRegistry

        skills_dir = self._cfg.workspace_dir / "skills"
        self._skills = SkillRegistry(skills_dir=skills_dir)
        _log.info("[judgment] 已从 %s 重新加载 skills", skills_dir)

    def _coerce_frame_args(
        self,
        frame_or_percept: CognitionFrame | Percept,
        wm: WorkingMemory | None,
        task_store: TaskStore | None,
        episodic: EpisodicMemory | None,
        semantic: SemanticMemory | None,
        emotion: EmotionState | None,
    ) -> tuple[
        Percept,
        WorkingMemory,
        TaskStore,
        EpisodicMemory,
        SemanticMemory,
        EmotionState,
    ]:
        from .runtime import CognitionFrame as _CognitionFrame  # lazy import avoids circular
        if isinstance(frame_or_percept, _CognitionFrame):
            return (
                frame_or_percept.percept,
                frame_or_percept.wm,
                frame_or_percept.task_store,
                frame_or_percept.episodic,
                frame_or_percept.semantic,
                frame_or_percept.emotion,
            )
        if None in (wm, task_store, episodic, semantic, emotion):
            raise TypeError("decide/_assemble_context 缺少认知基底参数")
        return (
            frame_or_percept,
            cast("WorkingMemory", wm),
            cast("TaskStore", task_store),
            cast("EpisodicMemory", episodic),
            cast("SemanticMemory", semantic),
            cast("EmotionState", emotion),
        )

    def set_identity_prefix(self, prefix: str) -> None:
        """由 SoulManager.bootstrap() 调用，将 BOOTSTRAP.md/IDENTITY.md 永久注入 system prompt。"""
        self._identity_prefix = prefix
        _log.debug("[judgment] identity_prefix 已设置（%d 字符）", len(prefix))

    def reload_prompt(self, key: str) -> None:
        """evolution 进化提示词后调用，热重载模板。"""
        if key == "judgment":
            self._judgment_template = self._cfg.load_prompt("judgment")
        elif key == "system":
            self._system_prompt = self._cfg.load_prompt("system")

    @staticmethod
    def _skills_for_log(skills: list[Skill]) -> str:
        if not skills:
            return "none"
        return ",".join(skill.name for skill in skills[:3])

    def _record_applied_skills(self, output: JudgmentOutput) -> str:
        applied = ",".join(output.applied_skills) if output.applied_skills else "none"
        if output.applied_skills:
            self._last_applied_skill_names = list(output.applied_skills)
        return applied

    def _effective_registry(self, registry: Any | None = None) -> Any:
        return registry or self._registry

    def _counts_as_exploration_budget(self, tool_name: str, registry: Any | None = None) -> bool:
        effective_registry = self._effective_registry(registry)
        return any(
            tool_has_capability(effective_registry, tool_name, capability)
            for capability in ("ask_evidence", "completion_info_only", "completion_verify")
        )

    def _build_messages(self, user_content: str) -> list[Any]:
        from provider.base import Message

        system_content = (
            self._identity_prefix + "\n\n" + self._system_prompt
            if self._identity_prefix
            else self._system_prompt
        )
        return [
            Message(role="system", content=system_content),
            Message(role="user", content=user_content),
        ]

    def _build_continue_context(
        self,
        tool_history: list[dict[str, Any]],
        *,
        user_message: str,
        reply_only: bool,
        wm_delta: list[dict[str, Any]] | None,
    ) -> str:
        history_json_block, history_block = _structured_tool_history_window(tool_history)
        wm_delta_block = ""
        if wm_delta:
            delta_lines = [
                f"- [{item.get('kind', '')}|p={item.get('priority', 0):.2f}] {item.get('content', '')}"
                for item in wm_delta
            ]
            wm_delta_block = "## 本轮新增工作记忆（WM 更新，初始上下文之后）\n" + "\n".join(delta_lines) + "\n\n"
        if reply_only:
            return (
                f"{self._last_context_text}\n\n"
                "---\n"
                f"{wm_delta_block}"
                "## 结构化最近工具结果(JSON)\n"
                f"{history_json_block}\n\n"
                "## 本轮已执行工具历史\n"
                f"{history_block}\n\n"
                "你现在处于最终回复阶段。禁止再调用任何工具。"
                "请只基于已有证据生成对用户的最终 reply_to_user。"
                "decision 只能是 pause 或 wait，chosen_action_id 必须留空。"
            )

        hint = "用户正在等待回复，尽快在本轮设置 reply_to_user 字段。" if user_message else ""
        return (
            f"{self._last_context_text}\n\n"
            "---\n"
            f"{wm_delta_block}"
            "## 结构化最近工具结果(JSON)\n"
            f"{history_json_block}\n\n"
            "## 本轮已执行工具历史\n"
            f"{history_block}\n\n"
            "优先依据结构化结果判断当前状态，不要只凭模糊回忆续写。\n\n"
            f"请根据以上结果继续执行下一个必要工具，或生成最终回复（reply_to_user 非空）。{hint}"
        )



    def _build_model_routing_section(
        self,
        *,
        phase: str,
        user_message: str,
        current_action: str,
        tool_history: list[dict[str, Any]] | None,
        effective_thinking: str,
        routing_overrides: dict[str, str] | None = None,
        registry: Any | None = None,
    ) -> str:
        effective_registry = self._effective_registry(registry)
        route_tiers: list[str] = ["reader", "reasoner", "repair"]
        available_models: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for tier in route_tiers:
            _, model_ref = self._executor._resolve_tier_model(tier)
            key = (tier, model_ref)
            if key in seen:
                continue
            seen.add(key)
            model_id = model_ref.split("/", 1)[1] if "/" in model_ref else model_ref
            spec = lookup_model(model_id) or {}
            reasoning = bool(spec.get("reasoning"))
            last_error = self._executor._provider_errors.get(model_ref)
            health = self._executor._get_health(model_ref)
            # 检查该 tier 是否被临时覆盖
            override_model = (routing_overrides or {}).get(tier)
            available_models.append({
                "tier": tier,
                "model": model_ref,
                "available": self._executor._is_model_available(model_ref),
                "reasoning": reasoning,
                "cost_level": self._executor._cost_level_for_model(model_ref, reasoning),
                "latency_level": self._executor._latency_level_for_model(model_ref, reasoning),
                "context_window": spec.get("context_window") or self._cfg.context_window_tokens,
                "current_thinking": effective_thinking or self._cfg.thinking,
                "last_error": last_error,
                "last_error_code": health.last_code or None,
                "cooldown_remaining_sec": max(0, int(health.cooldown_until - time.time())),
                "overridden_by": override_model if override_model and override_model != model_ref else None,
            })

        task_explore_count = 0
        repeat_action_count = 0
        repeat_read_count = 0
        if tool_history:
            def _trailing_repeat_count(matcher: Any) -> int:
                count = 0
                for item in reversed(tool_history):
                    if not matcher(item):
                        break
                    count += 1
                return count

            task_explore_count = sum(
                1
                for item in tool_history
                if self._counts_as_exploration_budget(str(item.get("tool") or ""), effective_registry)
            )
            if len(tool_history) >= 2:
                _last_tool = str(tool_history[-1].get("tool", ""))
                _last_action_sig = f"{_last_tool}|{action_key_param(tool_history[-1].get('params') or {})}"
                repeat_action_count = _trailing_repeat_count(
                    lambda item: (
                        f"{str(item.get('tool', ''))}|{action_key_param(item.get('params') or {})}"
                        == _last_action_sig
                    )
                )
                if _last_tool == "file.read":
                    _last_path = json.dumps(tool_history[-1].get("params", {}), ensure_ascii=False)
                    repeat_read_count = _trailing_repeat_count(
                        lambda item: str(item.get("tool", "")) == "file.read"
                        and json.dumps(item.get("params", {}), ensure_ascii=False) == _last_path
                    )

        ask_evidence_hits = sum(
            1 for item in (tool_history or [])
            if tool_has_capability(effective_registry, str(item.get("tool") or ""), "ask_evidence")
            and str(item.get("result") or "").strip()
            and not str(item.get("result") or "").startswith("ERROR[")
        )

        posture = (
            "respond"
            if user_message
            else (
                "converge"
                if task_explore_count >= self._cfg.thresholds.task_explore_converge_after
                else "conserve"
            )
        )
        def _fmt_duration_ms(value: float) -> str:
            ms = float(value)
            if ms >= 1000:
                return f"{ms / 1000.0:g}s"
            return f"{ms:g}ms"

        with_task_bounds = self._cfg.loop.idle_with_task_bounds
        no_task_bounds = self._cfg.loop.idle_no_task_bounds
        with_task_bounds_text = f"{_fmt_duration_ms(with_task_bounds[0])}-{_fmt_duration_ms(with_task_bounds[1])}"
        no_task_bounds_text = f"{_fmt_duration_ms(no_task_bounds[0])}-{_fmt_duration_ms(no_task_bounds[1])}"
        default_gap_text = (
            f"有任务 {_fmt_duration_ms(self._cfg.loop.active_idle_gap)}，"
            f"无任务 {_fmt_duration_ms(self._cfg.loop.max_idle_gap)}"
        )

        capability_mapping: dict[str, list[str]] = {}
        current_action_caps: list[str] = []
        task_plan_calls_this_tick = sum(
            1 for item in (tool_history or []) if str(item.get("tool") or "") == "task.plan"
        )
        continue_task_plan_max = self._cfg.thresholds.continue_task_plan_max_per_tick
        tool_history_compact_threshold = self._cfg.thresholds.continue_tool_history_compact_threshold
        tool_history_keep_last = self._cfg.thresholds.continue_tool_history_keep_last
        tool_history_count = len(tool_history or [])
        for manifest in effective_registry.list_manifests():
            for cap in manifest.capabilities:
                capability_mapping.setdefault(cap, []).append(manifest.name)
            if manifest.name == current_action:
                current_action_caps = sorted(manifest.capabilities)
        payload = {
            "active_overrides": routing_overrides or {},
            "tool_tier_mapping": tool_tier_mapping(effective_registry),
            "tool_capability_mapping": {k: sorted(v) for k, v in capability_mapping.items()},
            "current_action_capabilities": current_action_caps,
            "continue_phase_policy": {
                "task_plan_calls_this_tick": task_plan_calls_this_tick,
                "task_plan_max_per_tick": continue_task_plan_max,
                "task_plan_blocked_next": task_plan_calls_this_tick >= continue_task_plan_max,
                "tool_history_count": tool_history_count,
                "tool_history_compact_threshold": tool_history_compact_threshold,
                "tool_history_keep_last": tool_history_keep_last,
                "tool_history_will_compact_next": (
                    tool_history_count >= tool_history_compact_threshold
                    and tool_history_count > tool_history_keep_last
                ),
            },
            "tier_descriptions": {
                "reader": "轻量感知层：适合常规状态查询、读文件、检查计划、无复杂推理的心跳 tick",
                "reasoner": "深度推理层：适合用户交互、要求判断、处理复杂状态、制定或调整计划",
                "repair": "修复层：专用于解析失败、格式错误、小修小补",
            },
            "delegation_guide": (
                "你是当前层的决策者，可以通过 model_strategy 中的以下字段调控下一轮行为：\n"
                "• next_phase_tier：分配下轮的推理层级。reader=轻量感知，reasoner=深度推理，repair=修复。"
                "示例：本轮已完成复杂判断并写入任务，下轮只需追踪状态 → next_phase_tier=reader；\n"
                "• tool_tier_mapping：runtime 当前对工具族的默认分层真相；若你觉得某次具体动作应临时跨层处理，可通过 next_phase_tier 或 routing_overrides 调整，但不要假装这份映射不存在。\n"
                "• tool_capability_mapping：runtime 注入的工具能力真相（如 ask_evidence / plan_bootstrap_exempt / completion_verify）。"
                "优先按能力标签推理，不要仅凭工具名字猜类别。\n"
                "• continue_phase_policy：runtime 暴露的 tick 内计划限制真相。若 task_plan_blocked_next=true，"
                "本 tick 再输出 task.plan 会被强制打断；应直接执行计划内工具。"
                "若 tool_history_will_compact_next=true，下一轮会把早期工具记录折叠成 [compacted] 摘要，应尽量在压缩前完成总结或切换到执行。\n"
                "• next_idle_gap_secs / next_idle_gap_ms：【必须设置其中之一！】你的生命节奏控制器。"
                "next_idle_gap_secs 单位秒（小数可用，如 0.5 = 500ms），next_idle_gap_ms 单位毫秒（整数，如 500 = 500ms）；两者同时设置时 ms 优先。"
                f"范围由 idle_with_task_bounds / idle_no_task_bounds 决定（当前有任务时 {with_task_bounds_text}，无任务时 {no_task_bounds_text}）。"
                "你必须根据当前上下文主动选择一个合理值，不要依赖默认："
                "已发起shell预计30s出结果 → next_idle_gap_secs=35；刚回复完用户等下一步 → next_idle_gap_secs=120；"
                "任务推进中需快速追踪 → next_idle_gap_ms=500；实时等待短命令结束 → next_idle_gap_ms=200。"
                f"不设置此字段则用当前 loop 默认备用值（{default_gap_text}）。控制权在你手里。\n"
                "• routing_overrides：临时覆盖 tier→model 映射，格式 {\"reader\": \"bailian/qwen3.6-plus\"}。"
                "可选 tier: reader / reasoner / repair。从 catalog_models 中选择可用模型。"
                "设为 {} 可清除覆盖。覆盖持久到显式修改，无需每轮重复设置。\n"
                "• thinking_override：覆盖下一轮的 thinking 等级，可选局 off / minimal / low / medium / high。"
                "当前等级见 available_models[].current_thinking。"
                "示例：下轮需要深度推理 → thinking_override=\"high\"；下轮只需快速响应 → thinking_override=\"low\"。"
                "设为 null 或不填则恢复全局配置。仅对支持 thinking 的模型有效（reasoning=true）。\n"
                "没有明确偏好时用 default，进化机制将决定。"
            ),
            "budget_state": {
                "task_explore_count": task_explore_count,
                "repeat_action_count": repeat_action_count,
                "repeat_read_count": repeat_read_count,
                "ask_evidence_hits": ask_evidence_hits,
                "ask_evidence_budget": self._cfg.thresholds.ask_evidence_budget,
                "task_explore_converge_after": self._cfg.thresholds.task_explore_converge_after,
                "global_cost_posture": posture,
            },
            "routing_hint": {
                "phase": phase,
                "current_action": current_action,
                "user_message_present": bool(user_message),
            },
        }
        # 全量 catalog 模型列表（所有 provider 所有模型），让 LLM 能看到可用选项
        from provider import catalog as _cat
        catalog_entries: list[dict[str, Any]] = [
            {
                "model": f"{_pname}/{_m.get('id', '')}",
                "provider": _pname,
                "reasoning": bool(_m.get("reasoning")),
                "context_window": _m.get("context_window"),
            }
            for _pname in _cat.list_providers()
            for _m in _cat.list_provider_models(_pname)
        ]
        payload["catalog_models"] = catalog_entries
        # 主 provider 信息
        payload["primary_provider"] = {"model": self._cfg.model}
        # 实体消解模块健康状态
        if hasattr(self, "_ref_resolver") and self._ref_resolver is not None:
            _rr = self._ref_resolver
            payload["reference_resolution"] = {
                "llm_available": _rr.llm_available,
                "last_error": _rr.last_llm_error,
                "last_error_code": _rr.last_llm_error_code,
            }
        return json.dumps(payload, ensure_ascii=False, indent=2)


    async def _assemble_context(
        self,
        frame_or_percept: CognitionFrame | Percept,
        wm: WorkingMemory | None = None,
        task_store: TaskStore | None = None,
        episodic: EpisodicMemory | None = None,
        semantic: SemanticMemory | None = None,
        emotion: EmotionState | None = None,
        active_task: Any | None = None,
        user_message: str = "",
        chat_id: str | None = None,
        ethos_state: EthosState | None = None,
        judgment_signals: JudgmentSignals | None = None,
        hard_boundaries: list[str] | None = None,
        perception_replay: PerceptionReplaySummary | None = None,
        cognitive_signals: CognitiveSignals | None = None,
        phase: str = "initial",
        current_action: str = "",
        tool_history: list[dict[str, Any]] | None = None,
        effective_thinking: str | None = None,
        routing_overrides: dict[str, str] | None = None,
        registry_override: Any | None = None,
    ) -> str:
        """将运行时状态填入 judgment 模板。"""
        percept, wm, task_store, episodic, semantic, emotion = self._coerce_frame_args(
            frame_or_percept,
            wm,
            task_store,
            episodic,
            semantic,
            emotion,
        )
        effective_registry = self._effective_registry(registry_override)
        task = active_task if active_task is not None else await task_store.get_active()

        task_id_str = str(task.id) if task else None
        search_query = user_message or (task.next_step or task.goal or task.title) if task else user_message
        resolved_chat_id = await _resolve_context_chat_id(task_store, task, chat_id)
        _el = asyncio.get_running_loop()
        # episodic/semantic 使用同步 sqlite3，需经 executor 层驱动，避免阻塞事件循环。
        # 显式启动独立任务，既保留并行 IO，又避免把立即值混入 gather。
        episodic_text_future = _el.run_in_executor(
            None,
            episodic.load_for_context,
            task_id_str,
            self._cfg.memory.episodic_max_chars,
        )
        chat_continuity_future = (
            _el.run_in_executor(
                None,
                episodic.load_for_chat_context,
                resolved_chat_id,
                self._cfg.memory.episodic_max_chars,
            )
            if resolved_chat_id else None
        )
        recent_turns_future = (
            _el.run_in_executor(
                None,
                functools.partial(
                    episodic.get_recent_turns,
                    task_id_str,
                    self._cfg.thresholds.chat_history_turn_limit,
                    chat_id=resolved_chat_id,
                ),
            )
            if resolved_chat_id or task_id_str else None
        )
        chat_memories_future = (
            _el.run_in_executor(
                None,
                functools.partial(
                    semantic.retrieve,
                    search_query or resolved_chat_id or "",
                    min(3, self._cfg.memory.semantic_top_k),
                    tag=_chat_memory_tag(resolved_chat_id),
                    source="chat_summary",
                ),
            )
            if resolved_chat_id else None
        )
        speaker_hint_task = (
            asyncio.create_task(task_store.get_fact(f"chat:{resolved_chat_id}:interlocutor_profile_id"))
            if resolved_chat_id else None
        )
        recent_runs_task = (
            asyncio.create_task(task_store.list_runs(task_id=task.id, limit=6))
            if task else None
        )
        runnable_tasks_task = asyncio.create_task(_load_runnable_tasks_snapshot(task_store, limit=8))
        waiting_tasks_task = asyncio.create_task(task_store.list_tasks(status="waiting", limit=5))
        durable_failure_task = asyncio.create_task(_load_durable_failure_snapshot(task_store))
        context_facts_task = asyncio.create_task(_load_context_facts_snapshot(
            task_store,
            task,
            exclude_prefixes=self._cfg.thresholds.fact_context_exclude_prefixes,
            task_limit=self._cfg.thresholds.fact_context_task_limit,
            global_limit=self._cfg.thresholds.fact_context_global_limit,
            priority_prefixes=self._cfg.thresholds.fact_context_priority_prefixes,
            priority_limit=self._cfg.thresholds.fact_context_priority_limit,
            recent_scan_multiplier=self._cfg.thresholds.fact_context_recent_scan_multiplier,
            recent_scan_min=self._cfg.thresholds.fact_context_recent_scan_min,
        ))
        probes_task = (
            asyncio.create_task(self._probe_manager.list_probes())
            if self._probe_manager else None
        )
        failures_task = asyncio.create_task(
            task_store.list_failures_for_task(str(task.id), self._cfg.memory.failure_limit)
            if task else task_store.list_failures(self._cfg.memory.failure_limit)
        )

        # 统一收口并发上下文抓取，避免前一路异常时后续任务异常/结果无人消费。
        parallel_fetches: list[tuple[str, Any]] = [
            ("episodic_text", episodic_text_future),
        ]
        if chat_continuity_future is not None:
            parallel_fetches.append(("chat_continuity", chat_continuity_future))
        if recent_turns_future is not None:
            parallel_fetches.append(("recent_turns", recent_turns_future))
        if chat_memories_future is not None:
            parallel_fetches.append(("chat_memories", chat_memories_future))
        if speaker_hint_task is not None:
            parallel_fetches.append(("speaker_hint", speaker_hint_task))
        if recent_runs_task is not None:
            parallel_fetches.append(("recent_runs", recent_runs_task))
        parallel_fetches.extend([
            ("runnable_tasks", runnable_tasks_task),
            ("waiting_tasks", waiting_tasks_task),
            ("durable_failure_snapshot", durable_failure_task),
            ("context_facts", context_facts_task),
            ("failures", failures_task),
        ])
        if probes_task is not None:
            parallel_fetches.append(("probes", probes_task))

        parallel_results = await asyncio.gather(
            *(awaitable for _, awaitable in parallel_fetches),
            return_exceptions=True,
        )
        parallel_data: dict[str, Any] = {}
        parallel_error: BaseException | None = None
        for (name, _), value in zip(parallel_fetches, parallel_results, strict=False):
            if isinstance(value, BaseException):
                if parallel_error is None:
                    parallel_error = value
                continue
            parallel_data[name] = value
        if parallel_error is not None:
            raise parallel_error

        episodic_text = parallel_data["episodic_text"]
        chat_continuity_text = parallel_data.get("chat_continuity", "")
        recent_turns = parallel_data.get("recent_turns", [])
        chat_memories = parallel_data.get("chat_memories", [])
        speaker_hint = parallel_data.get("speaker_hint", ("", False))
        recent_runs = parallel_data.get("recent_runs", [])
        runnable_tasks = parallel_data["runnable_tasks"]
        waiting_tasks = parallel_data["waiting_tasks"]
        durable_failure_snapshot = parallel_data["durable_failure_snapshot"]
        context_facts = parallel_data["context_facts"]
        probes = parallel_data.get("probes", [])
        failures = parallel_data["failures"]

        if chat_continuity_text.strip() == episodic_text.strip():
            chat_continuity_text = ""
        similar_tasks = await _load_similar_tasks_snapshot(
            task_store, search_query, active_task=task, limit=5,
            min_score=self._cfg.thresholds.task_similarity_context_score,
        )
        episodic_search = (
            await _el.run_in_executor(None, episodic.search, search_query, 16000, task_id_str)
            if task_id_str and search_query else ""
        )
        if episodic_search and episodic_search not in episodic_text:
            episodic_text = episodic_text + "\n\n[跨任务检索命中]\n" + episodic_search
        _log.info("[context] episodic search=%r cross_task_hit=%s",
                  (search_query or "")[:50], bool(episodic_search))

        resolved_entities = await self._ref_resolver.resolve(user_message, semantic, episodic) if user_message else []
        cached_speaker_id = ""
        if isinstance(speaker_hint, tuple) and len(speaker_hint) >= 2 and speaker_hint[1]:
            cached_speaker_id = str(speaker_hint[0] or "").strip()
        interlocutor_continuity_text = ""
        if cached_speaker_id:
            interlocutor_continuity_text = await _el.run_in_executor(
                None,
                episodic.load_for_interlocutor_context,
                cached_speaker_id,
                self._cfg.memory.episodic_max_chars,
            )
        resolved_speaker = (
            await self._ref_resolver.resolve_current_speaker(
                user_message,
                semantic,
                chat_id=resolved_chat_id or "",
                recent_turns=recent_turns,
                chat_continuity=chat_continuity_text,
                interlocutor_continuity=interlocutor_continuity_text,
                cached_profile_id=cached_speaker_id,
                source_hint=str(getattr(task, "source", "") or "") if task else "",
            )
            if user_message else None
        )
        if resolved_speaker is not None:
            await self._ref_resolver.remember_speaker(
                resolved_speaker,
                semantic,
                task_store,
                message=user_message,
                chat_id=resolved_chat_id or "",
                task_id=task.id if task else None,
                source_hint=str(getattr(task, "source", "") or "") if task else "",
            )
            if resolved_speaker.node_id != cached_speaker_id or not interlocutor_continuity_text:
                interlocutor_continuity_text = await _el.run_in_executor(
                    None,
                    episodic.load_for_interlocutor_context,
                    resolved_speaker.node_id,
                    self._cfg.memory.episodic_max_chars,
                )
        entity_section = self._ref_resolver.format_section(resolved_entities)
        current_interlocutor_profile_section = self._ref_resolver.format_speaker_section(resolved_speaker)
        current_interlocutor_continuity_section = _fmt_interlocutor_continuity(interlocutor_continuity_text)

        # 动态构建检索锚点：结合任务、用户原话与近期失败，提升语义记忆命中率
        anchors: list[str] = []
        if task:
            # 优先级：下一步 > 目标 > 标题
            primary_anchor = task.next_step or task.goal or task.title
            if primary_anchor:
                anchors.append(primary_anchor)
            # 身份锚：确保跨会话认人
            task_source = str(getattr(task, "source", "") or "")
            if task_source and task_source not in anchors:
                anchors.append(task_source)

        # 用户消息锚：截取关键片段
        if user_message and user_message not in anchors:
            anchors.append(user_message[:100])

        if resolved_chat_id:
            chat_anchor = _chat_memory_tag(resolved_chat_id)
            if chat_anchor not in anchors:
                anchors.append(chat_anchor)

        if resolved_speaker is not None:
            for anchor in [resolved_speaker.title, *resolved_speaker.search_anchors, f"interlocutor:{resolved_speaker.node_id}"]:
                normalized_anchor = str(anchor or "").strip()
                if normalized_anchor and normalized_anchor not in anchors:
                    anchors.append(normalized_anchor)

        # 失败模式锚：若近期有失败，优先检索相关教训
        if failures:
            anchors.append(failures[0].kind)

        # 执行语义检索：使用动态锚点集合
        memories = await _el.run_in_executor(
            None, semantic.retrieve_multi_anchor, anchors, self._cfg.memory.semantic_top_k
        )
        semantic_top_score = max(
            (
                float(item.get("score") or 0.0)
                for item in memories
                if isinstance(item.get("score"), (int, float))
            ),
            default=0.0,
        )
        should_use_daily_fallback = bool(search_query) and not episodic_search and (
            not memories or semantic_top_score < self._cfg.memory.daily_recall_semantic_score_threshold
        )
        if should_use_daily_fallback:
            recent_daily = await _el.run_in_executor(
                None,
                episodic.search_recent_daily,
                search_query,
                self._cfg.memory.daily_recall_days,
                self._cfg.memory.daily_recall_max_chars,
            )
        else:
            recent_daily = "（长期记忆或情节命中充分，本轮不额外注入 daily 补短）"
        _log.info("[context] semantic hits=%d anchors=%r",
                  len(memories), [a[:40] for a in anchors[:3]])
        _log.info(
            "[context] daily fallback=%s semantic_top_score=%.3f episodic_hit=%s",
            should_use_daily_fallback,
            semantic_top_score,
            bool(episodic_search),
        )
        recall_mode = "no_relevant_memory"
        if memories and semantic_top_score >= self._cfg.memory.daily_recall_semantic_score_threshold:
            recall_mode = "long_term_primary"
        elif episodic_search:
            recall_mode = "episodic_cross_task"
        elif should_use_daily_fallback and recent_daily and "不额外注入" not in recent_daily:
            recall_mode = "daily_gap_fill"

        axioms_fact, ethos_fact = await asyncio.gather(
            task_store.get_fact("soul:hard_axioms"),
            task_store.get_fact("soul:ethos_baseline"),
        )
        axioms_val, _ = axioms_fact
        ethos_val, _ = ethos_fact
        soul_section = _fmt_soul(
            axioms_val,
            ethos_val,
            json.dumps(self._cfg.soul.ethos.baseline.as_dict(), ensure_ascii=False, sort_keys=True),
            json.dumps(self._cfg.soul.hard_axioms, ensure_ascii=False),
        )

        _wm_items = wm.get_top(15)
        all_skills = self._skills.all_skills()
        skills: list[Skill] = []
        self._last_selected_skills = []
        _log.debug("[skill] catalog-only mode: runtime 不预选候选 skill，由模型自行 activation")

        ctx = {
            "task_section": _fmt_task(task),
            "task_facts_section": _fmt_context_facts(context_facts),
            "waiting_tasks_section": _fmt_waiting_tasks(waiting_tasks),
            "runnable_tasks_section": _fmt_runnable_tasks(runnable_tasks, active_task_id=task.id if task else None),
            "similar_tasks_section": _fmt_similar_tasks(similar_tasks),
            "recent_runs_section": _fmt_recent_runs(recent_runs),
            "emotion_valence": f"{emotion.valence:.2f}",
            "emotion_arousal": f"{emotion.arousal:.2f}",
            "emotion_dominant": emotion.dominant or "（未确定）",
            "emotion_regulation": f"{emotion.regulation.strategy}（{emotion.regulation.reason}）" if emotion.regulation.reason else emotion.regulation.strategy,
            "wm_section": _fmt_wm(_wm_items, wm_count=len(wm), wm_capacity=wm._capacity,
                                   wm_tokens=wm.total_tokens, wm_token_budget=wm._token_budget),
            "failures_section": _fmt_failures(failures),
            "durable_failure_section": _fmt_durable_failures(durable_failure_snapshot),
            "episodic_section": episodic_text or "（暂无情节记忆）",
            "chat_continuity_section": _fmt_chat_continuity(chat_continuity_text),
            "current_interlocutor_profile_section": current_interlocutor_profile_section,
            "current_interlocutor_continuity_section": current_interlocutor_continuity_section,
            "daily_continuity_section": recent_daily or "（近两日无相关 daily 补短）",
            "entity_section": entity_section,
            "chat_memory_section": _fmt_chat_memories(chat_memories),
            "memories_section": _fmt_memories(memories),
            "memory_recall_section": _fmt_memory_recall(
                query=search_query or "",
                anchors=anchors,
                chat_id=resolved_chat_id or "",
                chat_memory_hits=len(chat_memories),
                memories=memories,
                semantic_top_score=semantic_top_score,
                episodic_cross_task_hit=bool(episodic_search),
                daily_fallback_used=bool(should_use_daily_fallback and recent_daily and "不额外注入" not in recent_daily),
                recall_mode=recall_mode,
            ),
            "memory_system_section": _fmt_memory_system(
                runtime_db=str(self._cfg.db_path),
                memory_dir=str(self._cfg.memory_dir),
                workspace_dir=str(self._cfg.workspace_dir),
                semantic=semantic,
                max_concurrent_ticks=self._cfg.loop.max_concurrent_ticks,
                max_tick_queue=self._cfg.loop.max_tick_queue,
            ),
            "soul_section": soul_section,
            "tools_section": _fmt_tools(effective_registry.list_manifests()),
            "shell_capabilities_section": _fmt_shell_capabilities(),
            "perception_section": _fmt_percept(percept),
            "ethos_section": _fmt_ethos(ethos_state),
            "signals_section": _fmt_judgment_signals(judgment_signals),
            "hard_boundaries_section": _fmt_hard_boundaries(hard_boundaries),
            "perception_replay_section": _fmt_perception_replay(perception_replay),
            "skills_catalog_section": _fmt_skill_catalog(all_skills),
            "primary_skill_section": _fmt_primary_skill(skills[0] if skills else None),
            "skills_section": _fmt_skills(skills),
            "cognitive_signals_section": _fmt_cognitive_signals(cognitive_signals),
            "probe_sensors_section": _fmt_probe_sensors(probes),
            "blind_spot_section": _fmt_blind_spots(probes),
            "self_model_section": fmt_self_model(self._executor.self_model),
            "team_view": _build_team_view_from_cfg(self._cfg),
            "model_routing_section": self._build_model_routing_section(
                phase=phase,
                user_message=user_message,
                current_action=current_action,
                tool_history=tool_history,
                effective_thinking=effective_thinking or self._cfg.thinking,
                routing_overrides=routing_overrides,
                registry=effective_registry,
            ),
            "current_time_section": _fmt_current_time(),
            "config_section": _fmt_config_snapshot(self._cfg),
            "user_message": user_message or "",
        }
        ctx["chat_history_section"] = _fmt_chat_history(
            recent_turns,
            max_chars=self._cfg.thresholds.chat_history_max_chars,
        )
        _validate_context_schema(ctx)
        ctx = apply_context_budget(
            ctx,
            self._cfg.judgment_input_token_budget(),
            skill_min_tokens=self._cfg.thresholds.skill_min_budget_tokens,
        )
        # 注入上下文预算信息到自我模型，供后续判断感知上下文压力
        budget = self._cfg.judgment_input_token_budget()
        if budget:
            used = sum(len(v) for v in ctx.values())
            self._executor.self_model.context_budget = f"{budget // 1000}K" if budget >= 1000 else str(budget)
            self._executor.self_model.context_pressure = min(1.0, used / max(budget, 1))
        return _fill_template(self._judgment_template, ctx)

