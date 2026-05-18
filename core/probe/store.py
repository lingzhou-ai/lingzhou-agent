"""core/probe/store.py — 探针配置持久化（aiosqlite）。"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

import aiosqlite

from .types import ProbeConfig

_log = logging.getLogger("lingzhou.probe")

_DDL = """
CREATE TABLE IF NOT EXISTS probes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    UNIQUE NOT NULL,
    kind         TEXT    NOT NULL,
    spec         TEXT    NOT NULL,
    trigger      TEXT    NOT NULL,
    data_back    TEXT    NOT NULL DEFAULT 'wm',
    alert_expr   TEXT,
    alert_message TEXT,
    chat_id      TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    last_run_at  TEXT,
    last_result  TEXT,
    last_error   TEXT
);
"""


def _row_to_config(row: Any) -> ProbeConfig:
    (
        id_, name, kind, spec, trigger, data_back,
        alert_expr, alert_message, chat_id, enabled,
        created_at, last_run_at, last_result, last_error,
    ) = row
    return ProbeConfig(
        id=id_,
        name=name,
        kind=kind,
        spec=spec,
        trigger=trigger,
        data_back=data_back,
        alert_expr=alert_expr,
        alert_message=alert_message,
        chat_id=chat_id,
        enabled=bool(enabled),
        created_at=created_at or "",
        last_run_at=last_run_at,
        last_result=last_result,
        last_error=last_error,
    )


class ProbeStore:
    """探针配置 CRUD。与 TaskStore 共享同一 aiosqlite 连接。"""

    def __init__(self, db_getter: Callable[[], aiosqlite.Connection]) -> None:
        self._db_getter = db_getter

    @property
    def _db(self) -> aiosqlite.Connection:
        return self._db_getter()

    async def migrate(self) -> None:
        """幂等建表。"""
        await self._db.executescript(_DDL)
        await self._db.commit()

    async def upsert(self, cfg: ProbeConfig) -> int:
        """新增或更新探针（按 name）。返回 id。"""
        async with self._db.execute(
            """INSERT INTO probes
               (name, kind, spec, trigger, data_back, alert_expr, alert_message, chat_id, enabled)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 kind=excluded.kind,
                 spec=excluded.spec,
                 trigger=excluded.trigger,
                 data_back=excluded.data_back,
                 alert_expr=excluded.alert_expr,
                 alert_message=excluded.alert_message,
                 chat_id=excluded.chat_id,
                 enabled=excluded.enabled
            """,
            (
                cfg.name, cfg.kind, cfg.spec, cfg.trigger,
                cfg.data_back, cfg.alert_expr, cfg.alert_message,
                cfg.chat_id, int(cfg.enabled),
            ),
        ) as cur:
            row_id: int = cur.lastrowid or 0
        await self._db.commit()
        return row_id

    async def delete(self, name: str) -> bool:
        """删除探针，返回是否找到并删除。"""
        result = await self._db.execute("DELETE FROM probes WHERE name=?", (name,))
        await self._db.commit()
        return (result.rowcount or 0) > 0

    async def get(self, name: str) -> ProbeConfig | None:
        async with self._db.execute(
            "SELECT id,name,kind,spec,trigger,data_back,alert_expr,alert_message,"
            "chat_id,enabled,created_at,last_run_at,last_result,last_error "
            "FROM probes WHERE name=?",
            (name,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_config(row) if row else None

    async def list_all(self, enabled_only: bool = False) -> list[ProbeConfig]:
        sql = (
            "SELECT id,name,kind,spec,trigger,data_back,alert_expr,alert_message,"
            "chat_id,enabled,created_at,last_run_at,last_result,last_error "
            "FROM probes"
        )
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY id"
        async with self._db.execute(sql) as cur:
            rows = await cur.fetchall()
        return [_row_to_config(r) for r in rows]

    async def update_run_result(
        self,
        name: str,
        last_run_at: str,
        last_result: str | None,
        last_error: str | None,
    ) -> None:
        await self._db.execute(
            "UPDATE probes SET last_run_at=?, last_result=?, last_error=? WHERE name=?",
            (last_run_at, last_result, last_error, name),
        )
        await self._db.commit()

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        result = await self._db.execute(
            "UPDATE probes SET enabled=? WHERE name=?",
            (int(enabled), name),
        )
        await self._db.commit()
        return (result.rowcount or 0) > 0
