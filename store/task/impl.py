from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiosqlite

from . import TaskStore
from .migrate import migrate_interlocutor_facts, migrate_ledger_run_id, migrate_legacy_schema
from .schema import (
    _CREATE_CHAT,
    _CREATE_FACTS,
    _CREATE_FAILURES,
    _CREATE_INDEXES,
    _CREATE_LIFE_LEDGER,
    _CREATE_META_REFLECTIONS,
    _CREATE_RUNS,
    _CREATE_SIGNALS,
    _CREATE_TASKS,
)

_logger = logging.getLogger("store.task")


def _db_getter(self: TaskStore) -> aiosqlite.Connection:
    assert self._db_conn is not None, "TaskStore not open — call open() first"
    return self._db_conn


async def open(self: TaskStore) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    self._db_conn = await aiosqlite.connect(str(self._path), timeout=60)
    await self._db.execute("PRAGMA journal_mode=WAL")
    await self._db.execute("PRAGMA busy_timeout=30000")
    await self._db.execute("PRAGMA synchronous=NORMAL")
    await self._db.execute("PRAGMA wal_autocheckpoint=100")
    await self._db.execute("PRAGMA foreign_keys=ON")
    await migrate_legacy_schema(self._db)
    await self._db.executescript(
        _CREATE_TASKS + _CREATE_FAILURES + _CREATE_FACTS + _CREATE_SIGNALS
        + _CREATE_CHAT + _CREATE_RUNS + _CREATE_META_REFLECTIONS
        + _CREATE_LIFE_LEDGER + _CREATE_INDEXES
    )
    await self._db.execute(
        "UPDATE chat_messages SET status='pending' WHERE role='user' AND status='processing'"
    )
    await self._db.commit()
    await migrate_interlocutor_facts(self._db)
    await migrate_ledger_run_id(self._db)


async def close(self: TaskStore) -> None:
    if self._db_conn:
        await self._db_conn.close()
        self._db_conn = None


async def wal_checkpoint(self: TaskStore) -> None:
    """触发 WAL checkpoint（TRUNCATE 模式）。"""
    await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    await self._db.commit()


async def _write_with_retry(self: TaskStore, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
    """所有写操作的统一入口：串行锁 + 指数退避重试。"""
    for attempt in range(6):
        try:
            async with self._write_lock:
                return await fn(*args, **kwargs)
        except Exception as exc:
            if "database is locked" in str(exc).lower() and attempt < 5:
                try:
                    await self._db.rollback()
                except Exception:
                    pass
                await asyncio.sleep(0.15 * (2 ** attempt))
                _logger.debug("[task_store] database locked, retry %d/5", attempt + 1)
            else:
                raise
    return None


async def reset_in_progress_tasks(self: TaskStore) -> int:
    async def _do() -> int:
        result = await self._db.execute(
            "UPDATE tasks SET status='pending' WHERE status='in_progress'"
        )
        await self._db.commit()
        return result.rowcount if result else 0

    return await self._write_with_retry(_do)


def bind_task_store(cls: type[TaskStore]) -> None:
    cls._db = property(_db_getter)
    cls.open = open
    cls.close = close
    cls.wal_checkpoint = wal_checkpoint
    cls._write_with_retry = _write_with_retry
    cls.reset_in_progress_tasks = reset_in_progress_tasks
