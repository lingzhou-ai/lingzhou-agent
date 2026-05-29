"""代谢引擎、免疫策略、情感状态、ethos 推导的窄测。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

# ══════════════════════════════════════════════════════════════════════════════
# MetabolicEngine
# ══════════════════════════════════════════════════════════════════════════════


def test_metabolic_submit_set_fact_writes_to_store_and_ledger():
    asyncio.run(_metabolic_submit_set_fact_writes_to_store_and_ledger())


async def _metabolic_submit_set_fact_writes_to_store_and_ledger():
    from core.metabolic import MetabolicEngine
    from core.metabolic.proposal import StateProposal
    from store.task import TaskStore

    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "runtime.db")
        await store.open()
        try:
            engine = MetabolicEngine(store)
            proposal = StateProposal(
                op="set_fact",
                key="test:key",
                value="hello",
                scope="system",
                source="test",
            )
            await engine.submit(proposal)

            val, found = await store.get_fact("test:key")
            assert found, "fact 应已写入"
            assert val == "hello"

            rows = await store.ledger_recent(limit=5)
            assert rows, "账本应有记录"
            last = rows[0]
            assert last["key"] == "test:key"
            assert last["accepted"] is True
        finally:
            await store.close()


def test_metabolic_submit_blocked_key_skips_write_but_records_ledger():
    asyncio.run(_metabolic_submit_blocked_key_skips_write_but_records_ledger())


async def _metabolic_submit_blocked_key_skips_write_but_records_ledger():
    """evolution.evolve 被免疫器官拒绝：不写 fact，但账本仍记 accepted=False。"""
    from core.metabolic import MetabolicEngine
    from core.metabolic.proposal import StateProposal
    from store.task import TaskStore

    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "runtime.db")
        await store.open()
        try:
            engine = MetabolicEngine(store)
            # op 不是 set_fact 且在黑名单中时触发拒绝路径
            proposal = StateProposal(
                op="evolution.evolve",
                key="evolve",
                value="{}",
                scope="system",
                source="test",
            )
            await engine.submit(proposal)

            # 写入不应发生（key "evolve" 没有通过 set_fact 写入）
            val, found = await store.get_fact("evolve")
            assert not found, "被阻断的提案不应写入 fact"

            rows = await store.ledger_recent(limit=5)
            assert rows, "账本应有记录（即使被拒绝）"
            last = rows[0]
            assert last["accepted"] is False, "账本应记录 accepted=False"
        finally:
            await store.close()


def test_metabolic_submit_unknown_op_does_not_crash():
    asyncio.run(_metabolic_submit_unknown_op_does_not_crash())


async def _metabolic_submit_unknown_op_does_not_crash():
    from core.metabolic import MetabolicEngine
    from core.metabolic.proposal import StateProposal
    from store.task import TaskStore

    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "runtime.db")
        await store.open()
        try:
            engine = MetabolicEngine(store)
            # 未知 op，免疫放行但落地跳过（仍记账本）
            proposal = StateProposal(
                op="create_task",
                key="task-1",
                value={"title": "test"},
                scope="system",
                source="test",
            )
            # 不崩溃即通过
            await engine.submit(proposal)
        finally:
            await store.close()


# ══════════════════════════════════════════════════════════════════════════════
# ImmunePolicy
# ══════════════════════════════════════════════════════════════════════════════


def test_immune_check_tool_blocked_allows_normal_tool():
    from core.immune.policy import check_tool_blocked

    assert check_tool_blocked("task.add") is None
    assert check_tool_blocked("memory.set_fact") is None
    assert check_tool_blocked("shell.run") is None
    assert check_tool_blocked("config.set") is None


def test_immune_check_tool_blocked_rejects_blacklisted_tools():
    from core.immune.policy import check_tool_blocked

    for tool in ("evolution.evolve", "evolution.synthesize", "soul.update",
                 "ethos.evolve", "skill.evolve", "subagent.run"):
        result = check_tool_blocked(tool)
        assert result is not None, f"{tool!r} 应被免疫阻断"
        assert "A4" in result or "黑名单" in result


def test_immune_check_tool_blocked_rejects_empty_name():
    from core.immune.policy import check_tool_blocked

    assert check_tool_blocked("") is not None


def test_immune_is_readonly_blocked_tool_blocks_mutation_tools():
    from core.immune.policy import is_readonly_blocked_tool

    # 只读子灵不能调用这些
    assert is_readonly_blocked_tool("config.set", None) is True
    assert is_readonly_blocked_tool("memory.add_semantic", None) is True
    assert is_readonly_blocked_tool("memory.set_fact", None) is True
    assert is_readonly_blocked_tool("schedule.add", None) is True
    assert is_readonly_blocked_tool("task.plan", None) is True


def test_immune_is_readonly_blocked_tool_allows_read_tools():
    from core.immune.policy import is_readonly_blocked_tool

    # 只读子灵可以使用这些
    assert is_readonly_blocked_tool("task.ask", None) is False
    assert is_readonly_blocked_tool("task.list", None) is False
    assert is_readonly_blocked_tool("memory.add_wm", None) is False
    assert is_readonly_blocked_tool("memory.drop_wm", None) is False


def test_immune_audit_evolution_target_blocks_protected_modules():
    from core.immune.policy import audit_evolution_target

    assert audit_evolution_target("core.immune.policy") is not None
    assert audit_evolution_target("core.immune.constitution") is not None
    assert audit_evolution_target("core.metabolic.engine") is not None


def test_immune_audit_evolution_target_allows_normal_modules():
    from core.immune.policy import audit_evolution_target

    assert audit_evolution_target("tools.shell") is None
    assert audit_evolution_target("core.execution") is None


# ══════════════════════════════════════════════════════════════════════════════
# EmotionState.derive_from_signals
# ══════════════════════════════════════════════════════════════════════════════


def test_emotion_high_failure_lowers_valence():
    from core.perception.emotion import EmotionState

    em = EmotionState(valence=0.65, arousal=0.50)
    em.derive_from_signals(
        failure_count=5,
        prediction_error=0.8,
        wm_pressure=0.7,
        workspace_dirty=False,
        alpha=1.0,  # 直接覆盖，无 EMA 平滑
    )
    assert em.valence < 0.65, "高失败率应降低效价"
    assert em.arousal > 0.0, "唤醒度应仍有值"


def test_emotion_low_failure_raises_valence_with_next_step():
    from core.perception.emotion import EmotionState

    em = EmotionState(valence=0.40, arousal=0.50)
    em.derive_from_signals(
        failure_count=0,
        prediction_error=0.1,
        wm_pressure=0.1,
        workspace_dirty=False,
        alpha=1.0,
        has_next_step=True,
        has_active_task=True,
        replay_trend="recovering",
    )
    assert em.valence > 0.40, "有下一步且 recovering 应提升效价"
    dominant_names = {f.name for f in em.feelings}
    assert dominant_names & {"hope", "confidence", "joy", "relief"}, \
        f"应出现正面情感，实际: {dominant_names}"


def test_emotion_recovering_trend_produces_positive_feelings():
    from core.perception.emotion import EmotionState

    em = EmotionState(valence=0.50, arousal=0.50)
    em.derive_from_signals(
        failure_count=1,
        prediction_error=0.2,
        wm_pressure=0.2,
        workspace_dirty=False,
        alpha=1.0,
        replay_trend="recovering",
    )
    names = {f.name for f in em.feelings}
    assert names & {"hope", "relief"}, f"recovering 应产生希望/宽慰，实际: {names}"


def test_emotion_derive_updates_dominant_name():
    from core.perception.emotion import EmotionState

    em = EmotionState()
    em.derive_from_signals(
        failure_count=3,
        prediction_error=0.7,
        wm_pressure=0.6,
        workspace_dirty=False,
        alpha=1.0,
    )
    assert em.dominant != "", "dominant 不应为空"


# ══════════════════════════════════════════════════════════════════════════════
# derive_ethos_state
# ══════════════════════════════════════════════════════════════════════════════


def _default_ethos_cfg() -> Any:
    from core.config import EthosConfig
    return EthosConfig()


def test_ethos_high_failure_triggers_prefer_verification():
    from core.perception.ethos import derive_ethos_state

    ec = _default_ethos_cfg()
    state = derive_ethos_state(
        failure_count=ec.prefer_verification_failure_count,
        high_error_streak=0,
        has_active_task=False,
        has_next_step=False,
        perception_trend="stable",
        emotion_down_regulate_streak=0,
        ethos_cfg=ec,
        baseline=None,
    )
    assert state.bias.prefer_verification is True, \
        "达到 prefer_verification_failure_count 时应启用验证偏置"


def test_ethos_multiple_failures_triggers_prefer_narrow():
    from core.perception.ethos import derive_ethos_state

    ec = _default_ethos_cfg()
    state = derive_ethos_state(
        failure_count=ec.prefer_narrow_failure_count,
        high_error_streak=0,
        has_active_task=False,
        has_next_step=False,
        perception_trend="stable",
        emotion_down_regulate_streak=0,
        ethos_cfg=ec,
        baseline=None,
    )
    assert state.bias.prefer_narrow_scope is True, \
        "达到 prefer_narrow_failure_count 时应收窄范围"


def test_ethos_high_error_streak_triggers_narrow():
    from core.perception.ethos import derive_ethos_state

    ec = _default_ethos_cfg()
    state = derive_ethos_state(
        failure_count=0,
        high_error_streak=ec.prefer_narrow_error_streak,
        has_active_task=False,
        has_next_step=False,
        perception_trend="stable",
        emotion_down_regulate_streak=0,
        ethos_cfg=ec,
        baseline=None,
    )
    assert state.bias.prefer_narrow_scope is True, \
        "高错误 streak 应触发 prefer_narrow_scope"


def test_ethos_no_failure_keeps_baseline_values():
    from core.perception.ethos import EthosValues, derive_ethos_state

    ec = _default_ethos_cfg()
    # 提供高 baseline truth 值
    baseline = EthosValues(truth=0.90, caution=0.50, continuity=0.60,
                           curiosity=0.55, care=0.60)
    state = derive_ethos_state(
        failure_count=0,
        high_error_streak=0,
        has_active_task=False,
        has_next_step=False,
        perception_trend="stable",
        emotion_down_regulate_streak=0,
        ethos_cfg=ec,
        baseline=baseline,
    )
    # EMA 混合后 truth 应接近 baseline
    assert state.values.truth >= ec.floor_truth, "truth 不应低于 floor_truth"
    # 无失败时 prefer_verification 取决于 caution 和 failure_count
    # caution=0.50 vs floor=0.05，prefer_verification_caution_min 默认 0.75
    # → 无需验证偏置（除非 failure_count 也达阈值）
    assert state.bias.prefer_verification is False, \
        "无失败且 caution 未超阈值时不应开启验证偏置"


def test_ethos_recovering_trend_boosts_curiosity():
    from core.perception.ethos import derive_ethos_state

    ec = _default_ethos_cfg()
    state_stable = derive_ethos_state(
        failure_count=0,
        high_error_streak=0,
        has_active_task=False,
        has_next_step=False,
        perception_trend="stable",
        emotion_down_regulate_streak=0,
        ethos_cfg=ec,
    )
    state_recovering = derive_ethos_state(
        failure_count=0,
        high_error_streak=0,
        has_active_task=False,
        has_next_step=False,
        perception_trend="recovering",
        emotion_down_regulate_streak=0,
        ethos_cfg=ec,
    )
    assert state_recovering.values.curiosity >= state_stable.values.curiosity, \
        "recovering 趋势应提升好奇心"


def test_ethos_floor_values_always_enforced():
    from core.perception.ethos import EthosValues, derive_ethos_state

    ec = _default_ethos_cfg()
    # 极低 baseline，验证 floor 兜底
    baseline = EthosValues(truth=0.0, caution=0.0, continuity=0.3,
                           curiosity=0.3, care=0.3)
    state = derive_ethos_state(
        failure_count=0,
        high_error_streak=0,
        has_active_task=False,
        has_next_step=False,
        perception_trend="stable",
        emotion_down_regulate_streak=0,
        ethos_cfg=ec,
        baseline=baseline,
    )
    assert state.values.truth >= ec.floor_truth, "truth 不应低于 floor"
    assert state.values.caution >= ec.floor_caution, "caution 不应低于 floor"


# ══════════════════════════════════════════════════════════════════════════════
# Task 3 — run_id 写入生命史账本
# ══════════════════════════════════════════════════════════════════════════════


def test_state_proposal_has_run_id_field():
    """StateProposal 应有 run_id 字段，默认为 0。"""
    from core.metabolic.proposal import StateProposal

    p = StateProposal(op="set_fact", key="x", value="v")
    assert hasattr(p, "run_id"), "StateProposal 应有 run_id 字段"
    assert p.run_id == 0, "默认 run_id 应为 0"
    p2 = StateProposal(op="set_fact", key="x", value="v", run_id=42)
    assert p2.run_id == 42


def test_ledger_append_stores_run_id():
    """LedgerStore.append 写入 run_id，recent() 可读回。"""
    asyncio.run(_ledger_append_stores_run_id())


async def _ledger_append_stores_run_id():
    import tempfile
    from pathlib import Path

    from store.task import TaskStore

    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "runtime.db")
        await store.open()
        try:
            await store.ledger_append(
                "set_fact", "run_id_test_key", "run_id_test_val",
                scope="task", source="pytest", accepted=True, run_id=99,
            )
            rows = await store.ledger_recent(limit=5)
            assert rows, "账本应有记录"
            last = rows[0]
            assert last.get("run_id") == 99, f"run_id 应为 99，实际 {last.get('run_id')!r}"
        finally:
            await store.close()


def test_metabolic_engine_propagates_run_id_to_ledger():
    """MetabolicEngine.submit 应把 proposal.run_id 写入账本。"""
    asyncio.run(_metabolic_engine_propagates_run_id_to_ledger())


async def _metabolic_engine_propagates_run_id_to_ledger():
    import tempfile
    from pathlib import Path

    from core.metabolic import MetabolicEngine
    from core.metabolic.proposal import StateProposal
    from store.task import TaskStore

    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "runtime.db")
        await store.open()
        try:
            engine = MetabolicEngine(store)
            proposal = StateProposal(
                op="set_fact",
                key="engine_run_id_key",
                value="engine_run_id_val",
                scope="task",
                source="pytest",
                run_id=77,
            )
            await engine.submit(proposal)
            rows = await store.ledger_recent(limit=5)
            assert rows, "账本应有记录"
            last = rows[0]
            assert last.get("run_id") == 77, f"run_id 应为 77，实际 {last.get('run_id')!r}"
        finally:
            await store.close()


def test_life_ledger_migration_adds_run_id_column():
    """旧 DB（无 run_id 列）在 open() 后应自动迁移增加该列。"""
    asyncio.run(_life_ledger_migration_adds_run_id_column())


async def _life_ledger_migration_adds_run_id_column():
    import tempfile
    from pathlib import Path

    import aiosqlite

    from store.task import TaskStore

    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "old.db"
        # 手工建一张没有 run_id 列的 life_ledger 表，模拟旧 DB
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS life_ledger (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts       TEXT NOT NULL DEFAULT (datetime('now')),
                    op       TEXT NOT NULL,
                    key      TEXT NOT NULL,
                    value    TEXT NOT NULL DEFAULT '',
                    scope    TEXT NOT NULL DEFAULT 'task',
                    source   TEXT NOT NULL DEFAULT '',
                    accepted INTEGER NOT NULL DEFAULT 1
                )
            """)
            await db.commit()

        # 正常 open() 应触发 _migrate_ledger_run_id
        store = TaskStore(db_path)
        await store.open()
        try:
            # 写入并读回，验证列存在且可存储
            await store.ledger_append(
                "set_fact", "migration_key", "migration_val",
                run_id=55,
            )
            rows = await store.ledger_recent(limit=5)
            assert rows and rows[0].get("run_id") == 55, \
                f"迁移后 run_id 应可读，实际 {rows[0] if rows else '[]'!r}"
        finally:
            await store.close()
