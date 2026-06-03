from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.metabolic import delete_fact, submit_fact

from .types import _breaker_fact_key, _global_breaker_fact_key

if TYPE_CHECKING:
    from core.evolution import EvolutionEngine
    from tools.registry import ToolContext

_log = logging.getLogger("lingzhou.evolution")


async def _submit_breaker_fact(ctx: ToolContext, *, key: str, value: str) -> None:
    await submit_fact(
        ctx,
        key=key,
        value=value,
        scope="system",
        source="evolution/breaker",
    )


async def _delete_breaker_fact(ctx: ToolContext, *, key: str) -> None:
    await delete_fact(ctx, key=key, source="evolution/breaker")


async def _load_breaker_fact(engine: EvolutionEngine, ctx: ToolContext, target: str) -> dict[str, Any]:
    facts = await ctx.task_store.list_facts(prefix=target, limit=1)
    for fact_key, raw in facts:
        if fact_key != target:
            continue
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            return {}
    return {}


async def _is_global_breaker_cooling_down(engine: EvolutionEngine, ctx: ToolContext) -> tuple[bool, int]:
    key = _global_breaker_fact_key()
    state = await _load_breaker_fact(engine, ctx, key)
    now = datetime.now(UTC).timestamp()
    cooldown_until = float(state.get("cooldown_until", 0.0) or 0.0)
    if cooldown_until <= now:
        with contextlib.suppress(Exception):
            await _delete_breaker_fact(ctx, key=key)
        return False, 0
    return True, int(cooldown_until - now)


async def _is_target_breaker_cooling_down(engine: EvolutionEngine, ctx: ToolContext, target: str) -> tuple[bool, int, int]:
    key = _breaker_fact_key(target)
    state = await _load_breaker_fact(engine, ctx, key)
    now = datetime.now(UTC).timestamp()
    cooldown_until = float(state.get("cooldown_until", 0.0) or 0.0)
    streak = int(state.get("failure_streak", 0) or 0)
    if cooldown_until <= now:
        with contextlib.suppress(Exception):
            await _delete_breaker_fact(ctx, key=key)
        return False, 0, streak
    return True, int(cooldown_until - now), streak


async def _update_target_breaker_state(
    engine: EvolutionEngine,
    ctx: ToolContext,
    *,
    target: str,
    success: bool,
    reason: str = "",
) -> None:
    key = _breaker_fact_key(target)
    if success:
        with contextlib.suppress(Exception):
            await _delete_breaker_fact(ctx, key=key)
        return

    state = await _load_breaker_fact(engine, ctx, key)
    prev_streak = int(state.get("failure_streak", 0) or 0)
    new_streak = prev_streak + 1
    now = datetime.now(UTC).timestamp()
    cooldown_until = 0.0
    if new_streak >= engine._breaker_fail_threshold:
        cooldown_until = now + float(engine._breaker_cooldown_seconds)
    payload = json.dumps(
        {
            "target": target,
            "failure_streak": new_streak,
            "cooldown_until": cooldown_until,
            "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "reason": reason if reason else "",
        },
        ensure_ascii=False,
    )
    await _submit_breaker_fact(ctx, key=key, value=payload)

    if new_streak >= engine._breaker_escalate_threshold:
        global_key = _global_breaker_fact_key()
        global_until = now + float(engine._breaker_global_cooldown_seconds)
        global_payload = json.dumps(
            {
                "failure_target": target,
                "failure_streak": new_streak,
                "cooldown_until": global_until,
                "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "reason": reason if reason else "",
            },
            ensure_ascii=False,
        )
        await _submit_breaker_fact(ctx, key=global_key, value=global_payload)
        _log.warning(
            "[evolution] 全局熔断开启 target=%r streak=%d cooldown=%ds",
            target,
            new_streak,
            engine._breaker_global_cooldown_seconds,
        )


__all__ = [
    "_is_global_breaker_cooling_down",
    "_is_target_breaker_cooling_down",
    "_load_breaker_fact",
    "_update_target_breaker_state",
]
