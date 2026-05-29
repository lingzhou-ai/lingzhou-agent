from __future__ import annotations

import json
import time
from typing import Any

from core.execution import action_key_param
from provider.catalog import lookup_model
from tools.registry import tool_has_capability

from ..output import tool_tier_mapping


def _build_model_routing_section(
    assembler: Any,
    *,
    phase: str,
    user_message: str,
    current_action: str,
    tool_history: list[dict[str, Any]] | None,
    effective_thinking: str,
    routing_overrides: dict[str, str] | None = None,
    registry: Any | None = None,
) -> str:
    effective_registry = registry or assembler._registry
    available_models: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for tier in ("reader", "reasoner", "repair"):
        _, model_ref = assembler._executor._resolve_tier_model(tier)
        key = (tier, model_ref)
        if key in seen:
            continue
        seen.add(key)
        model_id = model_ref.split("/", 1)[1] if "/" in model_ref else model_ref
        spec = lookup_model(model_id) or {}
        reasoning = bool(spec.get("reasoning"))
        health = assembler._executor._get_health(model_ref)
        override_model = (routing_overrides or {}).get(tier)
        available_models.append({
            "tier": tier,
            "model": model_ref,
            "available": assembler._executor._is_model_available(model_ref),
            "reasoning": reasoning,
            "cost_level": assembler._executor._cost_level_for_model(model_ref, reasoning),
            "latency_level": assembler._executor._latency_level_for_model(model_ref, reasoning),
            "context_window": spec.get("context_window") or assembler._cfg.context_window_tokens,
            "current_thinking": effective_thinking or assembler._cfg.thinking,
            "last_error": assembler._executor._provider_errors.get(model_ref),
            "last_error_code": health.last_code or None,
            "cooldown_remaining_sec": max(0, int(health.cooldown_until - time.time())),
            "overridden_by": override_model if override_model and override_model != model_ref else None,
        })

    task_explore_count = repeat_action_count = repeat_read_count = 0
    if tool_history:
        def _trailing_repeat_count(matcher: Any) -> int:
            count = 0
            for item in reversed(tool_history):
                if not matcher(item):
                    break
                count += 1
            return count

        task_explore_count = sum(1 for item in tool_history if any(tool_has_capability(effective_registry, str(item.get("tool") or ""), capability) for capability in ("ask_evidence", "completion_info_only", "completion_verify")))
        if len(tool_history) >= 2:
            last_tool = str(tool_history[-1].get("tool", ""))
            last_action_sig = f"{last_tool}|{action_key_param(tool_history[-1].get('params') or {})}"
            repeat_action_count = _trailing_repeat_count(lambda item: f"{str(item.get('tool', ''))}|{action_key_param(item.get('params') or {})}" == last_action_sig)
            if last_tool == "file.read":
                last_path = json.dumps(tool_history[-1].get("params", {}), ensure_ascii=False)
                repeat_read_count = _trailing_repeat_count(lambda item: str(item.get("tool", "")) == "file.read" and json.dumps(item.get("params", {}), ensure_ascii=False) == last_path)

    ask_evidence_hits = sum(1 for item in (tool_history or []) if tool_has_capability(effective_registry, str(item.get("tool") or ""), "ask_evidence") and str(item.get("result") or "").strip() and not str(item.get("result") or "").startswith("ERROR["))
    posture = "respond" if user_message else ("converge" if task_explore_count >= assembler._cfg.thresholds.task_explore_converge_after else "conserve")

    def _fmt_duration_ms(value: float) -> str:
        ms = float(value)
        return f"{ms / 1000.0:g}s" if ms >= 1000 else f"{ms:g}ms"

    with_task_bounds = assembler._cfg.loop.idle_with_task_bounds
    no_task_bounds = assembler._cfg.loop.idle_no_task_bounds
    with_task_bounds_text = f"{_fmt_duration_ms(with_task_bounds[0])}-{_fmt_duration_ms(with_task_bounds[1])}"
    no_task_bounds_text = f"{_fmt_duration_ms(no_task_bounds[0])}-{_fmt_duration_ms(no_task_bounds[1])}"
    default_gap_text = f"有任务 {_fmt_duration_ms(assembler._cfg.loop.active_idle_gap)}，无任务 {_fmt_duration_ms(assembler._cfg.loop.max_idle_gap)}"
    capability_mapping: dict[str, list[str]] = {}
    current_action_caps: list[str] = []
    tool_history_compact_threshold = assembler._cfg.thresholds.continue_tool_history_compact_threshold
    tool_history_keep_last = assembler._cfg.thresholds.continue_tool_history_keep_last
    tool_history_count = len(tool_history or [])
    for manifest in effective_registry.list_manifests():
        for cap in manifest.capabilities:
            capability_mapping.setdefault(cap, []).append(manifest.name)
        if manifest.name == current_action:
            current_action_caps = sorted(manifest.capabilities)

    payload = {
        "active_overrides": routing_overrides or {},
        "available_models": available_models,
        "tool_tier_mapping": tool_tier_mapping(effective_registry),
        "tool_capability_mapping": {k: sorted(v) for k, v in capability_mapping.items()},
        "current_action_capabilities": current_action_caps,
        "continue_phase_policy": {"tool_history_count": tool_history_count, "tool_history_compact_threshold": tool_history_compact_threshold, "tool_history_keep_last": tool_history_keep_last, "tool_history_will_compact_next": tool_history_count >= tool_history_compact_threshold and tool_history_count > tool_history_keep_last},
        "tier_descriptions": {"reader": "轻量感知层：适合常规状态查询、读文件、检查计划、无复杂推理的心跳 tick", "reasoner": "深度推理层：适合用户交互、要求判断、处理复杂状态、制定或调整计划", "repair": "修复层：专用于解析失败、格式错误、小修小补"},
        "delegation_guide": f"你是当前层的决策者，可以通过 model_strategy 中的字段调控下一轮行为。• next_phase_tier：reader=轻量感知，reasoner=深度推理，repair=修复。• tool_tier_mapping：runtime 当前对工具族的默认分层真相。• tool_capability_mapping：runtime 注入的工具能力真相，优先按能力标签推理。• continue_phase_policy：若 tool_history_will_compact_next=true，下一轮早期工具记录会折叠。• idle 参考：当前有任务时 {with_task_bounds_text}，无任务时 {no_task_bounds_text}。• 当前 loop 默认备用值（{default_gap_text}）。• next_idle_gap_secs / next_idle_gap_ms：必须设置其一，ms 优先。• routing_overrides：临时覆盖 tier→model 映射。• thinking_override：覆盖下一轮的 thinking 等级。",
        "budget_state": {"task_explore_count": task_explore_count, "repeat_action_count": repeat_action_count, "repeat_read_count": repeat_read_count, "ask_evidence_hits": ask_evidence_hits, "ask_evidence_budget": assembler._cfg.thresholds.ask_evidence_budget, "task_explore_converge_after": assembler._cfg.thresholds.task_explore_converge_after, "global_cost_posture": posture},
        "routing_hint": {"phase": phase, "current_action": current_action, "user_message_present": bool(user_message)},
    }
    from provider import catalog as _cat

    payload["catalog_models"] = [{"model": f"{provider_name}/{model.get('id', '')}", "provider": provider_name, "reasoning": bool(model.get("reasoning")), "context_window": model.get("context_window")} for provider_name in _cat.list_providers() for model in _cat.list_provider_models(provider_name)]
    payload["primary_provider"] = {"model": assembler._cfg.model}
    if hasattr(assembler, "_ref_resolver") and assembler._ref_resolver is not None:
        resolver = assembler._ref_resolver
        payload["reference_resolution"] = {"llm_available": resolver.llm_available, "last_error": resolver.last_llm_error, "last_error_code": resolver.last_llm_error_code}
    return json.dumps(payload, ensure_ascii=False, indent=2)
