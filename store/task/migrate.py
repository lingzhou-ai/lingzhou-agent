"""store/task/migrate.py — TaskStore 一次性 DB 迁移逻辑（包私有）。"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

from .schema import _CREATE_FAILURES, _CREATE_TASKS

logger = logging.getLogger(__name__)


async def migrate_legacy_schema(db: aiosqlite.Connection) -> None:
    """旧列式 schema → JSON-first 一次性迁移。"""
    async with db.execute(
        "SELECT COUNT(*) FROM pragma_table_info('tasks') WHERE name='data'"
    ) as cur:
        row = await cur.fetchone()
        if row and row[0] > 0:
            async with db.execute(
                "SELECT COUNT(*) FROM pragma_table_info('failures') WHERE name='dismissed'"
            ) as cur2:
                row2 = await cur2.fetchone()
                if not (row2 and row2[0] > 0):
                    await db.execute(
                        "ALTER TABLE failures ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0"
                    )
                    await db.commit()
            return

    async with db.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tasks'"
    ) as cur:
        row = await cur.fetchone()
        if not (row and row[0] > 0):
            return

    logger.info("[task_store] 检测到旧列式 schema，开始一次性迁移 → JSON-first")

    old_tasks: list[dict[str, Any]] = []
    try:
        async with db.execute(
            "SELECT id, title, goal, priority, status, source, next_step, created_at FROM tasks"
        ) as cur:
            async for r in cur:
                old_tasks.append({
                    "id": r[0], "title": r[1], "goal": r[2] or "",
                    "priority": r[3] or "normal", "status": r[4] or "pending",
                    "source": r[5] or "external", "next_step": r[6] or "",
                    "created_at": r[7] or "",
                })
    except Exception:
        pass

    old_failures: list[dict[str, Any]] = []
    try:
        async with db.execute(
            "SELECT id, kind, summary, context, task_id, created_at FROM failures"
        ) as cur:
            async for r in cur:
                old_failures.append({
                    "id": r[0], "kind": r[1], "summary": r[2] or "",
                    "context": r[3] or "", "task_id": r[4] or "",
                    "created_at": r[5] or "",
                })
    except Exception:
        pass

    await db.executescript("""
        DROP TABLE IF EXISTS tasks;
        DROP TABLE IF EXISTS failures;
    """)
    await db.executescript(_CREATE_TASKS + _CREATE_FAILURES)

    for t in old_tasks:
        data = json.dumps({
            "goal": t["goal"], "source": t["source"], "next_step": t["next_step"]
        }, ensure_ascii=False)
        await db.execute(
            "INSERT OR REPLACE INTO tasks (id, title, status, priority, created_at, data) "
            "VALUES (?,?,?,?,?,?)",
            (t["id"], t["title"], t["status"], t["priority"], t["created_at"], data),
        )

    for f in old_failures:
        data = json.dumps({
            "summary": f["summary"], "context": f["context"], "task_id": f["task_id"]
        }, ensure_ascii=False)
        await db.execute(
            "INSERT OR REPLACE INTO failures (id, kind, dismissed, created_at, data) "
            "VALUES (?,?,0,?,?)",
            (f["id"], f["kind"], f["created_at"], data),
        )

    await db.commit()
    logger.info("[task_store] 迁移完成：%d 任务, %d 失败记录", len(old_tasks), len(old_failures))


async def migrate_interlocutor_facts(db: aiosqlite.Connection) -> None:
    """旧 person_profile_id facts → interlocutor 命名空间。"""
    async with db.execute(
        "SELECT key, value, scope, updated_at FROM facts ORDER BY updated_at ASC"
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        return

    profile_ids = {
        str(value or "").strip()
        for key, value, _, _ in rows
        if str(key or "").endswith(":person_profile_id") and str(value or "").strip()
    }

    migrations: list[tuple[str, str, str, str, str]] = []
    for key, value, scope, updated_at in rows:
        normalized_key = str(key or "").strip()
        new_key = ""
        if normalized_key.endswith(":person_profile_id"):
            new_key = normalized_key[: -len(":person_profile_id")] + ":interlocutor_profile_id"
        elif normalized_key.startswith("user:"):
            parts = normalized_key.split(":")
            if len(parts) >= 3 and parts[1] in profile_ids:
                new_key = "interlocutor:" + ":".join(parts[1:])
        if new_key and new_key != normalized_key:
            migrations.append((normalized_key, new_key, str(value or ""), str(scope or "general"), str(updated_at or "")))

    if not migrations:
        return

    for old_key, new_key, value, scope, updated_at in migrations:
        await db.execute(
            """
            INSERT INTO facts (key, value, scope, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = CASE WHEN excluded.updated_at >= facts.updated_at THEN excluded.value ELSE facts.value END,
                scope = CASE WHEN excluded.updated_at >= facts.updated_at THEN excluded.scope ELSE facts.scope END,
                updated_at = CASE WHEN excluded.updated_at >= facts.updated_at THEN excluded.updated_at ELSE facts.updated_at END
            """,
            (new_key, value, scope or "general", updated_at or ""),
        )
        await db.execute("DELETE FROM facts WHERE key=?", (old_key,))
    await db.commit()
    logger.info("[task_store] 已迁移 %d 条旧 person_profile facts 到 interlocutor", len(migrations))


async def migrate_ledger_run_id(db: aiosqlite.Connection) -> None:
    """为旧 life_ledger 表补加 run_id 列。"""
    async with db.execute(
        "SELECT COUNT(*) FROM pragma_table_info('life_ledger') WHERE name='run_id'"
    ) as cur:
        row = await cur.fetchone()
        if not row or not row[0]:
            await db.execute(
                "ALTER TABLE life_ledger ADD COLUMN run_id INTEGER NOT NULL DEFAULT 0"
            )
            await db.commit()
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_life_ledger_run_id ON life_ledger(run_id)"
    )
    await db.commit()
