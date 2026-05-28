"""store/task/ledger.py — 生命史账本（只追加）。

公理 A5：代谢器官负责将每笔已决策的状态写入记录到此账本。
账本只追加，不修改，不删除；供 LLM 感知历史状态变化并做决策。
"""
from __future__ import annotations

from collections.abc import Callable

import aiosqlite

from ._base import BaseAsyncStore


class LedgerStore(BaseAsyncStore):
    """生命史账本：append-only，记录代谢器官每笔处理结果。

    LLM 可通过 recent() 感知近期状态变更历史，作为决策依据。
    """

    def __init__(self, db_getter: Callable[[], aiosqlite.Connection]) -> None:
        super().__init__(db_getter)

    async def append(
        self,
        op: str,
        key: str,
        value: str,
        *,
        scope: str = "task",
        source: str = "",
        accepted: bool = True,
        run_id: int = 0,
    ) -> None:
        """追加一条生命史记录。

        accepted=False 表示该提案被免疫器官拒绝，仍记录以备审计。
        run_id=0 表示未关联具体 Run（非执行路径产生的提案）。
        """
        await self._db.execute(
            "INSERT INTO life_ledger (op, key, value, scope, source, accepted, run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (op, key, str(value) if value is not None else "", scope, source, int(accepted), run_id),
        )
        await self._db.commit()

    async def recent(self, limit: int = 50) -> list[dict]:
        """读取最近 N 条账本记录（最新在前）。

        供 LLM 感知近期状态变化，返回 list[dict] 便于序列化注入上下文。
        """
        async with self._db.execute(
            "SELECT id, ts, op, key, value, scope, source, accepted, run_id "
            "FROM life_ledger ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": row[0],
                "ts": row[1],
                "op": row[2],
                "key": row[3],
                "value": row[4],
                "scope": row[5],
                "source": row[6],
                "accepted": bool(row[7]),
                "run_id": row[8],
            }
            for row in rows
        ]

    async def since(self, after_id: int, limit: int = 100) -> list[dict]:
        """读取 id > after_id 的记录（增量拉取，供 LLM 决策时对比前后变化）。"""
        async with self._db.execute(
            "SELECT id, ts, op, key, value, scope, source, accepted, run_id "
            "FROM life_ledger WHERE id > ? ORDER BY id ASC LIMIT ?",
            (after_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": row[0],
                "ts": row[1],
                "op": row[2],
                "key": row[3],
                "value": row[4],
                "scope": row[5],
                "source": row[6],
                "accepted": bool(row[7]),
                "run_id": row[8],
            }
            for row in rows
        ]
