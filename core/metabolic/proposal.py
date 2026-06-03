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
        当前支持：
        - ``"set_fact"``    写入/更新一条 fact
        - ``"delete_fact"`` 删除一条 fact
        - ``"create_task"`` 创建任务
        - ``"update_task_status"`` 更新任务状态/步骤
        - ``"mark_task_waiting"`` 将任务切入 waiting
        - ``"resume_task"`` 恢复 waiting/blocked 任务
        - ``"update_task_data"`` 更新任务 extras
        - ``"amend_task"`` 修正任务定义
        - ``"update_task_result"`` 累积写入任务 result_json（用于 run/result 生命周期）
        - ``"add_semantic_memory"`` 写入一条长期语义记忆节点
        - ``"soul_change"`` 写入人格/灵魂相关 fact（要求 key 以 ``soul:`` 开头）
        - ``"add_run"`` 创建一条 run
        - ``"update_run"`` 更新一条 run
    key:
        写入目标的 key（set_fact 场景）或实体 ID（task/memory 场景）。
    value:
        写入的值。类型依 op 而定（set_fact 为 str/None，其他为 dict/dataclass）。
    scope:
        fact 的作用域，或任务类 op 写入生命史账本时的分类。
    source:
        提交来源标识（如 ``"loop/tick"``、``"execution"``、``"reference"``），
        用于生命史账本溯源，不影响落地行为。
    """
    op: str
    key: str
    value: Any
    scope: str = "task"
    source: str = ""
    run_id: int = 0
    extras: dict[str, Any] = field(default_factory=dict)
