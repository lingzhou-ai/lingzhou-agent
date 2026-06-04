"""语义记忆维护器官。

SemanticMemory 负责存取；SemanticMaintenance 负责启动预算、索引恢复和健康状态。
这让“记忆存储”和“记忆新陈代谢”分离，避免存储构造函数承担生命周期职责。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import SemanticMemory

_log = logging.getLogger("lingzhou.memory.semantic")


@dataclass
class SemanticMaintenanceStatus:
    state: str = "idle"
    deferred: bool = False
    last_error: str = ""
    last_startup_seconds: float = 0.0
    last_background_seconds: float = 0.0


class SemanticMaintenance:
    """语义记忆维护器官：管理启动维护与后台索引恢复。"""

    def __init__(self, memory: SemanticMemory) -> None:
        self._memory = memory
        self.status = SemanticMaintenanceStatus()
        self._thread: threading.Thread | None = None

    def run_startup(self, *, max_seconds: float) -> None:
        started = time.monotonic()
        self.status.state = "startup"
        self.status.last_error = ""
        memory = self._memory
        memory._maintenance_deferred = False
        with memory._db_session():
            stage_started = time.monotonic()
            memory._migrate()
            _log.info("[semantic] 启动阶段 migrate 完成 dt=%.3fs", time.monotonic() - stage_started)
            stage_started = time.monotonic()
            memory._sync_from_files(max_seconds=max_seconds)
            _log.info("[semantic] 启动阶段 sync_from_files 完成 dt=%.3fs", time.monotonic() - stage_started)
            stage_started = time.monotonic()
            memory._migrate_interlocutor_profiles(max_seconds=max_seconds)
            _log.info("[semantic] 启动阶段 migrate_profiles 完成 dt=%.3fs", time.monotonic() - stage_started)
            stage_started = time.monotonic()
            memory._validate_and_repair_index()
            _log.info("[semantic] 启动阶段 validate_index 完成 dt=%.3fs", time.monotonic() - stage_started)
        elapsed = time.monotonic() - started
        self.status.last_startup_seconds = elapsed
        self.status.deferred = bool(memory._maintenance_deferred)
        self.status.state = "deferred" if self.status.deferred else "idle"
        _log.info("[semantic] 启动完成 dt=%.3fs", elapsed)
        if self.status.deferred:
            self.start_background()

    def start_background(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._background_worker,
            name="lingzhou-semantic-maintenance",
            daemon=True,
        )
        self._thread.start()

    def _background_worker(self) -> None:
        try:
            self.run_background()
        except Exception as exc:
            self.status.state = "failed"
            self.status.last_error = f"{exc.__class__.__name__}: {exc}"
            _log.exception("[semantic] 后台索引恢复失败")

    def run_background(self) -> None:
        started = time.monotonic()
        memory = self._memory
        self.status.state = "running"
        self.status.last_error = ""
        _log.info("[semantic] 后台索引恢复启动")
        with memory._db_session():
            stage_started = time.monotonic()
            memory._sync_from_files(max_seconds=None)
            _log.info("[semantic] 后台 JSON→索引同步完成 dt=%.3fs", time.monotonic() - stage_started)
        with memory._db_session():
            stage_started = time.monotonic()
            memory._migrate_embeddings(batch_limit=5000)
            _log.info("[semantic] 后台旧 embedding 迁移完成 dt=%.3fs", time.monotonic() - stage_started)
        memory._maintenance_deferred = False
        elapsed = time.monotonic() - started
        self.status.last_background_seconds = elapsed
        self.status.deferred = False
        self.status.state = "idle"
        _log.info("[semantic] 后台索引恢复完成 dt=%.3fs", elapsed)

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.status.state,
            "deferred": self.status.deferred,
            "last_error": self.status.last_error,
            "last_startup_seconds": self.status.last_startup_seconds,
            "last_background_seconds": self.status.last_background_seconds,
        }
