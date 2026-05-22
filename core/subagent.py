"""core/subagent.py — 子灵（完整实现）。

子灵是灵舟派生的有界任务执行体，提供四层能力：
  Tier-0（只读原型）: 共享父灵所有记忆，工具访问受限
  Tier-1（完整子灵）: 独立 memory namespace（EpisodicMemory + SemanticMemory）
  Tier-2（Ethos 继承）: 从父灵 soul:ethos_baseline 派生初始价值观
  Tier-3（结果合并）: SubagentResult 携带待吸收的语义记忆节点

设计原则：
  - 轻量：不运行完整 OCC 情绪 / Ethos 推导，只做 judgment + execution 循环
  - 只读默认：不写入父灵 TaskStore / SemanticMemory（isolated_memory=True 时独立写）
  - 可观测：每 tick 关键结果写入 observations，随 SubagentResult 返回
  - 可吸收：关键语义记忆可随结果返回，供父灵 tools/subagent_ops.absorb 合并
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

_log = logging.getLogger("lingzhou.subagent")

if TYPE_CHECKING:
    from core.config import Config
    from core.judgment import JudgmentLayer
    from core.execution import ExecutionLayer
    from memory.working import WorkingMemory
    from memory.episodic import EpisodicMemory
    from memory.semantic import SemanticMemory
    from memory.task_store import TaskStore
    from tools.registry import ToolRegistry, ToolContext
    from core.perception import EmotionState, Percept

# ── 默认黑名单：子灵不能调用的高权限工具 ────────────────────────────────────────
_DEFAULT_BLOCKED_TOOLS: frozenset[str] = frozenset({
    "evolution.evolve",
    "evolution.synthesize",
    "soul.update",
    "ethos.evolve",
    "skill.evolve",
    "subagent.run",  # 禁止递归
})

_READONLY_BLOCKED_TOOL_NAMES: frozenset[str] = frozenset({
    "config.set",
    "memory.add_semantic",
    "memory.set_fact",
    "schedule.add",
    "schedule.ack",
    "schedule.cancel",
    "task.plan",
})

_READONLY_ALLOWED_TASK_TOOLS: frozenset[str] = frozenset({
    "task.ask",
    "task.list",
})

_LOCAL_FACT_PREFIXES: tuple[str, ...] = (
    "durable_failure:",
)

_LOCAL_FACT_KEYS: frozenset[str] = frozenset({
    "control:durable_failure_policy",
})


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_locally_absorbable_fact(key: str, scope: str) -> bool:
    if scope == "system":
        return True
    if key in _LOCAL_FACT_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in _LOCAL_FACT_PREFIXES)


def _is_readonly_blocked_tool(name: str, manifest: Any | None) -> bool:
    if not name:
        return True
    if name in _READONLY_BLOCKED_TOOL_NAMES:
        return True
    if name.startswith("task.") and name not in _READONLY_ALLOWED_TASK_TOOLS:
        return True
    if manifest is not None and getattr(manifest, "progress_category", "") == "mutation":
        return True
    return False


class _SubagentReadonlyViolation(RuntimeError):
    pass


class _SubagentTaskStoreView:
    """父灵 TaskStore 的子灵隔离视图：读透传，运行期 bookkeeping 本地吸收。"""

    def __init__(self, parent: Any) -> None:
        self._parent = parent
        self._local_facts: dict[str, tuple[str, str]] = {}
        self._local_failures: list[Any] = []
        self._local_runs: dict[int, dict[str, Any]] = {}
        self._local_meta_reflections: list[Any] = []
        self._next_run_id = -1

    def _reject(self, action: str) -> _SubagentReadonlyViolation:
        return _SubagentReadonlyViolation(f"子灵只读模式禁止修改父灵状态: {action}")

    async def get_active(self) -> Any:
        return await self._parent.get_active()

    async def get_task_by_id(self, task_id: int) -> Any:
        return await self._parent.get_task_by_id(task_id)

    async def list_tasks(self, *args: Any, **kwargs: Any) -> list[Any]:
        return await self._parent.list_tasks(*args, **kwargs)

    async def list_runs(self, *args: Any, **kwargs: Any) -> list[Any]:
        return await self._parent.list_runs(*args, **kwargs)

    async def add_run(self, **kwargs: Any) -> int:
        run_id = self._next_run_id
        self._next_run_id -= 1
        self._local_runs[run_id] = {
            "id": run_id,
            "task_id": kwargs.get("task_id", 0),
            "run_type": kwargs.get("run_type", "tool_chain"),
            "worker_type": kwargs.get("worker_type", "tool-chain-worker"),
            "status": kwargs.get("status", "running"),
            "input_json": dict(kwargs.get("input_json") or {}),
            "tool_name": kwargs.get("tool_name", ""),
            "model_tier": kwargs.get("model_tier", ""),
            "created_at": _utc_now_iso(),
            "started_at": _utc_now_iso(),
            "completed_at": "",
            "output_json": {},
            "error_text": "",
            "log_text": "",
            "session_id": "",
            "progress": "",
            "extras": {},
        }
        return run_id

    async def update_run(self, run_id: int, **kwargs: Any) -> None:
        run = self._local_runs.get(run_id)
        if run is None:
            return
        run.update({k: v for k, v in kwargs.items() if v is not None})
        status = str(kwargs.get("status") or run.get("status") or "")
        if status in {"succeeded", "failed", "cancelled"}:
            run["completed_at"] = _utc_now_iso()

    async def record_failure(
        self,
        kind: str,
        summary: str,
        context: str = "",
        task_id: str = "",
    ) -> None:
        from memory.task_store import Failure

        self._local_failures.append(Failure(
            id=-(len(self._local_failures) + 1),
            kind=kind,
            dismissed=False,
            created_at=_utc_now_iso(),
            summary=summary,
            context=context,
            task_id=task_id,
        ))

    async def list_failures(self, limit: int = 20) -> list[Any]:
        local = list(self._local_failures[-limit:])
        parent = await self._parent.list_failures(limit=limit)
        return local + list(parent[: max(0, limit - len(local))])

    async def list_failures_for_task(self, task_id: str, limit: int = 20) -> list[Any]:
        local = [item for item in self._local_failures if str(getattr(item, "task_id", "")) == str(task_id)][-limit:]
        parent = await self._parent.list_failures_for_task(task_id, limit=limit)
        return local + list(parent[: max(0, limit - len(local))])

    async def set_fact(self, key: str, value: str, scope: str = "general") -> None:
        if not _is_locally_absorbable_fact(key, scope):
            raise self._reject(f"set_fact:{key}")
        self._local_facts[key] = (value, scope)

    async def get_fact(self, key: str) -> tuple[str, bool]:
        local = self._local_facts.get(key)
        if local is not None:
            return local[0], True
        return await self._parent.get_fact(key)

    async def list_facts(self, prefix: str = "", limit: int = 100) -> list[tuple[str, str]]:
        local = [
            (key, value)
            for key, (value, _) in self._local_facts.items()
            if not prefix or key.startswith(prefix)
        ]
        parent = await self._parent.list_facts(prefix=prefix, limit=limit)
        merged = list(local[-limit:])
        seen = {key for key, _ in merged}
        for item in parent:
            if item[0] in seen:
                continue
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    async def update_task_result(self, task_id: int, result_json: dict[str, Any]) -> None:
        return None

    async def add_meta_reflection(self, **kwargs: Any) -> None:
        self._local_meta_reflections.append(dict(kwargs))

    async def list_meta_reflections(self, limit: int = 20, loop_level: str | None = None) -> list[Any]:
        return await self._parent.list_meta_reflections(limit=limit, loop_level=loop_level)

    async def due_signals(self) -> list[dict[str, Any]]:
        return await self._parent.due_signals()

    async def list_signals(self, limit: int = 30, include_done: bool = False) -> list[dict[str, Any]]:
        return await self._parent.list_signals(limit=limit, include_done=include_done)

    async def get_signal(self, signal_id: int) -> dict[str, Any] | None:
        return await self._parent.get_signal(signal_id)

    async def add_task(self, *args: Any, **kwargs: Any) -> Any:
        raise self._reject("add_task")

    async def update_status(self, *args: Any, **kwargs: Any) -> Any:
        raise self._reject("update_status")

    async def update_task_data(self, *args: Any, **kwargs: Any) -> Any:
        raise self._reject("update_task_data")

    async def add_signal(self, *args: Any, **kwargs: Any) -> Any:
        raise self._reject("add_signal")

    async def ack_signal(self, *args: Any, **kwargs: Any) -> Any:
        raise self._reject("ack_signal")

    async def cancel_signal(self, *args: Any, **kwargs: Any) -> Any:
        raise self._reject("cancel_signal")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._parent, name)


class _SubagentEpisodicView:
    """父灵情节记忆的只读视图，子灵运行日志不回写父灵。"""

    def __init__(self, parent: Any) -> None:
        self._parent = parent

    def record_event(self, *args: Any, **kwargs: Any) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._parent, name)


class _SubagentSemanticView:
    """父灵语义记忆的只读视图，子灵反思与 run 结晶不回写父灵。"""

    def __init__(self, parent: Any) -> None:
        self._parent = parent

    def upsert(self, node: Any) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._parent, name)


# ── 数据模型 ────────────────────────────────────────────────────────────────────

@dataclass
class SubagentConfig:
    """子灵执行配置。"""
    goal: str
    max_ticks: int = 8
    allowed_tools: list[str] | None = None    # None = 继承所有（减去黑名单）
    blocked_tools: list[str] | None = None    # 额外黑名单（追加）
    subagent_id: str = field(default_factory=lambda: f"sub-{uuid.uuid4().hex[:8]}")
    label: str = ""                           # 可选标签（竞争进化时标识候选版本）
    # Tier-1: 独立 memory namespace
    isolated_memory: bool = False             # True = 使用独立 EpisodicMemory + SemanticMemory
    # Tier-2: Ethos 继承
    inherit_ethos: bool = True                # True = 从父灵 soul:ethos_baseline 派生价值观


@dataclass
class SubagentResult:
    """子灵执行结果，注入到父灵 WM；可选携带待吸收的语义记忆节点。"""
    subagent_id: str
    goal: str
    ticks_run: int
    completed: bool          # LLM 判断 "wait"（无任务）= 认为完成
    error: str | None
    last_summary: str        # 最后一次工具执行摘要
    observations: list[str]  # 每 tick 的关键观察
    label: str = ""
    # Tier-3: 结果合并 — 子灵记录的语义记忆节点，供父灵选择性吸收
    absorbed_memories: list[dict[str, Any]] = field(default_factory=list)
    # 子灵独立记忆目录路径（供吸收时引用）
    memory_dir: str = ""

    def to_wm_content(self) -> str:
        status = "完成" if self.completed else ("错误" if self.error else "未完成")
        parts = [f"子灵[{self.subagent_id}] 目标={self.goal!r} 状态={status} ticks={self.ticks_run}"]
        if self.error:
            parts.append(f"错误: {self.error}")
        if self.observations:
            parts.append("关键观察:")
            for obs in self.observations[-5:]:  # 最近 5 条
                parts.append(f"  · {obs}")
        if self.last_summary:
            parts.append(f"最终结果: {self.last_summary}")
        if self.absorbed_memories:
            parts.append(f"可吸收记忆节点: {len(self.absorbed_memories)} 条（调用 subagent.absorb 合并）")
        return "\n".join(parts)


# ── 工具过滤代理 ────────────────────────────────────────────────────────────────

class _FilteredRegistry:
    """对 ToolRegistry 的只读代理，限制可调用的工具集合。"""

    def __init__(
        self,
        real: "ToolRegistry",
        allowed: set[str] | None,
        blocked: set[str],
    ) -> None:
        self._real = real
        self._allowed = allowed   # None = 不限制 allowed（只走 blocked）
        self._blocked = blocked

    def _is_visible(self, name: str) -> bool:
        if name in self._blocked:
            return False
        entry = self._real.get(name)
        manifest = entry.manifest if entry is not None else None
        if _is_readonly_blocked_tool(name, manifest):
            return False
        if self._allowed is not None:
            return name in self._allowed
        return True

    def get(self, name: str):
        if not self._is_visible(name):
            return None
        return self._real.get(name)

    def list_manifests(self):
        return [m for m in self._real.list_manifests() if self._is_visible(m.name)]

    def list_manifests_as_dict(self):
        return [m for m in self._real.list_manifests_as_dict() if self._is_visible(m["name"])]

    # 透传 discover / reload_tool（子灵不调用这些，但防止 AttributeError）
    def discover(self, *args, **kwargs):
        return None

    def reload_tool(self, *args, **kwargs):
        return False


# ── 辅助：读取父灵 Ethos 基线 ────────────────────────────────────────────────────

async def _load_parent_ethos(task_store: "TaskStore") -> dict[str, float]:
    """从父灵 TaskStore 读取 soul:ethos_baseline，解析失败返回空 dict。"""
    try:
        ethos_json, found = await task_store.get_fact("soul:ethos_baseline")
        if not found or not ethos_json:
            return {}
        return json.loads(ethos_json)
    except Exception:
        return {}


# ── 子灵运行器 ──────────────────────────────────────────────────────────────────

class SubagentRunner:
    """
    完整子灵运行器，支持 Tier-0 ~ Tier-3 全部能力。

    Tier-0: judgment + execution 循环，无完整情绪/Ethos 机制
    Tier-1: isolated_memory=True 时使用独立 EpisodicMemory + SemanticMemory
    Tier-2: inherit_ethos=True 时继承父灵价值观基线
    Tier-3: 关键语义记忆随 SubagentResult 返回
    """

    def __init__(
        self,
        sub_cfg: SubagentConfig,
        *,
        judgment: "JudgmentLayer",
        execution: "ExecutionLayer",
        parent_ctx: "ToolContext",
        registry: "ToolRegistry",
    ) -> None:
        self._sub_cfg = sub_cfg
        self._judgment = judgment
        self._execution = execution
        self._parent_ctx = parent_ctx
        self._registry = registry

    # ── 公开接口 ────────────────────────────────────────────────────────────────

    async def run(self) -> SubagentResult:
        """执行子灵 tick 循环，返回 SubagentResult。"""
        from memory.working import WorkingMemory, WMItem
        from core.perception import EmotionState, Percept, derive_ethos_state, EthosValues
        from tools.registry import ToolContext

        cfg = self._sub_cfg
        sub_id = cfg.subagent_id
        parent_cfg = self._parent_ctx.config

        _log.info("[subagent][%s] 启动 goal=%r max_ticks=%d isolated=%s inherit_ethos=%s",
                  sub_id, cfg.goal, cfg.max_ticks, cfg.isolated_memory, cfg.inherit_ethos)

        # ── Tier-1: 独立 memory namespace ──────────────────────────────────────
        sub_memory_dir = ""
        if cfg.isolated_memory:
            base_mem_dir = parent_cfg.memory_dir
            sub_mem_path = base_mem_dir / "subagents" / sub_id
            sub_mem_path.mkdir(parents=True, exist_ok=True)
            sub_memory_dir = str(sub_mem_path)

            from memory.episodic import EpisodicMemory
            from memory.semantic import SemanticMemory
            sub_episodic = EpisodicMemory(
                sub_mem_path / "episodic",
                max_events=getattr(parent_cfg.memory, "max_events", 0),
            )
            sub_semantic = SemanticMemory(sub_mem_path / "semantic")
            _log.debug("[subagent][%s] 独立记忆目录: %s", sub_id, sub_mem_path)
        else:
            # Tier-0: 共享父灵记忆（只读）
            sub_episodic = _SubagentEpisodicView(self._parent_ctx.episodic)
            sub_semantic = _SubagentSemanticView(self._parent_ctx.semantic)

        sub_task_store = _SubagentTaskStoreView(self._parent_ctx.task_store)

        # ── Tier-2: Ethos 继承 ─────────────────────────────────────────────────
        inherited_ethos_state = None
        if cfg.inherit_ethos:
            baseline_dict = await _load_parent_ethos(self._parent_ctx.task_store)
            if baseline_dict:
                # 用与父灵相同的 derive_ethos_state 逻辑，传入父灵基线
                inherited_ethos_state = derive_ethos_state(
                    failure_count=0,
                    high_error_streak=0,
                    has_active_task=True,
                    has_next_step=True,
                    perception_trend="neutral",
                    emotion_down_regulate_streak=0,
                    baseline=baseline_dict,
                )
                _log.debug("[subagent][%s] 已继承父灵 Ethos 基线 keys=%s",
                           sub_id, list(baseline_dict.keys()))

        # ── 独立 WM（不影响父灵）──────────────────────────────────────────────
        sub_wm = WorkingMemory(
            capacity=getattr(parent_cfg.memory, "working_capacity", 20),
        )
        sub_wm.add(WMItem(kind="goal", content=f"子灵任务: {cfg.goal}", priority=1.0))

        # 受限工具集
        blocked = set(_DEFAULT_BLOCKED_TOOLS)
        if cfg.blocked_tools:
            blocked.update(cfg.blocked_tools)
        allowed: set[str] | None = set(cfg.allowed_tools) if cfg.allowed_tools else None
        filtered_reg = _FilteredRegistry(self._registry, allowed, blocked)

        # 中性情绪（子灵不运行 OCC 情绪模型）
        neutral_emotion = EmotionState()

        observations: list[str] = []
        last_summary = ""
        completed = False
        error_msg: str | None = None
        ticks_run = 0

        for tick in range(cfg.max_ticks):
            ticks_run = tick + 1

            # 最小感知快照
            percept = Percept(summary=cfg.goal if tick == 0 else "")

            try:
                output = await self._judgment.decide(
                    percept,
                    sub_wm,
                    sub_task_store,
                    sub_episodic,
                    sub_semantic,
                    neutral_emotion,
                    user_message=cfg.goal if tick == 0 else "",
                    ethos_state=inherited_ethos_state,  # Tier-2: 传入继承的 Ethos
                )
            except Exception as exc:
                error_msg = f"judgment 异常: {exc}"
                _log.exception("[subagent][%s] tick=%d judgment 异常", sub_id, tick)
                break

            decision = output.decision

            if decision == "wait":
                completed = True
                _log.info("[subagent][%s] tick=%d 决定 wait，任务完成", sub_id, tick)
                break

            if decision != "act":
                completed = (decision == "pause")
                break

            # 构造子灵专用 ToolContext（使用独立记忆）
            sub_ctx = ToolContext(
                config=parent_cfg,
                wm=sub_wm,
                task_store=sub_task_store,
                episodic=sub_episodic,
                semantic=sub_semantic,
                emotion=neutral_emotion,
                judgment=self._judgment,
                execution=self._execution,
                registry=filtered_reg,
            )

            # 注入受限 registry（临时替换，执行后恢复）
            orig_registry = self._execution._registry  # type: ignore[attr-defined]
            try:
                self._execution._registry = filtered_reg  # type: ignore[attr-defined]
                result = await self._execution.dispatch(output, sub_ctx)
            finally:
                self._execution._registry = orig_registry  # type: ignore[attr-defined]

            last_summary = result.summary
            observations.append(f"[tick={ticks_run}] {result.summary[:200]}")

            sub_wm.add(WMItem(
                kind=result.kind,
                content=result.summary[:400],
                priority=result.priority,
            ))

            _log.debug("[subagent][%s] tick=%d act=%s summary=%s",
                       sub_id, tick, output.chosen_action_id, result.summary[:100])

        # ── Tier-3: 收集待合并的语义记忆节点 ─────────────────────────────────
        absorbed_memories: list[dict[str, Any]] = []
        if cfg.isolated_memory:
            try:
                # 检索子灵语义记忆中评分最高的节点（最多 10 条）
                nodes = sub_semantic.search(cfg.goal, top_k=10)
                absorbed_memories = [n.to_dict() if hasattr(n, "to_dict") else vars(n) for n in nodes]
            except Exception:
                pass  # 内存检索失败不影响结果

        _log.info("[subagent][%s] 结束 ticks=%d completed=%s error=%s memories=%d",
                  sub_id, ticks_run, completed, error_msg, len(absorbed_memories))

        return SubagentResult(
            subagent_id=sub_id,
            goal=cfg.goal,
            ticks_run=ticks_run,
            completed=completed,
            error=error_msg,
            last_summary=last_summary,
            observations=observations,
            label=cfg.label,
            absorbed_memories=absorbed_memories,
            memory_dir=sub_memory_dir,
        )


# ── 工厂函数 ────────────────────────────────────────────────────────────────────

def make_subagent_runner(
    sub_cfg: SubagentConfig,
    parent_ctx: "ToolContext",
    judgment: "JudgmentLayer",
    execution: "ExecutionLayer",
    registry: "ToolRegistry",
) -> SubagentRunner:
    """根据父灵上下文构造子灵 Runner，供 tools/subagent_ops.py 调用。"""
    return SubagentRunner(
        sub_cfg,
        judgment=judgment,
        execution=execution,
        parent_ctx=parent_ctx,
        registry=registry,
    )
