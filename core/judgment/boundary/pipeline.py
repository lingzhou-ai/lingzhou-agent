"""判断输出边界流水线：解析修复 + 形态归一化。"""
from __future__ import annotations

from typing import Any

from core.judgment.boundary.normalize import normalize_action_shape, normalize_reply_pseudo_tool
from core.judgment.output import JudgmentOutput

_PROBLEM_SOLVING_GUARD_ACTIVE = "### 通用问题解决守卫"
_PROBLEM_SOLVING_ALLOWED_ACTIONS = {"task.workbench", "task.amend"}


def _problem_solving_guard_active(context_text: str) -> bool:
    marker_index = context_text.find(_PROBLEM_SOLVING_GUARD_ACTIVE)
    if marker_index < 0:
        return False
    next_section = context_text.find("\n### ", marker_index + len(_PROBLEM_SOLVING_GUARD_ACTIVE))
    section = context_text[marker_index:] if next_section < 0 else context_text[marker_index:next_section]
    return "guard=active" in section


def _action_first_must_act(context_text: str) -> bool:
    marker = "action_first:"
    marker_index = context_text.find(marker)
    if marker_index < 0:
        return False
    next_section = context_text.find("\n### ", marker_index + len(marker))
    section = context_text[marker_index:] if next_section < 0 else context_text[marker_index:next_section]
    return "must_act=yes" in section


def _action_allowed_by_problem_solving_guard(output: JudgmentOutput) -> bool:
    if output.decision != "act":
        return False
    if output.chosen_action_id:
        return output.chosen_action_id in _PROBLEM_SOLVING_ALLOWED_ACTIONS
    if output.parallel_actions:
        action_ids = {
            str(item.get("action_id") or "").strip()
            for item in output.parallel_actions
            if str(item.get("action_id") or "").strip()
        }
        return bool(action_ids) and action_ids.issubset(_PROBLEM_SOLVING_ALLOWED_ACTIONS)
    return False


def enforce_problem_solving_guard(output: JudgmentOutput, *, context_text: str) -> JudgmentOutput:
    """Prevent non-workbench actions while the generic problem-solving guard is active."""
    if not _problem_solving_guard_active(context_text):
        return output
    if _action_first_must_act(context_text) and output.decision == "act":
        return output
    if _action_allowed_by_problem_solving_guard(output):
        return output
    return JudgmentOutput(
        decision="wait",
        rationale=(
            "通用问题解决守卫已触发：继续执行或直接回复前，必须先用 "
            "task.workbench 固化 domain/intent/hypothesis/capabilities/"
            "experiments_or_evidence/next_verification/completion_checks；"
            "若用户纠正改变了任务定义，先 task.amend。"
        ),
        reflection=output.reflection,
        next_step=output.next_step,
        model_strategy=dict(output.model_strategy or {}),
        applied_skills=list(output.applied_skills or []),
    )


async def normalize_judgment_output(
    executor: Any,
    output: JudgmentOutput,
    *,
    context_text: str,
    raw: str,
    record_parse_failure: Any | None = None,
    registry: Any | None = None,
    allow_delegate_tasks: bool = False,
) -> JudgmentOutput:
    """在输出进入执行层前完成边界校验与归一化。"""
    if output.rationale.startswith("LLM 输出解析失败"):
        repaired = await executor._repair_output(context_text, raw)
        if repaired is not None:
            output = repaired
        elif record_parse_failure is not None:
            await record_parse_failure("judgment_parse", output.rationale)

    output = normalize_reply_pseudo_tool(output)
    output = enforce_problem_solving_guard(output, context_text=context_text)
    return normalize_action_shape(
        output,
        registry=registry,
        allow_delegate_tasks=allow_delegate_tasks,
    )
