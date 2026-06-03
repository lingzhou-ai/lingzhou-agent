from __future__ import annotations

import sqlite3
from contextlib import contextmanager, suppress

from . import (
    EpisodicMemory,
    db,
    events,
    narrative,
)


def _conn_getter(self: EpisodicMemory) -> sqlite3.Connection:
    conn = getattr(self, "_conn_ref", None)
    if conn is None:
        raise RuntimeError("episodic db session is not open")
    return conn


def _conn_setter(self: EpisodicMemory, value: sqlite3.Connection | None) -> None:
    self._conn_ref = value


@contextmanager
def _db_session(self: EpisodicMemory):
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


def close(self: EpisodicMemory) -> None:
    conn = getattr(self, "_conn_ref", None)
    self._conn_ref = None
    self._session_depth = 0
    if conn is not None:
        with suppress(Exception):
            conn.close()


def max_events(self: EpisodicMemory) -> int:
    """Maximum retained events per type; 0 means unlimited."""
    return self._max_events


def bind_episodic_memory(cls: type[EpisodicMemory]) -> None:
    cls._conn = property(_conn_getter, _conn_setter)
    cls._db_session = _db_session
    cls.close = close
    cls.max_events = property(max_events)

    cls._open_db = db.open_db
    cls._connect = db.connect
    cls._ensure_schema_compat = db.ensure_schema_compat
    cls._table_columns = staticmethod(db.table_columns)
    cls._rebuild_narrative_fts = db.rebuild_narrative_fts
    cls._migrate_from_jsonl = db.migrate_from_jsonl

    cls._narrative_filename = staticmethod(narrative.narrative_filename)
    cls._chat_filename = staticmethod(narrative.chat_filename)
    cls._interlocutor_filename = staticmethod(narrative.interlocutor_filename)
    cls._daily_filename = staticmethod(narrative.daily_filename)
    cls.narrative_path_for_dir = classmethod(narrative.narrative_path_for_dir)
    cls.daily_path_for_dir = classmethod(narrative.daily_path_for_dir)
    cls.chat_path_for_dir = classmethod(narrative.chat_path_for_dir)
    cls.interlocutor_path_for_dir = classmethod(narrative.interlocutor_path_for_dir)
    cls.legacy_narrative_path_for_dir = classmethod(narrative.legacy_narrative_path_for_dir)
    cls._task_path = narrative.task_path
    cls._daily_path = narrative.daily_path
    cls._chat_path = narrative.chat_path
    cls._interlocutor_path = narrative.interlocutor_path
    cls._legacy_task_path = narrative.legacy_task_path
    cls._resolve_task_path = narrative.resolve_task_path
    cls._iter_legacy_narrative_files = narrative.iter_legacy_narrative_files
    cls._iter_narrative_files = narrative.iter_narrative_files
    cls._migrate_legacy_narrative_files = narrative.migrate_legacy_narrative_files
    cls._append_markdown_block = staticmethod(narrative.append_markdown_block)
    cls._day_stamp_from_ts = staticmethod(narrative.day_stamp_from_ts)
    cls._insert_narrative_row = narrative.insert_narrative_row
    cls._sync_narrative_fts = narrative.sync_narrative_fts
    cls.record = narrative.record
    cls.load_for_context = narrative.load_for_context
    cls.load_for_chat_context = narrative.load_for_chat_context
    cls.load_for_interlocutor_context = narrative.load_for_interlocutor_context
    cls.load_for_speaker_recognition = narrative.load_for_speaker_recognition
    cls.load_for_task_narrative = narrative.load_for_task_narrative
    cls.load_recent_daily_context = narrative.load_recent_daily_context
    cls.search_recent_daily = narrative.search_recent_daily
    cls.get_recent_turns = narrative.get_recent_turns
    cls.list_tasks = narrative.list_tasks
    cls.list_recent_narrative = narrative.list_recent_narrative
    cls.query_recent_narrative = narrative.query_recent_narrative

    cls.record_event = events.record_event
    cls._rotate_events_db = events.rotate_events_db
    cls.list_events = events.list_events
    cls._fallback_list_events = events.fallback_list_events
    cls.list_events_multi = events.list_events_multi

    cls.search = narrative.search
