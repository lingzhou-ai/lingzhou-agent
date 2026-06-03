"""core/metabolic/ — 代谢器官。

公理 A5：正式状态写入必须经过代谢器官；外围器官与子灵只能提交候选写入，不能直接定稿。

当前阶段：
  - StateProposal 数据结构就位
  - submit() 先经免疫检查再落地
  - 生命史账本（只追加）
  - fact 与任务生命周期的正式写入统一收归此入口
"""
from core.metabolic.engine import MetabolicEngine
from core.metabolic.fact_lifecycle import delete_fact, resolve_metabolic, submit_fact
from core.metabolic.proposal import StateProposal
from core.metabolic.run_lifecycle import add_run, update_run
from core.metabolic.semantic_lifecycle import add_semantic_memory
from core.metabolic.soul_lifecycle import set_soul_fact
from core.metabolic.state_writer import StateWriteResult, apply_state_write
from core.metabolic.task_lifecycle import (
    amend_task,
    create_task,
    mark_task_waiting,
    resume_task,
    update_task_data,
    update_task_result,
    update_task_status,
)

__all__ = [
    "MetabolicEngine",
    "StateProposal",
    "StateWriteResult",
    "add_semantic_memory",
    "amend_task",
    "add_run",
    "apply_state_write",
    "create_task",
    "delete_fact",
    "mark_task_waiting",
    "resolve_metabolic",
    "update_task_result",
    "resume_task",
    "set_soul_fact",
    "submit_fact",
    "update_run",
    "update_task_data",
    "update_task_status",
]
