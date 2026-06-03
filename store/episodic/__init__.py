"""store.episodic — 情节记忆（EpisodicMemory）。

双层存储（解决 O(n) P0 问题）：
    1. episodic/task-{id}.md / episodic/global.md  — 人类可读叙事（直接截取末尾注入 LLM context）
  2. episodic.db               — 结构化事件 + 叙事 FTS5 索引
     - events 表：替代 O(n) events.jsonl 扫描，O(log n) 索引查询
     - narrative 表 + narrative_fts：支持跨任务叙事全文检索

数据迁移：
  - 启动时一次性将历史 events.jsonl 导入 DB（幂等）
  - DB 损坏时自动重建（从 .md 文件恢复叙事 FTS5，从 jsonl 恢复 events）

设计依据：
  - Tulving (1983): WHAT+WHEN+CONTEXT+AFFECT 四元素绑定
  - Johnson & Raye (1981): 来源监控（source_type）
  - Ricoeur (1984): 叙事连续性（task_id 组织，跨 chat 持久）
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from .source import (
    SRC_EXECUTION,
    SRC_HUMAN,
    SRC_INFERENCE,
    SRC_REFLECTION,
    SRC_SYSTEM,
    source_from_role,
)


def _source_from_role(role: str) -> str:
    """向后兼容旧的模块内函数名。"""
    return source_from_role(role)


class EpisodicMemory:
    def __init__(self, memory_dir: Path, max_events: int = 0) -> None:
        self._dir = memory_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._narrative_dir = self._dir / "episodic"
        self._narrative_dir.mkdir(parents=True, exist_ok=True)
        self._chat_dir = self._narrative_dir / "chat"
        self._chat_dir.mkdir(parents=True, exist_ok=True)
        self._interlocutor_dir = self._narrative_dir / "interlocutor"
        self._interlocutor_dir.mkdir(parents=True, exist_ok=True)
        self._daily_dir = self._narrative_dir / "daily"
        self._daily_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_narrative_files()
        self._max_events = max_events
        self._db_path = memory_dir / "episodic.db"
        self._conn = None
        self._session_depth = 0
        with self._db_session():
            self._migrate_from_jsonl()

    @contextmanager
    def _db_session(self):
        raise RuntimeError("episodic db session binding missing")
        yield None

    def close(self) -> None:
        raise RuntimeError("episodic close binding missing")

    @property
    def max_events(self) -> int:
        raise RuntimeError("episodic max_events binding missing")

    def _migrate_legacy_narrative_files(self) -> None:
        raise RuntimeError("episodic narrative migration binding missing")

    def _migrate_from_jsonl(self) -> None:
        raise RuntimeError("episodic jsonl migration binding missing")

def _bind_episodic_memory() -> None:
    """延迟绑定：等待类定义完成后再注入 db/query/registry 的运行时方法。"""
    from .impl import bind_episodic_memory

    bind_episodic_memory(EpisodicMemory)


_bind_episodic_memory()


__all__ = [
    "EpisodicMemory",
    "SRC_HUMAN",
    "SRC_INFERENCE",
    "SRC_EXECUTION",
    "SRC_SYSTEM",
    "SRC_REFLECTION",
]
