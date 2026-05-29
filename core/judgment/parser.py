"""core/judgment/parser.py — 输出解析与纯净化层。

职责：
- 对 JudgmentOutput 做纯函数级别的修正（不依赖任何 LLM 调用）
- reply_only 模式强制、记忆诚信守卫等

与 JudgmentLayer 解耦：不知道上下文如何组装，不持有任何 provider 引用。
需要调用 LLM 进行修复（_repair_output）的逻辑保留在 executor.py。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .output import JudgmentOutput

if TYPE_CHECKING:
    from core.perception import JudgmentSignals

_MEMORY_ASSERTIVE_PHRASE_RE = re.compile(
    r"(我还?记得|我记着|你之前说过|之前你说过|你之前提过|之前你提过)"
)
_REPLY_PSEUDO_TOOLS = {"chat_reply"}


def simulate_safe_output(
    failure_count: int,
    signals: JudgmentSignals | None,
    hard_boundaries: list[str],
    reason: str = "",
) -> JudgmentOutput:
    """LLM 不可用时的确定性回退。行为原则：posture > wait。"""
    if signals and signals.posture in ("pause", "narrow"):
        return JudgmentOutput.wait(reason=f"[fallback] posture={signals.posture}, LLM 不可用: {reason}")
    return JudgmentOutput.wait(reason=f"[fallback] LLM 不可用: {reason}")


def coerce_reply_only_output(output: JudgmentOutput) -> JudgmentOutput:
    """将 continue 续判结果强制修正为 reply_only 模式（禁止 act，必须有 reply_to_user）。"""
    if not output.reply_to_user.strip():
        return JudgmentOutput.wait(reason="[reply-only] reply_to_user 不能为空")
    return JudgmentOutput(
        decision=output.decision if output.decision in {"pause", "wait"} else "wait",
        chosen_action_id="",
        params={},
        rationale=output.rationale,
        reflection=output.reflection,
        reply_to_user=output.reply_to_user,
        next_step=output.next_step,
        model_strategy=dict(output.model_strategy or {}),
    )


def normalize_reply_pseudo_tool(output: JudgmentOutput) -> JudgmentOutput:
    """将误写成工具的直接回复动作归一化回 reply 链路。"""
    tool_name = str(output.chosen_action_id or "").strip().lower()
    if output.decision != "act" or tool_name not in _REPLY_PSEUDO_TOOLS:
        return output

    reply = str(output.reply_to_user or output.speech_intent or "").strip()
    if not reply:
        return JudgmentOutput.wait(reason=f"伪工具 {tool_name!r} 缺少 reply_to_user")

    return JudgmentOutput(
        decision="wait",
        chosen_action_id="",
        params={},
        rationale=output.rationale,
        reflection=output.reflection,
        speech_intent=output.speech_intent,
        reply_to_user=reply,
        next_step=output.next_step,
        model_strategy=dict(output.model_strategy or {}),
        applied_skills=list(output.applied_skills or []),
    )


def _extract_memory_recall_mode(context_text: str) -> str:
    match = re.search(r"recall_mode:\s*([A-Za-z_]+)", context_text or "")
    return str(match.group(1)).strip() if match else ""


def _strip_memory_assertive_phrases(text: str) -> str:
    stripped = _MEMORY_ASSERTIVE_PHRASE_RE.sub("", text or "")
    stripped = re.sub(r"^[，,。；;:\s]+", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def apply_memory_honesty_guard(output: JudgmentOutput, *, context_text: str) -> JudgmentOutput:
    """记忆诚信守卫：当 reply_to_user 包含断言式记忆声明时，按 recall_mode 降级表述。"""
    reply = (output.reply_to_user or "").strip()
    if not reply or not _MEMORY_ASSERTIVE_PHRASE_RE.search(reply):
        return output

    recall_mode = _extract_memory_recall_mode(context_text)
    if recall_mode == "long_term_primary":
        return output

    stripped = _strip_memory_assertive_phrases(reply)
    if recall_mode == "episodic_cross_task":
        guarded_reply = (
            f"从跨任务情节记录看，{stripped}"
            if stripped else
            "我在跨任务情节里看到过相关线索，但这还不是稳定长期记忆。"
        )
    elif recall_mode == "daily_gap_fill":
        guarded_reply = (
            f"从近期线索看，{stripped}"
            if stripped else
            "我只在近期线索里看到相关片段，还不能把它当成稳定记忆。"
        )
    elif recall_mode == "no_relevant_memory":
        guarded_reply = (
            f"我现在没有足够稳定记忆证据，只能按当前线索判断：{stripped}"
            if stripped else
            "我现在没有足够稳定记忆证据，不能直接说自己记得这件事。"
        )
    else:
        return output

    output.reply_to_user = guarded_reply.strip()
    return output
