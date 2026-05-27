"""core/metabolic/proposal.py — 候选状态写入提案。

公理 A5：外围器官与子灵只能提交候选写入（StateProposal），不能直接定稿。
代谢器官（MetabolicEngine）负责验证后落定。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StateProposal:
    """一次状态写入候选提案。

    Attributes
    ----------
    op:
        操作类型。当前支持：
        - ``"set_fact"``    写入/更新一条 fact
        - ``"create_task"`` 创建任务（Phase 2 扩展）
        - ``"update_task"`` 更新任务状态（Phase 2 扩展）
        - ``"add_memory"``  写入语义/情节记忆节点（Phase 2 扩展）
        - ``"soul_change"`` 人格/灵魂层变更（Phase 3 扩展）
    key:
        写入目标的 key（set_fact 场景）或实体 ID（task/memory 场景）。
    value:
        写入的值。类型依 op 而定（set_fact 为 str/None，其他为 dict/dataclass）。
    scope:
        fact 的作用域（``"task"`` | ``"system"``），仅 set_fact 场景有效。
    source:
        提交来源标识（如 ``"loop/tick"``、``"execution"``、``"reference"``），
        用于生命史账本溯源，不影响落地行为。
    """
    op: str
    key: str
    value: Any
    scope: str = "task"
    source: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
