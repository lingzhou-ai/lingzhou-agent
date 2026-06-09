"""Action-first task intent capture for generic problem solving."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_URL_RE = re.compile(r"https?://[^\s，。；、）)】>\"']+")
_ABS_PATH_RE = re.compile(r"(?:~|/Users/|/tmp/|/var/|/etc/|/opt/|/root/)[^\s，。；、）)】>\"']*")
_COMMAND_HINT_RE = re.compile(
    r"(?:^|\s)(git|curl|wget|npm|pnpm|yarn|python|pytest|ruff|mvn|docker|kubectl|ssh|scp)\s+[^\n，。；]+"
)

_EXECUTE_MARKERS = (
    "执行",
    "运行",
    "下载",
    "拉取",
    "写入",
    "覆盖",
    "更新",
    "配置",
    "重载",
    "切换",
    "推送",
    "提交",
    "测试",
    "验证",
    "确认",
    "检查",
    "查一下",
    "看一下",
    "解决",
    "修复",
    "继续",
    "重试",
    "推进",
    "实现",
    "改",
    "补",
)
_STATUS_MARKERS = (
    "好了吗",
    "完成了吗",
    "下载好了吗",
    "推了吗",
    "推送了吗",
    "测试通过了吗",
    "状态",
)
_ANALYSIS_MARKERS = (
    "为什么",
    "原因",
    "分析",
    "对比",
    "局限",
    "怎么设计",
    "如何设计",
    "方案",
    "架构",
)


@dataclass(frozen=True)
class ActionFirstSignal:
    intent: str = "unknown"
    must_act: bool = False
    captured_inputs: list[dict[str, str]] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    minimum_next_action: str = ""


def _clip_text(value: Any, *, limit: int = 260) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _dedupe_inputs(items: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        kind = str(item.get("kind") or "").strip()
        value = str(item.get("value") or "").strip()
        if not kind or not value:
            continue
        key = (kind, value)
        if key in seen:
            continue
        seen.add(key)
        result.append({"kind": kind, "value": _clip_text(value, limit=260)})
        if len(result) >= 8:
            break
    return result


def extract_action_first_signal(user_message: str) -> ActionFirstSignal:
    """Classify whether a user turn should force at least one verifiable action."""
    text = str(user_message or "").strip()
    if not text:
        return ActionFirstSignal()

    inputs: list[dict[str, str]] = []
    for url in _URL_RE.findall(text):
        inputs.append({"kind": "url", "value": url.rstrip("，。；、")})
    for path in _ABS_PATH_RE.findall(text):
        inputs.append({"kind": "path", "value": path.rstrip("，。；、")})
    for match in _COMMAND_HINT_RE.finditer(text):
        inputs.append({"kind": "command", "value": match.group(0).strip()})
    captured_inputs = _dedupe_inputs(inputs)

    markers: list[str] = []
    execute_like = _has_any(text, _EXECUTE_MARKERS)
    status_like = _has_any(text, _STATUS_MARKERS)
    analysis_like = _has_any(text, _ANALYSIS_MARKERS)
    if execute_like:
        markers.append("execute_marker")
    if status_like:
        markers.append("status_query")
    if analysis_like:
        markers.append("analysis_marker")
    if captured_inputs:
        markers.append("strong_input")

    must_act = bool((execute_like or status_like) and not (analysis_like and not captured_inputs))
    if captured_inputs and execute_like:
        must_act = True
    intent = "execute" if must_act else ("analyze" if analysis_like else "unknown")

    if status_like:
        minimum_next_action = "检查已有运行/文件/远端/服务状态；若未完成，继续执行最小验证动作。"
    elif captured_inputs:
        minimum_next_action = "先对用户给定的强输入做最小可验证动作，不要只记录或承诺下一轮处理。"
    elif must_act:
        minimum_next_action = "本轮至少执行一个能产生新证据的工具动作。"
    else:
        minimum_next_action = ""

    return ActionFirstSignal(
        intent=intent,
        must_act=must_act,
        captured_inputs=captured_inputs,
        markers=markers,
        minimum_next_action=minimum_next_action,
    )


def build_action_first_cortex_patch(
    *,
    existing_cortex: dict[str, Any] | None,
    user_message: str,
) -> dict[str, Any]:
    """Return a result_json patch that persists action-first task state."""
    signal = extract_action_first_signal(user_message)
    if not signal.markers and not signal.captured_inputs:
        return {}
    cortex = dict(existing_cortex or {})
    previous_inputs = cortex.get("captured_inputs")
    inputs = _dedupe_inputs([
        *signal.captured_inputs,
        *(previous_inputs if isinstance(previous_inputs, list) else []),
    ])
    if inputs:
        cortex["captured_inputs"] = inputs

    action_first = dict(cortex.get("action_first") if isinstance(cortex.get("action_first"), dict) else {})
    action_first.update({
        "intent": signal.intent,
        "must_act": signal.must_act,
        "markers": signal.markers,
        "latest_user_message": _clip_text(user_message, limit=300),
    })
    if signal.minimum_next_action:
        action_first["minimum_next_action"] = signal.minimum_next_action
    cortex["action_first"] = action_first
    return {"cortex": cortex}
