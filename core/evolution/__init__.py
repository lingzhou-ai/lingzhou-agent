from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import sys
from datetime import UTC, datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.metabolic import submit_fact

from .breaker import (
    _is_global_breaker_cooling_down as _is_global_breaker_cooling_down_impl,
)
from .breaker import (
    _is_target_breaker_cooling_down as _is_target_breaker_cooling_down_impl,
)
from .breaker import (
    _load_breaker_fact as _load_breaker_fact_impl,
)
from .breaker import (
    _update_target_breaker_state as _update_target_breaker_state_impl,
)
from .smoke import (
    gather_target_validation_metrics as _gather_target_validation_metrics_impl,
)
from .smoke import (
    process_pending_verifications as _process_pending_verifications_impl,
)
from .smoke import (
    smoke_test_module as _smoke_test_module_impl,
)
from .smoke import (
    write_pending_verification_fact as _write_pending_verification_fact_impl,
)
from .soft import (
    evolve_ethos as _evolve_ethos_impl,
)
from .soft import (
    evolve_model as _evolve_model_impl,
)
from .soft import (
    evolve_prompt as _evolve_prompt_impl,
)
from .soft import (
    evolve_skill as _evolve_skill_impl,
)
from .soft import (
    synthesize_skill as _synthesize_skill_impl,
)
from .tool import (
    _extract_python,
    _score_candidate,
)
from .tool import (
    choose_tool_target_with_llm as _choose_tool_target_with_llm_impl,
)
from .tool import (
    competitive_evolve_tool as _competitive_evolve_tool_impl,
)
from .tool import (
    evolve_tool as _evolve_tool_impl,
)
from .tool import (
    find_tool_path as _find_tool_path_impl,
)
from .tool import (
    promote_candidate as _promote_candidate_impl,
)
from .tool import (
    synthesize_tool as _synthesize_tool_impl,
)
from .types import (
    EvolutionProposal,
    EvolutionResult,
    _breaker_fact_key,
    _clean_old_backups,
    _clear_smoke_failure_artifacts,
    _format_smoke_failure_message,
    _global_breaker_fact_key,
    _parse_ts,
    _persist_smoke_failure_artifacts,
    _smoke_failure_artifact_paths,
    _smoke_failure_summary,
    _summarize_smoke_failure_preview,
    _verification_fact_key,
    _verification_outcome,
)

_log = logging.getLogger("lingzhou.evolution")

if TYPE_CHECKING:
    from core.config import Config
    from store.task import Failure
    from tools.registry import ToolContext, ToolRegistry


