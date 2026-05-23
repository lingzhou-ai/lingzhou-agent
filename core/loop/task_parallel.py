"""core/loop/task_parallel.py — 任务并行执行器。

主 tick（reasoner）通过 JudgmentOutput.delegate_tasks 将独立子目标委派为
真实 Task（持久化到 task_store）。run_tasks_parallel() 用 asyncio.gather
并发执行多个 Task，每个 Task 独立调用 LLM（reader tier），结果写回 task.result_json。
全部完成后主 tick（reasoner）做统一审查决策。

架构：
  Main Tick (reasoner)
    └── decide() → delegate_tasks: [{id, goal, tools, max_rounds, params}]
          ↓ run_tasks_parallel()
    ┌────────────────────────────────────────────────────────────┐
    │  Task A  (task_store.add_task → Task)                      │
    │    decide_continue(active_task=A, reader) × max_rounds     │  asyncio.gather
    │    → task_store.update_task_result + update_status         │
    │  Task B  ...                                               │
    └────────────────────────────────────────────────────────────┘
          ↓ history_entries → main tick decide_continue(reasoner)
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from typing import TYPE_CHECKING, Any

_log = logging.getLogger("lingzhou.task_parallel")

if TYPE_CHECKING:
    from core.loop.runtime import CognitionLoop
    from memory.task_store import Task
    from tools.registry import ToolContext


class _ScopedTaskStore:
    """透传所有 TaskStore 方法，仅覆盖 get_active() 始终返回指定子任务。

    并行执行时多个 _run_one_task 协程共享同一个 ctx，
    而 _dispatch_act 内部调用 ctx.task_store.get_active() 确定当前活跃任务。
    注入 pin 后确保每个子任务的 dispatch 只操作自己的行，
    避免 run 记录、update_task_result、record_failure 写入错误任务。
    """

    def __init__(self, inner: Any, pinned: "Task") -> None:
        self._inner = inner
        self._pinned = pinned

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def get_active(self) -> "Task":
        return self._pinned


async def _run_one_task(
    task: "Task",
    spec: dict[str, Any],
    ctx: "ToolContext",
    loop: "CognitionLoop",
) -> dict[str, Any]:
    """运行单个 Task 的 judgment 循环（reader tier），结果写回 task_store。

    返回 tool_history 格式的 entry，供主 tick decide_continue() 审查。
    """
    tools: list[str] = spec.get("tools") or []
    max_rounds: int = int(spec.get("max_rounds") or 10)
    spec_id: str = str(spec.get("id") or task.id)

    # 并发安全：为本子任务创建隔离的 ToolContext，确保 _dispatch_act 内的
    # get_active() 始终返回本子任务，而不是兄弟任务或父任务。
    scoped_ctx = dataclasses.replace(ctx, task_store=_ScopedTaskStore(ctx.task_store, task))

    # 首条注入任务目标（让 decide_continue 知道当前目标）
    init_parts = [f"[任务 {spec_id}] 目标: {task.goal}"]
    if spec.get("params"):
        init_parts.append(f"上下文: {json.dumps(spec['params'], ensure_ascii=False)}")
    if tools:
        init_parts.append(f"可用工具限定: {tools}")

    tool_history: list[dict[str, Any]] = [{
        "tool": "task.init",
        "params": {},
        "result": "\n".join(init_parts),
        "summary": f"任务目标: {task.goal}",
        "error": "",
        "status": "ok",
    }]
    final_rationale = ""
    terminal_decision = "wait"
    error = ""

    for round_i in range(max_rounds):
        try:
            output = await loop._judgment.decide_continue(
                tool_history=tool_history,
                user_message=task.goal if round_i == 0 else "",
                active_task=task,
                prefer_tier="reader",
            )
        except Exception as exc:
            error = str(exc)
            _log.warning("[task_parallel:%s] decide_continue 失败(round=%d): %s", spec_id, round_i, exc)
            break

        terminal_decision = output.decision or terminal_decision
        final_rationale = output.rationale or ""

        if output.decision != "act":
            _log.info("[task_parallel:%s] 结束 round=%d decision=%s", spec_id, round_i, output.decision)
            break

        tool_name = output.chosen_action_id or ""
        if tools and tool_name not in tools:
            _log.info("[task_parallel:%s] 工具 %r 不在白名单，停止", spec_id, tool_name)
            break

        result = await loop._execution.dispatch(output, scoped_ctx)
        tool_history.append({
            "tool": tool_name,
            "params": output.params,
            "result": result.summary or "",
            "summary": result.summary or "",
            "error": result.error or "",
            "status": "error" if result.error else "ok",
        })
        _log.info("[task_parallel:%s] round=%d tool=%s ok=%s", spec_id, round_i, tool_name, not result.error)

        if result.error:
            error = result.error
            break

    # 将结果写回 task_store（持久化）
    ok_steps = sum(1 for h in tool_history[1:] if not h.get("error"))
    result_data = {
        "summary": final_rationale,
        "error": error,
        "rounds": len(tool_history) - 1,
        "ok_steps": ok_steps,
        "terminal_decision": terminal_decision,
    }
    await loop._task_store.update_task_result(task.id, result_data)
    if error:
        await loop._task_store.update_status(task.id, "failed")
    elif terminal_decision in {"wait", "pause"}:
        wait_key = str(getattr(task, "parent_task_id", "") or "")
        next_step = (str(getattr(task, "next_step", "") or "").strip() or (final_rationale or "").strip() or None)
        await loop._task_store.mark_waiting(
            task.id,
            wait_kind="task",
            wait_key=wait_key,
            wait_json={
                "wait_kind": "task",
                "wait_key": wait_key,
                "terminal_decision": terminal_decision,
            },
            next_step=next_step,
        )
    else:
        await loop._task_store.update_status(task.id, "done")

    # 构建返回给主 tick 的 history entry
    steps_text = "\n".join(
        f"  [{h['tool']}] {h.get('result', '')[:200]}"
        for h in tool_history[1:]
    )
    result_text = (
        f"目标: {task.goal}\n"
        f"最终决策: {terminal_decision}\n"
        f"结论: {final_rationale or '(无结论)'}\n"
        f"步骤:\n{steps_text or '  (无步骤)'}"
    )
    if error:
        result_text += f"\n错误: {error}"

    summary_prefix = f"[{spec_id}/task:{task.id}]"
    if error:
        summary = f"{summary_prefix} error: {(error or final_rationale or '(无结论)')[:200]}"
    elif terminal_decision in {"wait", "pause"}:
        summary = f"{summary_prefix} {terminal_decision}: {(final_rationale or '(无结论)')[:200]}"
    else:
        summary = f"{summary_prefix} {ok_steps} 步完成: {(final_rationale or '(无结论)')[:200]}"

    entry_status = "error" if error else (terminal_decision if terminal_decision in {"wait", "pause"} else "ok")
    return {
        "tool": f"task.parallel.{spec_id}",
        "params": {"goal": task.goal, "task_id": task.id},
        "result": result_text,
        "summary": summary,
        "error": error,
        "status": entry_status,
    }


async def run_tasks_parallel(
    specs: list[dict[str, Any]],
    ctx: "ToolContext",
    loop: "CognitionLoop",
    parent_task_id: int | None = None,
) -> list[dict[str, Any]]:
    """创建真实 Task 并并行执行，返回 tool_history 格式的 entry 列表。

    每个 spec 对应一个新 Task（持久化到 task_store），
    所有 Task 通过 asyncio.gather 并发执行（各自用 reader tier 调 LLM），
    结果写入 task.result_json 后汇总返回，供主 tick gate decision 审查。
    """
    valid_specs = [s for s in specs if isinstance(s, dict) and s.get("id") and s.get("goal")]
    if not valid_specs:
        return []

    _log.info("[task_parallel] 并行启动 %d 个任务: %s", len(valid_specs), [s["id"] for s in valid_specs])

    # 先顺序创建所有 Task（写 DB 不适合并发）
    tasks: list[tuple["Task", dict]] = []
    for spec in valid_specs:
        title = f"[并行:{spec['id']}] {spec['goal'][:60]}"
        task_id = await loop._task_store.add_task(
            title,
            str(spec["goal"]),
            priority="normal",
            source="internal",
            parent_task_id=str(parent_task_id) if parent_task_id else "",
            next_step=str(spec["goal"]),
        )
        task = await loop._task_store.get_task_by_id(task_id)
        if task:
            tasks.append((task, spec))

    # 并发执行所有任务
    results = await asyncio.gather(*[
        _run_one_task(task, spec, ctx, loop)
        for task, spec in tasks
    ])
    return list(results)
