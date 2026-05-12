"""memory/working.py — 工作记忆（WorkingMemory）。

设计：内存优先队列，有容量上限，按 priority 降序排列。
     超过容量时自动驱逐最低优先级条目。
     不持久化——WM 本来就是瞬态的，重启后从情节/语义记忆重建。
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any


@dataclass(order=True)
class WMItem:
    # heapq 是最小堆，用负优先级实现最大堆
    _neg_priority: float = field(init=False, repr=False)
    kind: str = field(compare=False)
    content: str = field(compare=False)
    priority: float = field(compare=False, default=0.8)
    created_at: datetime = field(compare=False, default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self._neg_priority = -self.priority

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "content": self.content,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
        }


class WorkingMemory:
    """容量有界的工作记忆。线程/协程安全（asyncio 单线程模型下天然安全）。"""

    def __init__(self, capacity: int = 20) -> None:
        self._capacity = capacity
        self._items: list[WMItem] = []

    @property
    def pressure(self) -> float:
        """当前占用率 [0, 1]，供感知层判断是否触发整合任务。"""
        return len(self._items) / self._capacity if self._capacity > 0 else 0.0

    def add(self, item: WMItem) -> None:
        """添加条目，若超容量则驱逐优先级最低的。"""
        heapq.heappush(self._items, item)
        while len(self._items) > self._capacity:
            # heappop 弹出最小（即负优先级最大 = 真实优先级最低）
            heapq.heappop(self._items)

    def get_top(self, n: int | None = None) -> list[dict[str, Any]]:
        """按优先级降序返回前 n 条（不修改内部状态）。"""
        sorted_items = sorted(self._items, key=lambda x: x.priority, reverse=True)
        if n is not None:
            sorted_items = sorted_items[:n]
        return [item.to_dict() for item in sorted_items]

    def clear(self, preserve_kinds: set[str] | None = None) -> None:
        """清空工作记忆。preserve_kinds 中列出的类型条目保留（如身份锚点 bootstrap_identity）。"""
        if preserve_kinds:
            self._items = [item for item in self._items if item.kind in preserve_kinds]
            heapq.heapify(self._items)
        else:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