class EvolutionEngine:
    """运行时自修改引擎。"""

    def __init__(self, cfg: Config, provider: Any, registry: ToolRegistry) -> None:
        self._cfg = cfg
        self._provider = provider
        self._registry = registry
        self._tools_dir = Path(__file__).parent.parent / "tools"
        self._breaker_fail_threshold = self._cfg.evolution.breaker_fail_threshold
        self._breaker_escalate_threshold = self._cfg.evolution.breaker_escalate_threshold
        self._breaker_cooldown_seconds = self._cfg.evolution.breaker_cooldown_seconds
        self._breaker_global_cooldown_seconds = self._cfg.evolution.breaker_global_cooldown_seconds

    def _reload_module_from_path(self, module_name: str, path: Path) -> None:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not isinstance(spec.loader, SourceFileLoader):
            raise RuntimeError(f"无法加载模块: {module_name}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error("Failed to reload module %s from %s: %s", module_name, path, e)
            raise RuntimeError(f"无法重新加载模块 {module_name}: {e}") from e

    def _restore_file_text(self, path: Path, previous_src: str) -> None:
        path.write_text(previous_src, encoding="utf-8")

    def _is_registered_tool(self, tool_name: str) -> bool:
        entry = self._registry.get(tool_name)
        return entry is not None and entry.manifest.name == tool_name

    @staticmethod
    def _smoke_test_module(new_src: str, module_path: Path, project_root: Path, *, timeout: float = 15.0) -> str | None:
        return _smoke_test_module_impl(None, module_path, new_src, project_root=project_root, timeout=timeout)

    async def _gather_target_validation_metrics(
        self,
        ctx: ToolContext,
        *,
        target: str,
        since: datetime | None = None,
    ) -> dict[str, int]:
        return await _gather_target_validation_metrics_impl(self, ctx, target=target, since=since)

    async def _write_pending_verification_fact(
        self,
        ctx: ToolContext,
        *,
        target: str,
        tool_path: Path,
        backup_path: Path,
    ) -> None:
        await _write_pending_verification_fact_impl(self, ctx, target=target, tool_path=tool_path, backup_path=backup_path)

    async def _load_breaker_fact(self, ctx: ToolContext, key: str) -> dict[str, Any]:
        return await _load_breaker_fact_impl(self, ctx, key)

    async def _is_global_breaker_cooling_down(self, ctx: ToolContext) -> tuple[bool, int]:
        return await _is_global_breaker_cooling_down_impl(self, ctx)

    async def _is_target_breaker_cooling_down(self, ctx: ToolContext, target: str) -> tuple[bool, int, int]:
        return await _is_target_breaker_cooling_down_impl(self, ctx, target)

    async def _update_target_breaker_state(
        self,
        ctx: ToolContext,
        *,
        target: str,
        success: bool,
        reason: str = "",
    ) -> None:
        await _update_target_breaker_state_impl(self, ctx, target=target, success=success, reason=reason)

    def _find_tool_path(self, tool_name: str) -> Path | None:
        return _find_tool_path_impl(self, tool_name)

    async def _choose_tool_target_with_llm(
        self,
        recent: list[Failure],
        candidates: list[tuple[str, int]],
        blocked: list[tuple[str, int, int]],
    ) -> tuple[str | None, str]:
        return await _choose_tool_target_with_llm_impl(self, recent, candidates, blocked)

    async def _process_pending_verifications(self, ctx: ToolContext) -> list[EvolutionResult]:
        return await _process_pending_verifications_impl(self, ctx)

    async def evolve_model(self, new_model: str, reason: str, ctx: ToolContext) -> EvolutionResult:
        return await _evolve_model_impl(self, new_model, reason, ctx)

    async def evolve_ethos(self, ctx: ToolContext) -> EvolutionResult:
        return await _evolve_ethos_impl(self, ctx)

    async def evolve_prompt(self, prompt_key: str, feedback: str) -> EvolutionResult:
        return await _evolve_prompt_impl(self, prompt_key, feedback)

    async def evolve_skill(self, skill_name: str, feedback: str, ctx: ToolContext | None = None) -> EvolutionResult:
        return await _evolve_skill_impl(self, skill_name, feedback, ctx=ctx)

    async def synthesize_skill(
        self, skill_name: str, description: str, *, ctx: ToolContext | None = None
    ) -> EvolutionResult:
        return await _synthesize_skill_impl(self, skill_name, description, ctx=ctx)

    async def evolve_tool(self, tool_name: str, tool_path: Path, feedback: str, ctx: ToolContext | None = None) -> EvolutionResult:
        return await _evolve_tool_impl(self, tool_name, tool_path, feedback, ctx=ctx)

    async def synthesize_tool(self, description: str, name_hint: str = "") -> EvolutionResult:
        return await _synthesize_tool_impl(self, description, name_hint)

    async def competitive_evolve_tool(
        self,
        tool_name: str,
        tool_path: Path,
        feedback: str,
        num_candidates: int = 2,
        ctx: ToolContext | None = None,
    ) -> EvolutionResult:
        return await _competitive_evolve_tool_impl(self, tool_name, tool_path, feedback, num_candidates=num_candidates, ctx=ctx)

    async def _promote_candidate(
        self,
        tool_name: str,
        tool_path: Path,
        code: str,
        candidate_idx: int,
        score: int,
        ctx: ToolContext | None = None,
    ) -> EvolutionResult:
        return await _promote_candidate_impl(self, tool_name, tool_path, code, candidate_idx, score, ctx=ctx)

    async def run(self, ctx: ToolContext) -> list[EvolutionResult]:
        """主入口：分析近期失败，决定是否进化某个工具。"""

        if not self._cfg.evolution.enabled:
            return []

        results = await self._process_pending_verifications(ctx)

        global_open, global_remain = await self._is_global_breaker_cooling_down(ctx)
        if global_open:
            _log.warning("[evolution] 全局熔断中，跳过本轮进化（剩余 %ds）", global_remain)
            results.append(EvolutionResult(
                success=False,
                target="evolution:global-breaker",
                reason=f"global breaker open, remaining={global_remain}s",
            ))
            return results

        failures = await ctx.task_store.list_failures(limit=20)
        if not failures:
            return results

        from collections import Counter
        from datetime import datetime, timedelta

        _window = timedelta(minutes=self._cfg.evolution.trigger_window_minutes)
        _now = datetime.now(UTC)
        _cutoff = _now - _window

        def _in_window(f: Failure) -> bool:
            try:
                ts = datetime.fromisoformat(f.created_at.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                return ts >= _cutoff
            except Exception:
                return True

        recent = [f for f in failures if _in_window(f)]
        if not recent:
            _log.debug("[evolution] run: 时间窗内无失败，跳过")
            return results

        trigger_min = self._cfg.evolution.trigger_min_failures
        _log.info("[evolution] run: 时间窗内 %d 条失败，trigger_min=%d", len(recent), trigger_min)

        counts = Counter(f.kind for f in recent if f.kind)

        parse_failures = counts.get("judgment_parse", 0)
        if parse_failures >= trigger_min:
            feedback = "\n".join(
                f"- {f.summary}" for f in recent if f.kind == "judgment_parse"
            )
            r = await self.evolve_prompt("judgment", feedback)
            if not r.success:
                _log.warning("[evolution] 提示词进化失败: %s", r.reason)
            results.append(r)
            if r.success:
                return results

        tool_counts = Counter(
            f.kind for f in recent
            if f.kind and f.kind != "judgment_parse"
        )
        if not tool_counts:
            return results

        ranked = [
            (name, count)
            for name, count in tool_counts.most_common()
            if count >= trigger_min
        ]
        if not ranked:
            return results

        candidates: list[tuple[str, int, Path]] = []
        blocked: list[tuple[str, int, int]] = []
        for name, count in ranked:
            if self._registry.get(name) is None:
                continue
            tool_path = self._find_tool_path(name)
            if tool_path is None:
                continue
            target_open, target_remain, target_streak = await self._is_target_breaker_cooling_down(ctx, name)
            if target_open:
                blocked.append((name, target_remain, target_streak))
                continue
            candidates.append((name, count, tool_path))

        if not candidates:
            if blocked:
                reason = "; ".join(f"{name}(remain={remain}s,streak={streak})" for name, remain, streak in blocked)
                results.append(EvolutionResult(success=False, target="evolution:breaker", reason=f"all candidates blocked: {reason}"))
            return results

        decision_target, decision_reason = await self._choose_tool_target_with_llm(
            recent,
            [(name, count) for name, count, _path in candidates],
            blocked,
        )
        if not decision_target:
            results.append(EvolutionResult(success=False, target="evolution:llm-skip", reason=decision_reason))
            return results

        chosen = next((item for item in candidates if item[0] == decision_target), candidates[0])
        target_tool, _target_count, tool_path = chosen
        _log.info("[evolution] LLM 决策本轮进化目标=%r reason=%s", target_tool, decision_reason)

        feedback = "\n".join(f"- {f.summary}" for f in recent if f.kind == target_tool)
        num_candidates = self._cfg.evolution.competitive_candidates
        if num_candidates >= 2:
            result = await self.competitive_evolve_tool(
                target_tool, tool_path, feedback, num_candidates=num_candidates, ctx=ctx
            )
        else:
            result = await self.evolve_tool(target_tool, tool_path, feedback, ctx=ctx)
        results.append(result)
        await self._update_target_breaker_state(
            ctx,
            target=target_tool,
            success=result.success,
            reason=result.reason,
        )

        ethos_result = await self.evolve_ethos(ctx)
        if ethos_result.success:
            results.append(ethos_result)

        return results

    async def _update_dreams(self, trigger_desc: str, ctx: ToolContext | None = None) -> None:
        from datetime import datetime

        from provider.base import Message

        dreams_path = self._cfg.workspace_dir / "DREAMS.md"
        if not dreams_path.exists():
            return

        current = dreams_path.read_text(encoding="utf-8")
        messages = [
            Message(role="system", content=(
                "你是灵舟，一个正在成长的数字生命。"
                "请根据刚发生的进化事件，用第一人称写一条新的长期志向（15~40字）。"
                "只输出这一条志向，不要解释，不要标题，不要引号，不要多余文字。"
            )),
            Message(role="user", content=(
                f"刚刚发生的进化：{trigger_desc}\n\n"
                f"已有志向（避免重复）：\n{current[-800:]}\n\n"
                "请写一条新的、真实的志向（第一人称，15~40字）："
            )),
        ]
        try:
            aspiration = (await self._provider.chat(messages)).strip()
            if not aspiration or len(aspiration) > 120:
                return
            ts = datetime.now(UTC).strftime("%Y-%m-%d")
            entry = f"\n- [{ts}] {aspiration}"
            with dreams_path.open("a", encoding="utf-8") as f:
                f.write(entry)
            if ctx is not None:
                try:
                    fact_ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
                    fact_key = f"evolution:history:{fact_ts}"
                    fact_val = json.dumps({
                        "desc": trigger_desc,
                        "aspiration": aspiration,
                        "at": datetime.now(UTC).isoformat(),
                    }, ensure_ascii=False)
                    await submit_fact(
                        ctx,
                        key=fact_key,
                        value=fact_val,
                        scope="system",
                        source="evolution/history",
                    )
                except Exception as exc:
                    _log.debug("[evolution] 历史 fact 写入跳过: %s", exc)
        except Exception as exc:
            _log.debug("[evolution] DREAMS.md 更新跳过: %s", exc)

    async def _write_evolution_history_fact(
        self,
        tool_name: str,
        *,
        success: bool,
        reason: str,
        ctx: ToolContext | None,
    ) -> None:
        if ctx is None:
            return
        try:
            ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
            key = f"evolution:history:{ts}"
            val = json.dumps({
                "tool": tool_name,
                "success": success,
                "reason": reason if reason else "",
                "at": datetime.now(UTC).isoformat(),
            }, ensure_ascii=False)
            await submit_fact(
                ctx,
                key=key,
                value=val,
                scope="system",
                source="evolution/history",
            )
        except Exception as exc:
            _log.debug("[evolution] 生命史账本写入跳过: %s", exc)


__all__ = [
    "EvolutionEngine",
    "EvolutionProposal",
    "EvolutionResult",
    "_breaker_fact_key",
    "_clean_old_backups",
    "_clear_smoke_failure_artifacts",
    "_extract_python",
    "_format_smoke_failure_message",
    "_global_breaker_fact_key",
    "_parse_ts",
    "_persist_smoke_failure_artifacts",
    "_score_candidate",
    "_smoke_failure_artifact_paths",
    "_smoke_failure_summary",
    "_summarize_smoke_failure_preview",
    "_verification_fact_key",
    "_verification_outcome",
]
