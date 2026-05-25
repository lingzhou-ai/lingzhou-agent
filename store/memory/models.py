"""store/memory/models.py — 持久化层公共数据类（DTO）。

所有 Store 子类和 memory 层共用这些类；数据类本身不依赖任何上层模块。
DDL 常量也集中于此，避免 schema 与数据类分离。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ── 状态常量 ─────────────────────────────────────────────────────────────────

OPEN_TASK_STATUSES: tuple[str, ...] = (
    "pending", "ready", "in_progress", "resumed", "waiting"
)
RUNNABLE_TASK_STATUSES: tuple[str, ...] = (
    "pending", "ready", "in_progress", "resumed"
)

_TASK_CORE_DATA_KEYS: frozenset[str] = frozenset({
    "goal", "source", "next_step", "chain_id", "parent_task_id",
    "current_step", "wait_kind", "wait_key", "state_json", "wait_json",
    "result_json", "async_job_id", "model_tier",
})

# ── DDL ──────────────────────────────────────────────────────────────────────

DDL_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'pending',
    priority   TEXT    NOT NULL DEFAULT 'normal',
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    data       TEXT    NOT NULL DEFAULT '{}'
);
"""

DDL_FAILURES = """
CREATE TABLE IF NOT EXISTS failures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,
    dismissed  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    data       TEXT    NOT NULL DEFAULT '{}'
);
"""

DDL_FACTS = """
CREATE TABLE IF NOT EXISTS facts (
    key        TEXT PRIMARY KEY,
    value      TEXT    NOT NULL DEFAULT '',
    scope      TEXT    NOT NULL DEFAULT 'general',
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

DDL_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    run_at      TEXT    NOT NULL,
    repeat_secs INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'pending',
    payload     TEXT    NOT NULL DEFAULT '{}',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_signals_pending
    ON signals(run_at) WHERE status='pending';
"""

DDL_CHAT = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    session_id TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'pending',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_pending
    ON chat_messages(status, id) WHERE role='user';
"""

DDL_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      INTEGER NOT NULL DEFAULT 0,
    run_type     TEXT    NOT NULL DEFAULT 'tool_chain',
    worker_type  TEXT    NOT NULL DEFAULT 'tool-chain-worker',
    status       TEXT    NOT NULL DEFAULT 'pending',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    started_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT    NOT NULL DEFAULT '',
    data         TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_runs_task_status
    ON runs(task_id, status, id DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status
    ON runs(status, id DESC);
"""

DDL_META_REFLECTIONS = """
CREATE TABLE IF NOT EXISTS meta_reflections (
    id                TEXT PRIMARY KEY,
    target_kind       TEXT NOT NULL,
    trigger           TEXT NOT NULL,
    loop_level        TEXT NOT NULL,
    diagnosis         TEXT NOT NULL,
    proposal          TEXT NOT NULL,
    verification_plan TEXT NOT NULL DEFAULT '',
    decision          TEXT NOT NULL DEFAULT 'defer',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    data              TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_meta_reflections_loop
    ON meta_reflections(loop_level, created_at DESC);
"""

DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_title
    ON tasks(title);
CREATE INDEX IF NOT EXISTS idx_failures_active
    ON failures(dismissed, id DESC);
CREATE INDEX IF NOT EXISTS idx_failures_kind
    ON failures(kind, dismissed);
