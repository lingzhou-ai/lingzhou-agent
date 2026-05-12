"""core/execution.py — 执行层。

职责：
- 接收 JudgmentOutput，dispatch 到具体工具
- 处理 act / pause / wait 三种决策
- 失败时写入 failures 表（绑定当前任务 ID，P2-B 原则）
- 返回 ToolResult 给 loop 层整合
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tools.registry import ToolResult, ToolContext

_log = logging.getLogger("lingzhou.execution")

if TYPE_CHECKING:
    from core.config import Config
    from core.judgment import JudgmentOutput
    from memory.working import WorkingMemory, WMItem
    from memory.task_store import TaskStore
    from tools.registry import ToolRegistry


class ExecutionLayer:
    def __init__(self, registry: "ToolRegistry", cfg: "Config") -> None:
        self._registry = registry
        self._cfg = cfg

    async def dispatch(self, action: "JudgmentOutput", ctx: ToolContext) -> ToolResult:
        """根据 decision 类型分发执行。"""
        match action.decision:
            case "wait":
                return ToolResult(
                    summary=f"wait: {action.rationale[:200]}",
                    skipped=True,
                    kind="wait",
                    priority=0.3,
                )
            case "pause":
                from memory.working import WMItem
                ctx.wm.add(WMItem(
                    kind="caution",
                    content=f"pause: {action.rationale[:300]}",
                    priority=0.9,
                ))
                return ToolResult(
                    summary=f"pause: {action.rationale[:200]}",
                    skipped=True,
                    kind="pause",
                    priority=0.9,
                )
            case "act":
                return await self._dispatch_act(action, ctx)
            case _:
                return ToolResult(
                    summary=f"未知决策类型: {action.decision!r}",
                    skipped=True,
                    kind="error",
                )

    async def _dispatch_act(self, action: "JudgmentOutput", ctx: ToolContext) -> ToolResult:
        entry = self._registry.get(action.chosen_action_id)
        if not entry:
            return ToolResult(
                summary=f"工具不存在: {action.chosen_action_id!r}",
                error="ToolNotFound",
                skipped=True,
                kind="error",
            )

        if self._cfg.loop.debug:
            _log.debug("[exec] %s params=%s", action.chosen_action_id, action.params)
        _log.info("[exec] %s", action.chosen_action_id)

        try:
            result = await entry.handler(action.params, ctx)
        except Exception as exc:
            result = ToolResult(
                summary=f"工具执行异常: {exc}",
                evidence=str(exc),
                error=str(exc),
                kind="execute_result",
            )

        # 失败时写入 failures 表，绑定当前任务（P2-B 任务边界原则）
        if result.error and not result.skipped:
            task = await ctx.task_store.get_active()
            task_id = str(task.id) if task else ""
            await ctx.task_store.record_failure(
                kind=action.chosen_action_id,
                summary=result.summary[:300],
                context=result.evidence[:200],
                task_id=task_id,
            )

        return result
