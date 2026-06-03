"""store/task/__init__.py — 统一任务存储入口（TaskStore + 所有子存储）。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite

from store.task.chat import ChatMessageStore, sanitize_chat_content
from store.task.fact import FactStore, build_fact_upsert
from store.task.failure import FailureStore
from store.task.ingress import IngressStore, IngressWriter
from store.task.ledger import LedgerStore
from store.task.models import Failure, MetaReflection, Run, Task
from store.task.query import (
    find_similar_open_tasks as _find_similar_open_tasks,
)
from store.task.query import (
    query_open_tasks,
)
from store.task.reflection import MetaReflectionStore
from store.task.run import RunStore
from store.task.schema import (
    OPEN_TASK_STATUSES,
    RUNNABLE_TASK_STATUSES,
    TASK_DUPLICATE_REUSE_SCORE,
    TASK_SIMILARITY_CONTEXT_SCORE,
    build_task_run_result_patch,
)
from store.task.schema import (
    build_task_similarity_query as build_task_similarity_query,  # re-export
)
from store.task.signal import SignalStore
from store.task.state import TaskStateStore, build_task_data, build_task_insert


class TaskStore:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path) if isinstance(db_path, str) else db_path
        self._db_conn: aiosqlite.Connection | None = None
        # 写操作串行锁：防止并行 tick 多链并发写同一 aiosqlite 连接引发 SQLITE_LOCKED
        # （busy_timeout 只对跨进程 SQLITE_BUSY 有效，同进程内 SQLITE_LOCKED 无效）
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._chat = ChatMessageStore(lambda: self._db)

        self._facts = FactStore(lambda: self._db)
        self._failures = FailureStore(lambda: self._db)
        self._signals = SignalStore(lambda: self._db)
        self._tasks = TaskStateStore(lambda: self._db)
        self._runs = RunStore(lambda: self._db)
        self._meta_reflections = MetaReflectionStore(lambda: self._db)
        self._ledger = LedgerStore(lambda: self._db)

    @property
    def _db(self) -> aiosqlite.Connection:
        raise RuntimeError("task db binding missing")

    async def open(self) -> None:
        raise RuntimeError("task open binding missing")

    async def close(self) -> None:
        raise RuntimeError("task close binding missing")

    async def wal_checkpoint(self) -> None:
        raise RuntimeError("task checkpoint binding missing")

    async def _write_with_retry(self, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("task write retry binding missing")

    # ── 任务操作 ─────────────────────────────────────────────────────────

    async def add_task(
        self, title: str, goal: str = "", priority: str = "normal", source: str = "external", **kwargs: Any
    ) -> int:
        return await self._write_with_retry(self._tasks.add_task, title, goal, priority, source, **kwargs)

    async def get_task_by_id(self, task_id: int) -> Task | None:
        return await self._tasks.get_task_by_id(task_id)

    async def list_runnable_tasks(self, limit: int = 20) -> list[Task]:
        return await self._tasks.list_runnable_tasks(limit)

    async def list_open_tasks(
        self,
        limit: int = 50,
        *,
        statuses: tuple[str, ...] | list[str] | None = None,
    ) -> list[Task]:
        return await query_open_tasks(self._db, limit, statuses=statuses)

    async def find_similar_open_tasks(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = TASK_SIMILARITY_CONTEXT_SCORE,
        exclude_task_ids: list[int] | tuple[int, ...] | set[int] | None = None,
        allowed_sources: list[str] | tuple[str, ...] | set[str] | None = None,
        excluded_sources: list[str] | tuple[str, ...] | set[str] | None = None,
        statuses: tuple[str, ...] | list[str] | None = None,
    ) -> list[tuple[Task, float]]:
        return await _find_similar_open_tasks(
            self._db, query, limit=limit, min_score=min_score,
            exclude_task_ids=exclude_task_ids, allowed_sources=allowed_sources,
            excluded_sources=excluded_sources, statuses=statuses,
        )

    async def get_active(self) -> Task | None:
        return await self._tasks.get_active()

    async def list_tasks(self, status: str | None = None, limit: int = 50) -> list[Task]:
        return await self._tasks.list_tasks(status=status, limit=limit)

    async def update_status(
        self,
        task_id: int,
        status: str,
        next_step: str | None = None,
        *,
        current_step: str | None = None,
        model_tier: str | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> None:
        await self._write_with_retry(
            self._tasks.update_status,
            task_id, status, next_step,
            current_step=current_step, model_tier=model_tier, result_json=result_json,
        )

    async def mark_waiting(
        self,
        task_id: int,
        *,
        wait_kind: str,
        wait_key: str = "",
        wait_json: dict[str, Any] | None = None,
        current_step: str | None = None,
        next_step: str | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> None:
        await self._write_with_retry(
            self._tasks.mark_waiting,
            task_id, wait_kind=wait_kind, wait_key=wait_key, wait_json=wait_json,
            current_step=current_step, next_step=next_step, result_json=result_json,
        )

    async def resume_task(
        self,
        task_id: int,
        *,
        status: str = "resumed",
        current_step: str | None = None,
        next_step: str | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> None:
        await self._write_with_retry(
            self._tasks.resume_task,
            task_id, status=status, current_step=current_step,
            next_step=next_step, result_json=result_json,
        )

    async def update_task_data(self, task_id: int, extra_dict: dict[str, Any]) -> None:
        await self._write_with_retry(self._tasks.update_task_data, task_id, extra_dict)

    async def amend_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        goal: str | None = None,
        priority: str | None = None,
        amendment_reason: str = "",
    ) -> bool:
        return await self._write_with_retry(
            self._tasks.amend_task,
            task_id,
            title=title, goal=goal, priority=priority,
            amendment_reason=amendment_reason,
        )

    async def pop_task_inbox(self, task_id: int) -> list[str]:
        return await self._write_with_retry(self._tasks.pop_task_inbox, task_id)

    async def update_task_result(self, task_id: int, result_json: dict[str, Any]) -> None:
        await self._write_with_retry(self._tasks.update_task_result, task_id, result_json)

    async def sync_task_progress(
        self,
        task_id: int,
        *,
        current_step: str | None = None,
        next_step: str | None = None,
    ) -> None:
        await self._write_with_retry(self._tasks.sync_task_progress, task_id, current_step=current_step, next_step=next_step)

    async def add_run(
        self, *, task_id: int = 0, **kwargs: Any
    ) -> int:
        return await self._write_with_retry(self._runs.add_run, task_id=task_id, **kwargs)

    async def get_run_by_id(self, run_id: int) -> Run | None:
        return await self._runs.get_run_by_id(run_id)

    async def list_runs(
        self,
        *,
        task_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Run]:
        return await self._runs.list_runs(task_id=task_id, status=status, limit=limit)

    async def update_run(
        self,
        run_id: int,
        *,
        task_id: int | None = None,
        status: str | None = None,
        output_json: dict[str, Any] | None = None,
        log_text: str | None = None,
        error_text: str | None = None,
        session_id: str | None = None,
        model_tier: str | None = None,
        progress: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        await self._write_with_retry(
            self._runs.update_run,
            run_id, task_id=task_id, status=status, output_json=output_json,
            log_text=log_text, error_text=error_text, session_id=session_id,
            model_tier=model_tier, progress=progress, extras=extras,
        )

    async def cancel_stale_runs(self, stale_after_seconds: int = 600) -> int:
        """清理进程重启后遗留的非终态 Run（Phase 3d 崩溃恢复）。"""
        return await self._write_with_retry(self._runs.cancel_stale_runs, stale_after_seconds)

    async def get_pending_runs(self, *, limit: int = 10) -> list:
        """查询 status='pending' 的 Run（Phase 3d 调度器轮询用）。"""
        return await self._runs.get_pending_runs(limit=limit)

    async def add_meta_reflection(
        self,
        *,
        reflection_id: str,
        target_kind: str,
        trigger: str,
        loop_level: str,
        diagnosis: str,
        proposal: str,
        verification_plan: str = "",
        decision: str = "defer",
        task_id: int = 0,
        run_id: int = 0,
        tool_name: str = "",
        extras: dict[str, Any] | None = None,
    ) -> None:
        await self._write_with_retry(
            self._meta_reflections.add_meta_reflection,
            reflection_id=reflection_id, target_kind=target_kind, trigger=trigger,
            loop_level=loop_level, diagnosis=diagnosis, proposal=proposal,
            verification_plan=verification_plan, decision=decision,
            task_id=task_id, run_id=run_id, tool_name=tool_name, extras=extras,
        )

    async def list_meta_reflections(self, limit: int = 20, loop_level: str | None = None) -> list[MetaReflection]:
        return await self._meta_reflections.list_meta_reflections(limit=limit, loop_level=loop_level)

    # ── 生命史账本 ────────────────────────────────────────────────────────

    async def ledger_append(
        self,
        op: str,
        key: str,
        value: str,
        *,
        scope: str = "task",
        source: str = "",
        accepted: bool = True,
        run_id: int = 0,
        reason: str = "",
        proposal_hash: str = "",
        decision_basis: str = "",
    ) -> None:
        await self._write_with_retry(
            self._ledger.append,
            op,
            key,
            value,
            scope=scope,
            source=source,
            accepted=accepted,
            run_id=run_id,
            reason=reason,
            proposal_hash=proposal_hash,
            decision_basis=decision_basis,
        )

    async def ledger_recent(self, limit: int = 50) -> list[dict]:
        """返回最近 N 条生命史记录，供 LLM 感知近期状态变化。"""
        return await self._ledger.recent(limit=limit)

    async def ledger_since(self, after_id: int, limit: int = 100) -> list[dict]:
        """增量拉取，供 LLM 对比前后变化做决策。"""
        return await self._ledger.since(after_id, limit=limit)

    async def enqueue_if_absent(
        self,
        title: str,
        goal: str = "",
        priority: str = "normal",
        source: str = "internal",
    ) -> bool:
        return await self._write_with_retry(self._tasks.enqueue_if_absent, title, goal=goal, priority=priority, source=source)

    # ── 失败记录 ─────────────────────────────────────────────────────────

    async def record_failure(self, kind: str, summary: str, context: str = "", task_id: str = "") -> None:
        await self._write_with_retry(self._failures.record_failure, kind, summary, context, task_id)

    async def list_failures(self, limit: int = 20) -> list[Failure]:
        return await self._failures.list_failures(limit)

    async def list_failures_for_task(self, task_id: str, limit: int = 20) -> list[Failure]:
        return await self._failures.list_failures_for_task(task_id, limit)

    async def count_failures_by_kind(self, kind: str) -> int:
        return await self._failures.count_failures_by_kind(kind)

    async def dismiss_failure(self, failure_id: int) -> None:
        await self._write_with_retry(self._failures.dismiss_failure, failure_id)

    # ── Facts KV ─────────────────────────────────────────────────────────

    async def set_fact(self, key: str, value: str, scope: str = "general") -> None:
        await self._write_with_retry(self._facts.set_fact, key, value, scope)

    async def get_fact(self, key: str) -> tuple[str, bool]:
        return await self._facts.get_fact(key)

    async def list_facts(self, prefix: str = "", limit: int = 100) -> list[tuple[str, str]]:
        return await self._facts.list_facts(prefix, limit)

    async def delete_fact(self, key: str) -> None:
        await self._write_with_retry(self._facts.delete_fact, key)

    # ── 调度信号（cron 机制）──────────────────────────────────────────────

    async def add_signal(self, title: str, run_at: str, repeat_secs: int = 0, payload: dict[str, Any] | None = None) -> int:
        return await self._write_with_retry(self._signals.add_signal, title, run_at, repeat_secs, payload)

    async def due_signals(self) -> list[dict[str, Any]]:
        return await self._signals.due_signals()

    async def ack_signal(self, signal_id: int) -> None:
        await self._write_with_retry(self._signals.ack_signal, signal_id)

    async def list_signals(self, limit: int = 30, include_done: bool = False) -> list[dict[str, Any]]:
        return await self._signals.list_signals(limit, include_done)

    async def get_signal(self, signal_id: int) -> dict[str, Any] | None:
        return await self._signals.get_signal(signal_id)

    async def cancel_signal(self, signal_id: int) -> None:
        await self._write_with_retry(self._signals.cancel_signal, signal_id)

    # ── 对话消息（chat IPC）────────────────────────────────────────────────

    async def add_chat_message(self, role: str, content: str, chat_id: str = "") -> int:
        return await self._write_with_retry(self._chat.add_message, role, content, chat_id=chat_id)

    async def has_pending_chat_message(self) -> bool:
        return await self._chat.has_pending_message()

    async def pop_pending_chat_message(self) -> dict[str, Any] | None:
        return await self._chat.pop_pending_message()

    async def drain_pending_for_chat(self, chat_id: str, after_id: int) -> list[dict[str, Any]]:
        return await self._chat.drain_pending_for_chat(chat_id, after_id)

    async def mark_chat_messages_processed(self, message_ids: list[int] | tuple[int, ...]) -> None:
        await self._write_with_retry(self._chat.mark_messages_processed, message_ids)

    async def release_chat_messages(self, message_ids: list[int] | tuple[int, ...]) -> None:
        await self._write_with_retry(self._chat.release_messages, message_ids)

    async def get_chat_messages_since(self, since_id: int = 0, chat_id: str = "") -> list[dict[str, Any]]:
        return await self._chat.get_messages_since(since_id, chat_id=chat_id)

    async def get_recent_chat_messages(self, limit: int = 6, chat_id: str = "") -> list[dict[str, Any]]:
        return await self._chat.get_recent_messages(limit, chat_id=chat_id)

    async def reset_in_progress_tasks(self) -> int:
        raise RuntimeError("task reset binding missing")


def _bind_task_store() -> None:
    """延迟绑定：在 TaskStore 定义后，再将实现函数混入类。"""
    from .impl import bind_task_store

    bind_task_store(TaskStore)


_bind_task_store()


__all__ = [
    "OPEN_TASK_STATUSES",
    "RUNNABLE_TASK_STATUSES",
    "TASK_DUPLICATE_REUSE_SCORE",
    "TASK_SIMILARITY_CONTEXT_SCORE",
    "ChatMessageStore",
    "FactStore",
    "Failure",
    "FailureStore",
    "IngressStore",
    "IngressWriter",
    "LedgerStore",
    "MetaReflection",
    "MetaReflectionStore",
    "Run",
    "RunStore",
    "SignalStore",
    "Task",
    "TaskStateStore",
    "TaskStore",
    "build_fact_upsert",
    "build_task_data",
    "build_task_insert",
    "build_task_run_result_patch",
    "build_task_similarity_query",
    "sanitize_chat_content",
]
