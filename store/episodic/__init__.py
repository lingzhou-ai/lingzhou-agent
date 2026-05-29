"""memory/episodic.py — 情节记忆（EpisodicMemory）。

双层存储（解决 O(n) P0 问题）：
    1. episodic/task-{id}.md / episodic/global.md  — 人类可读叙事（直接截取末尾注入 LLM context）
  2. episodic.db               — 结构化事件 + 叙事 FTS5 索引
     - events 表：替代 O(n) events.jsonl 扫描，O(log n) 索引查询
     - narrative 表 + narrative_fts：支持跨任务叙事全文检索

向后兼容：
  - 公开接口签名不变，调用方零改动
  - 启动时一次性将历史 events.jsonl 导入 DB（幂等）
  - DB 损坏时自动重建（从 .md 文件恢复叙事 FTS5，从 jsonl 恢复 events）

设计依据：
  - Tulving (1983): WHAT+WHEN+CONTEXT+AFFECT 四元素绑定
  - Johnson & Raye (1981): 来源监控（source_type）
  - Ricoeur (1984): 叙事连续性（task_id 组织，跨 chat 持久）
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager, suppress
from pathlib import Path

from ._db import connect as _connect_impl
from ._db import ensure_schema_compat as _ensure_schema_compat_impl
from ._db import migrate_from_jsonl as _migrate_from_jsonl_impl
from ._db import open_db as _open_db_impl
from ._db import rebuild_narrative_fts as _rebuild_narrative_fts_impl
from ._db import table_columns as _table_columns_impl
from ._events import fallback_list_events as _fallback_list_events_impl
from ._events import list_events as _list_events_impl
from ._events import list_events_multi as _list_events_multi_impl
from ._events import record_event as _record_event_impl
from ._events import rotate_events_db as _rotate_events_db_impl
from ._narrative import append_markdown_block as _append_markdown_block_impl
from ._narrative import chat_filename as _chat_filename_impl
from ._narrative import chat_path as _chat_path_impl
from ._narrative import chat_path_for_dir as _chat_path_for_dir_impl
from ._narrative import daily_filename as _daily_filename_impl
from ._narrative import daily_path as _daily_path_impl
from ._narrative import daily_path_for_dir as _daily_path_for_dir_impl
from ._narrative import day_stamp_from_ts as _day_stamp_from_ts_impl
from ._narrative import get_recent_turns as _get_recent_turns_impl
from ._narrative import insert_narrative_row as _insert_narrative_row_impl
from ._narrative import interlocutor_filename as _interlocutor_filename_impl
from ._narrative import interlocutor_path as _interlocutor_path_impl
from ._narrative import interlocutor_path_for_dir as _interlocutor_path_for_dir_impl
from ._narrative import iter_legacy_narrative_files as _iter_legacy_narrative_files_impl
from ._narrative import iter_narrative_files as _iter_narrative_files_impl
from ._narrative import legacy_narrative_path_for_dir as _legacy_narrative_path_for_dir_impl
from ._narrative import legacy_task_path as _legacy_task_path_impl
from ._narrative import list_recent_narrative as _list_recent_narrative_impl
from ._narrative import list_tasks as _list_tasks_impl
from ._narrative import load_for_chat_context as _load_for_chat_context_impl
from ._narrative import load_for_context as _load_for_context_impl
from ._narrative import load_for_interlocutor_context as _load_for_interlocutor_context_impl
from ._narrative import load_for_task_narrative as _load_for_task_narrative_impl
from ._narrative import load_markdown_context as _load_markdown_context_impl
from ._narrative import load_recent_daily_context as _load_recent_daily_context_impl
from ._narrative import migrate_legacy_narrative_files as _migrate_legacy_narrative_files_impl
from ._narrative import narrative_filename as _narrative_filename_impl
from ._narrative import narrative_path_for_dir as _narrative_path_for_dir_impl
from ._narrative import query_recent_narrative as _query_recent_narrative_impl
from ._narrative import record as _record_impl
from ._narrative import resolve_task_path as _resolve_task_path_impl
from ._narrative import search as _search_impl
from ._narrative import search_recent_daily as _search_recent_daily_impl
from ._narrative import sync_narrative_fts as _sync_narrative_fts_impl
from ._narrative import task_path as _task_path_impl
from ._source import SRC_EXECUTION
from ._source import SRC_HUMAN
from ._source import SRC_INFERENCE
from ._source import SRC_REFLECTION
from ._source import SRC_SYSTEM
from ._source import source_from_role


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

    @property
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self, "_conn_ref", None)
        if conn is None:
            raise RuntimeError("episodic db session is not open")
        return conn

    @_conn.setter
    def _conn(self, value: sqlite3.Connection | None) -> None:
        self._conn_ref = value

    @contextmanager
    def _db_session(self):
        if self._conn_ref is not None:
            self._session_depth += 1
            try:
                yield self._conn_ref
            finally:
                self._session_depth -= 1
            return

        conn = self._open_db()
        self._conn = conn
        self._session_depth = 1
        try:
            yield conn
        finally:
            self._session_depth -= 1
            if self._session_depth == 0:
                self.close()

    def close(self) -> None:
        conn = getattr(self, "_conn_ref", None)
        self._conn_ref = None
        self._session_depth = 0
        if conn is not None:
            with suppress(Exception):
                conn.close()

    @property
    def max_events(self) -> int:
        """Maximum retained events per type; 0 means unlimited."""
        return self._max_events

    _open_db = _open_db_impl
    _connect = _connect_impl
    _ensure_schema_compat = _ensure_schema_compat_impl
    _table_columns = staticmethod(_table_columns_impl)
    _rebuild_narrative_fts = _rebuild_narrative_fts_impl
    _migrate_from_jsonl = _migrate_from_jsonl_impl

    _narrative_filename = staticmethod(_narrative_filename_impl)
    _chat_filename = staticmethod(_chat_filename_impl)
    _interlocutor_filename = staticmethod(_interlocutor_filename_impl)
    _daily_filename = staticmethod(_daily_filename_impl)
    narrative_path_for_dir = classmethod(_narrative_path_for_dir_impl)
    daily_path_for_dir = classmethod(_daily_path_for_dir_impl)
    chat_path_for_dir = classmethod(_chat_path_for_dir_impl)
    interlocutor_path_for_dir = classmethod(_interlocutor_path_for_dir_impl)
    legacy_narrative_path_for_dir = classmethod(_legacy_narrative_path_for_dir_impl)
    _task_path = _task_path_impl
    _daily_path = _daily_path_impl
    _chat_path = _chat_path_impl
    _interlocutor_path = _interlocutor_path_impl
    _legacy_task_path = _legacy_task_path_impl
    _resolve_task_path = _resolve_task_path_impl
    _iter_legacy_narrative_files = _iter_legacy_narrative_files_impl
    _iter_narrative_files = _iter_narrative_files_impl
    _migrate_legacy_narrative_files = _migrate_legacy_narrative_files_impl
    _append_markdown_block = staticmethod(_append_markdown_block_impl)
    _day_stamp_from_ts = staticmethod(_day_stamp_from_ts_impl)
    _insert_narrative_row = _insert_narrative_row_impl
    _sync_narrative_fts = _sync_narrative_fts_impl
    record = _record_impl
    _load_markdown_context = staticmethod(_load_markdown_context_impl)
    load_for_context = _load_for_context_impl
    load_for_chat_context = _load_for_chat_context_impl
    load_for_interlocutor_context = _load_for_interlocutor_context_impl
    load_for_task_narrative = _load_for_task_narrative_impl
    load_recent_daily_context = _load_recent_daily_context_impl
    search_recent_daily = _search_recent_daily_impl
    get_recent_turns = _get_recent_turns_impl
    list_tasks = _list_tasks_impl
    list_recent_narrative = _list_recent_narrative_impl
    query_recent_narrative = _query_recent_narrative_impl

    record_event = _record_event_impl
    _rotate_events_db = _rotate_events_db_impl
    list_events = _list_events_impl
    _fallback_list_events = _fallback_list_events_impl
    list_events_multi = _list_events_multi_impl

    search = _search_impl


__all__ = [
    "EpisodicMemory",
    "SRC_HUMAN",
    "SRC_INFERENCE",
    "SRC_EXECUTION",
    "SRC_SYSTEM",
    "SRC_REFLECTION",
]