"""

ALL_DDL: list[str] = [
    DDL_TASKS, DDL_FAILURES, DDL_FACTS, DDL_SIGNALS,
    DDL_CHAT, DDL_RUNS, DDL_META_REFLECTIONS, DDL_INDEXES,
]

# ── 数据类 ────────────────────────────────────────────────────────────────────

@dataclass
class Task:
    id: int
    title: str
    status: str
    priority: str
    created_at: str
    goal: str = ""
    source: str = "external"
    next_step: str = ""
    chain_id: str = ""
    parent_task_id: str = ""
    current_step: str = ""
    wait_kind: str = ""
    wait_key: str = ""
    state_json: dict[str, Any] = field(default_factory=dict)
    wait_json: dict[str, Any] = field(default_factory=dict)
    result_json: dict[str, Any] = field(default_factory=dict)
    async_job_id: str = ""
    model_tier: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Any) -> "Task":
        rid, title, status, priority, created_at, data_raw = row
        try:
            data: dict[str, Any] = json.loads(data_raw or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return cls(
            id=rid,
            title=title,
            status=status,
            priority=priority,
            created_at=created_at,
            goal=data.pop("goal", ""),
            source=data.pop("source", "external"),
            next_step=data.pop("next_step", ""),
            chain_id=data.pop("chain_id", ""),
            parent_task_id=data.pop("parent_task_id", ""),
            current_step=data.pop("current_step", ""),
            wait_kind=data.pop("wait_kind", ""),
            wait_key=data.pop("wait_key", ""),
            state_json=data.pop("state_json", {}) or {},
            wait_json=data.pop("wait_json", {}) or {},
            result_json=data.pop("result_json", {}) or {},
            async_job_id=data.pop("async_job_id", ""),
            model_tier=data.pop("model_tier", ""),
            extras=data,
        )

    def to_data_json(self) -> str:
        d: dict[str, Any] = {
            "goal": self.goal,
            "source": self.source,
            "next_step": self.next_step,
            "chain_id": self.chain_id,
            "parent_task_id": self.parent_task_id,
            "current_step": self.current_step,
            "wait_kind": self.wait_kind,
            "wait_key": self.wait_key,
            "state_json": self.state_json,
            "wait_json": self.wait_json,
            "result_json": self.result_json,
            "async_job_id": self.async_job_id,
            "model_tier": self.model_tier,
        }
        d.update({k: v for k, v in self.extras.items() if k not in _TASK_CORE_DATA_KEYS})
        return json.dumps(d, ensure_ascii=False)


@dataclass
class Failure:
    id: int
    kind: str
    dismissed: bool
    created_at: str
    summary: str = ""
    context: str = ""
    task_id: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Any) -> "Failure":
        rid, kind, dismissed, created_at, data_raw = row
        try:
            data: dict[str, Any] = json.loads(data_raw or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return cls(
            id=rid,
            kind=kind,
            dismissed=bool(dismissed),
            created_at=created_at,
            summary=data.pop("summary", ""),
            context=data.pop("context", ""),
            task_id=data.pop("task_id", ""),
            extras=data,
        )


@dataclass
class Run:
    id: int
    task_id: int
    run_type: str
    worker_type: str
    status: str
    created_at: str
    started_at: str = ""
    completed_at: str = ""
    input_json: dict[str, Any] = field(default_factory=dict)
    output_json: dict[str, Any] = field(default_factory=dict)
    log_text: str = ""
    error_text: str = ""
    tool_name: str = ""
    session_id: str = ""
    model_tier: str = ""
    progress: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Any) -> "Run":
        rid, task_id, run_type, worker_type, status, created_at, started_at, completed_at, data_raw = row
        try:
            data: dict[str, Any] = json.loads(data_raw or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return cls(
            id=rid,
            task_id=task_id,
            run_type=run_type,
            worker_type=worker_type,
            status=status,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            input_json=data.pop("input_json", {}) or {},
            output_json=data.pop("output_json", {}) or {},
            log_text=data.pop("log_text", ""),
            error_text=data.pop("error_text", ""),
            tool_name=data.pop("tool_name", ""),
            session_id=data.pop("session_id", ""),
            model_tier=data.pop("model_tier", ""),
            progress=data.pop("progress", ""),
            extras=data,
        )

    def to_data_json(self) -> str:
        data: dict[str, Any] = {
            "input_json": self.input_json,
            "output_json": self.output_json,
            "log_text": self.log_text,
            "error_text": self.error_text,
            "tool_name": self.tool_name,
            "session_id": self.session_id,
            "model_tier": self.model_tier,
            "progress": self.progress,
        }
        data.update(self.extras)
        return json.dumps(data, ensure_ascii=False)


@dataclass
class MetaReflection:
    id: str
    target_kind: str
    trigger: str
    loop_level: str
    diagnosis: str
    proposal: str
    verification_plan: str
    decision: str
    created_at: str
    task_id: int = 0
    run_id: int = 0
    tool_name: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Any) -> "MetaReflection":
        rid, target_kind, trigger, loop_level, diagnosis, proposal, verification_plan, decision, created_at, data_raw = row
        try:
            data: dict[str, Any] = json.loads(data_raw or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return cls(
            id=str(rid),
            target_kind=target_kind,
            trigger=trigger,
            loop_level=loop_level,
            diagnosis=diagnosis,
            proposal=proposal,
            verification_plan=verification_plan,
            decision=decision,
            created_at=created_at,
            task_id=int(data.pop("task_id", 0) or 0),
            run_id=int(data.pop("run_id", 0) or 0),
            tool_name=str(data.pop("tool_name", "") or ""),
            extras=data,
        )

    def to_data_json(self) -> str:
        data: dict[str, Any] = {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
        }
        data.update(self.extras)
        return json.dumps(data, ensure_ascii=False)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def build_task_run_result_patch(
    *,
    run_id: int,
    status: str,
    worker_type: str,
    tool_name: str,
    session_id: str,
    summary: str,
    error: str | None,
) -> dict[str, Any]:
    return {
        "last_run_id": int(run_id),
        "last_run_status": str(status or ""),
        "worker_type": str(worker_type or ""),
        "tool_name": str(tool_name or ""),
        "session_id": str(session_id or ""),
        "summary": str(summary or ""),
        "error": error,
    }
