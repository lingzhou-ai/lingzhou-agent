"""Task-level cortex workspace.

The short WM is intentionally aggressive; this module builds a durable task
workspace from task state, plan, recent runs, facts and failures so judgment
does not rely on a cramped recency-only context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CortexWorkspace:
    task_id: int = 0
    title: str = ""
    goal: str = ""
    status: str = ""
    current_step: str = ""
    next_step: str = ""
    plan: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


def _clip_text(text: str, max_chars: int) -> str:
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return value[: max(0, max_chars - 3)] + "..."


def _clip_for_context(text: str, max_chars: int) -> str:
    value = " ".join(str(text or "").split())
    return _clip_text(value, max_chars)


def _as_list(value: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("content") or item.get("summary") or item.get("step") or "").strip()
            status = str(item.get("status") or "").strip()
            if text and status:
                text = f"[{status}] {text}"
        else:
            text = str(item or "").strip()
        if text:
            result.append(_clip_for_context(text, 180))
        if len(result) >= limit:
            break
    return result


def _plan_from_task(task: Any) -> list[str]:
    raw_plan = task.extras.get("plan") if isinstance(getattr(task, "extras", None), dict) else None
    if not isinstance(raw_plan, list):
        return []
    result: list[str] = []
    for index, item in enumerate(raw_plan, 1):
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or "").strip()
        if not step:
            continue
        status = str(item.get("status") or "pending").strip()
        result.append(f"{index}. [{status}] {_clip_for_context(step, 140)}")
        if len(result) >= 8:
            break
    return result


def _progress_from_runs(recent_runs: list[Any], *, limit: int = 5) -> list[str]:
    result: list[str] = []
    for run in recent_runs[:limit]:
        status = str(getattr(run, "status", "") or "").strip()
        tool = str(getattr(run, "tool_name", "") or getattr(run, "run_type", "") or "").strip()
        progress = str(getattr(run, "progress", "") or "").strip()
        summary = ""
        output_json = getattr(run, "output_json", {}) or {}
        if isinstance(output_json, dict):
            summary = str(output_json.get("summary") or output_json.get("result") or "").strip()
        if not summary:
            summary = str(getattr(run, "log_text", "") or "").strip()
        text = f"run#{getattr(run, 'id', '?')} [{status}] {tool or '-'}"
        detail = progress or summary
        if detail:
            text += f": {_clip_for_context(detail, 160)}"
        result.append(text)
    return result


def _facts_as_evidence(context_facts: list[Any], *, limit: int = 6) -> list[str]:
    result: list[str] = []
    for item in context_facts[:limit]:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        key, value = item[0], item[1]
        result.append(f"{key}: {_clip_for_context(str(value or ''), 160)}")
    return result


def _failure_lines(failures: list[Any], *, limit: int = 4) -> list[str]:
    result: list[str] = []
    for failure in failures[:limit]:
        kind = str(getattr(failure, "kind", "") or "").strip()
        summary = str(getattr(failure, "summary", "") or "").strip()
        context = str(getattr(failure, "context", "") or "").strip()
        text = kind or "failure"
        if summary or context:
            text += f": {_clip_for_context(summary or context, 160)}"
        result.append(text)
    return result


def build_cortex_workspace(
    *,
    task: Any | None,
    recent_runs: list[Any] | None = None,
    context_facts: list[Any] | None = None,
    failures: list[Any] | None = None,
) -> CortexWorkspace:
    if task is None:
        return CortexWorkspace()
    result_json = getattr(task, "result_json", {}) or {}
    cortex = result_json.get("cortex") if isinstance(result_json, dict) else None
    if not isinstance(cortex, dict):
        cortex = {}
    evidence = _as_list(cortex.get("evidence"), limit=8)
    evidence.extend(_facts_as_evidence(context_facts or [], limit=max(0, 8 - len(evidence))))
    return CortexWorkspace(
        task_id=int(getattr(task, "id", 0) or 0),
        title=str(getattr(task, "title", "") or "").strip(),
        goal=str(getattr(task, "goal", "") or "").strip(),
        status=str(getattr(task, "status", "") or "").strip(),
        current_step=str(getattr(task, "current_step", "") or "").strip(),
        next_step=str(getattr(task, "next_step", "") or "").strip(),
        plan=_as_list(cortex.get("plan"), limit=8) or _plan_from_task(task),
        evidence=evidence[:8],
        progress=_as_list(cortex.get("progress"), limit=6) or _progress_from_runs(recent_runs or []),
        failures=_as_list(cortex.get("failures"), limit=4) or _failure_lines(failures or []),
        open_questions=_as_list(cortex.get("open_questions"), limit=5),
    )


def _section(title: str, lines: list[str]) -> list[str]:
    if not lines:
        return []
    return [title, *[f"- {line}" for line in lines]]


def format_cortex_workspace(workspace: CortexWorkspace) -> str:
    if workspace.task_id <= 0:
        return "（无活跃任务级皮层工作区）"
    lines = [
        f"task_id={workspace.task_id} status={workspace.status or 'unknown'}",
        f"title={_clip_text(workspace.title, 160) or '（未命名）'}",
        f"goal={_clip_text(workspace.goal, 220) or '（未指定）'}",
        f"current_step={_clip_text(workspace.current_step, 180) or '（未指定）'}",
        f"next_step={_clip_text(workspace.next_step, 180) or '（未指定）'}",
    ]
    lines.extend(_section("plan_state:", workspace.plan))
    lines.extend(_section("evidence_board:", workspace.evidence))
    lines.extend(_section("recent_progress:", workspace.progress))
    lines.extend(_section("known_failures:", workspace.failures))
    lines.extend(_section("open_questions:", workspace.open_questions))
    return "\n".join(lines)
