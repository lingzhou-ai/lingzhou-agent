"""core/metabolic/engine.py — 代谢引擎（正式状态写入唯一出口）。

公理 A5：正式状态写入必须经过代谢器官。

Phase 1：submit() 直接调用 task_store.set_fact（行为与原有散落写入一致）。
Phase 2（当前）：
  1. 免疫器官检查（违宪则拒绝，不写入，但仍记录账本）
  2. 生命史账本追加记录（append-only）
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.immune.policy import check_tool_blocked
from core.metabolic.proposal import StateProposal

if TYPE_CHECKING:
    from store.task import TaskStore

_log = logging.getLogger("lingzhou.metabolic")


class MetabolicEngine:
    """代谢引擎：全系统唯一正式状态写入出口。

    Phase 2：先做免疫检查，通过后落地并追加生命史账本。
    """

    def __init__(self, task_store: "TaskStore") -> None:
        self._task_store = task_store

    async def submit(self, proposal: StateProposal) -> None:
        """提交候选状态写入。

        流程：
          1. 免疫器官检查（key 映射为伪工具名 "fact:<key>"）
          2. 通过 → 落地写入
          3. 无论通过/拒绝，均追加生命史账本（accepted 标记区分）
        """
        # ── Phase 2-①：免疫检查 ──────────────────────────────────────
        # set_fact 写入以 "fact:<key>" 形式过黑名单；soul_change 等高风险 op
        # 日后可在 check_tool_blocked 中新增规则，此处自动生效。
        pseudo_tool = f"fact:{proposal.key}" if proposal.op == "set_fact" else proposal.op
        block_reason = check_tool_blocked(pseudo_tool)

        accepted = block_reason is None

        if not accepted:
            _log.warning(
                "[metabolic] 免疫器官拒绝写入 key=%r op=%r source=%r reason=%s",
                proposal.key,
                proposal.op,
                proposal.source,
                block_reason,
            )
        else:
            # ── 落地写入 ──────────────────────────────────────────────
            if proposal.op == "set_fact":
                await self._task_store.set_fact(
                    proposal.key,
                    proposal.value,
                    scope=proposal.scope,
                )
                _log.debug(
                    "[metabolic] set_fact key=%r scope=%r source=%r",
                    proposal.key,
                    proposal.scope,
                    proposal.source,
                )
            else:
                _log.warning(
                    "[metabolic] 未知 op=%r，跳过（key=%r source=%r）",
                    proposal.op,
                    proposal.key,
                    proposal.source,
                )

        # ── Phase 2-②：生命史账本追加（不阻塞主流程，出错仅 warning）──
        try:
            value_str = str(proposal.value) if proposal.value is not None else ""
            await self._task_store.ledger_append(
                op=proposal.op,
                key=proposal.key,
                value=value_str,
                scope=proposal.scope,
                source=proposal.source,
                accepted=accepted,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("[metabolic] 生命史账本写入失败（不影响主流程）: %s", exc)

