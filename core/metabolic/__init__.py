"""core/metabolic/ — 代谢器官。

公理 A5：正式状态写入必须经过代谢器官；外围器官与子灵只能提交候选写入，不能直接定稿。

当前阶段（Phase 1）：
  - StateProposal 数据结构就位
  - MetabolicEngine.submit() 直接落地（与原有 set_fact 行为一致）

Phase 2 起：
  - submit() 先经免疫检查再落地
  - 生命史账本（只追加）
  - ~40 处散落 set_fact 全部收归此入口
"""
from core.metabolic.proposal import StateProposal
from core.metabolic.engine import MetabolicEngine

__all__ = ["StateProposal", "MetabolicEngine"]
