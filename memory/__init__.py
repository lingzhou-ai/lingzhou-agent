from __future__ import annotations

from typing import TYPE_CHECKING

from memory.working import WMItem, WorkingMemory

if TYPE_CHECKING:
    from store.episodic import EpisodicMemory
    from store.semantic import MemoryNode, SemanticMemory
    from store.task import Failure, MetaReflection, Run, Task, TaskStore


def __getattr__(name: str):  # type: ignore[return]
    if name == "EpisodicMemory":
        from store.episodic import EpisodicMemory
        return EpisodicMemory
    if name in ("SemanticMemory", "MemoryNode"):
        import store.semantic as _sm
        return getattr(_sm, name)
    if name in ("TaskStore", "Task", "Failure", "Run", "MetaReflection"):
        import store.task as _st
        return getattr(_st, name)
    raise AttributeError(f"module 'memory' has no attribute {name!r}")


__all__ = [
    "EpisodicMemory",
    "Failure",
    "MemoryNode",
    "MetaReflection",
    "Run",
    "SemanticMemory",
    "Task",
    "TaskStore",
    "WMItem",
    "WorkingMemory",
]
