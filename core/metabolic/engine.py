"""core/metabolic/engine.py — 代谢引擎（正式状态写入唯一出口）。

公理 A5：正式状态写入必须经过代谢器官。

当前阶段（Phase 1）：MetabolicEngine.submit() 直接调用 task_store.set_fact，
行为与原有散落写入完全一致。接口就位后，Phase 2 开始逐步将散落的 ~40 处
set_fact 收归到此处，并在此加入免疫检查与生命史账本。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.metabolic.proposal import StateProposal

if TYPE_CHECKING:
    from store.task import TaskStore

_log = logging.getLogger("lingzhou.metabolic")


class MetabolicEngine:
    """代谢引擎：全系统唯一正式状态写入出口。

    Phase 1：直接落地（行为与 task_store.set_fact 一致）。
    Phase 2：加入免疫检查 + 生命史账本（只追加）。
    """

    def __init__(self, task_store: "TaskStore") -> None:
        self._task_store = task_store

    async def submit(self, proposal: StateProposal) -> None:
        """提交候选状态写入，由代谢引擎决定是否落定。

        当前阶段直接落地；后续版本将在此加入：
          1. 免疫器官检查（违宪则拒绝）
          2. 生命史账本追加记录
        """
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
            # Phase 2+ 的其他 op 类型在此扩展
            _log.warning(
                "[metabolic] 未知 op=%r，跳过（key=%r source=%r）",
                proposal.op,
                proposal.key,
                proposal.source,
            )
