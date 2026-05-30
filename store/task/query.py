"""store/task/query.py — TaskStore 复杂查询逻辑（包私有）。"""
from __future__ import annotations

from typing import Any

import aiosqlite

from .models import Task
from .schema import (
    OPEN_TASK_STATUSES,
    TASK_SIMILARITY_CONTEXT_SCORE,
    _TASK_PRIORITY_RANK,
    _TASK_SIMILARITY_SCAN_LIMIT,
    _TASK_STATUS_RANK,
    _task_similarity_score,
    build_task_similarity_query,
)


async def query_open_tasks(
    db: aiosqlite.Connection,
    limit: int = 50,
    *,
    statuses: tuple[str, ...] | list[str] | None = None,
) -> list[Task]:
    normalized_statuses = tuple(
        str(s or "").strip()
        for s in (statuses or OPEN_TASK_STATUSES)
        if str(s or "").strip()
    )
    if limit <= 0 or not normalized_statuses:
        return []
    placeholders = ",".join("?" for _ in normalized_statuses)
    sql = (
        "SELECT id, title, status, priority, created_at, data "
        f"FROM tasks WHERE status IN ({placeholders}) "
        "ORDER BY "
        "CASE status "
        "    WHEN 'in_progress' THEN 0 "
        "    WHEN 'resumed' THEN 1 "
        "    WHEN 'ready' THEN 2 "
        "    WHEN 'pending' THEN 3 "
        "    WHEN 'waiting' THEN 4 "
        "    ELSE 5 "
        "END, "
        "CASE priority "
        "    WHEN 'critical' THEN 0 "
        "    WHEN 'high' THEN 1 "
        "    WHEN 'normal' THEN 2 "
        "    ELSE 3 "
        "END, "
        "id LIMIT ?"
    )
    args: tuple[Any, ...] = (*normalized_statuses, int(limit))
    async with db.execute(sql, args) as cur:
        rows = await cur.fetchall()
    return [Task.from_row(row) for row in rows]


async def find_similar_open_tasks(
    db: aiosqlite.Connection,
    query: str,
    *,
    limit: int = 5,
    min_score: float = TASK_SIMILARITY_CONTEXT_SCORE,
    exclude_task_ids: list[int] | tuple[int, ...] | set[int] | None = None,
    allowed_sources: list[str] | tuple[str, ...] | set[str] | None = None,
    excluded_sources: list[str] | tuple[str, ...] | set[str] | None = None,
    statuses: tuple[str, ...] | list[str] | None = None,
) -> list[tuple[Task, float]]:
    query_text = build_task_similarity_query(query)
    if limit <= 0 or not query_text:
        return []

    exclude_ids = {
        int(task_id)
        for task_id in (exclude_task_ids or [])
        if str(task_id).strip()
    }
    normalized_allowed = {
        str(s).strip() for s in (allowed_sources or []) if str(s).strip()
    }
    normalized_excluded = {
        str(s).strip() for s in (excluded_sources or []) if str(s).strip()
    }
    scan_limit = min(_TASK_SIMILARITY_SCAN_LIMIT, max(int(limit) * 6, 24))
    candidates = await query_open_tasks(db, limit=scan_limit, statuses=statuses)

    scored: list[tuple[Task, float]] = []
    for task in candidates:
        if task.id in exclude_ids:
            continue
        task_source = str(getattr(task, "source", "") or "").strip()
        if normalized_allowed and task_source not in normalized_allowed:
            continue
        if normalized_excluded and task_source in normalized_excluded:
            continue
        score = _task_similarity_score(query_text, task)
        if score < float(min_score):
            continue
        scored.append((task, score))

    scored.sort(key=lambda item: (
        -item[1],
        _TASK_STATUS_RANK.get(item[0].status, 99),
        _TASK_PRIORITY_RANK.get(item[0].priority, 99),
        item[0].id,
    ))
    return scored[: int(limit)]
