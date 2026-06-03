"""状态落地器：把已通过免疫检查的 StateProposal 写入 TaskStore。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.metabolic.proposal import StateProposal
    from tools.view_protocols import TaskStoreViewProtocol

_log = logging.getLogger("lingzhou.metabolic")


@dataclass(slots=True)
class StateWriteResult:
    result: Any = None
    ledger_key: str = ""
    accepted: bool = True
    reason: str = ""


async def apply_state_write(
    task_store: TaskStoreViewProtocol,
    proposal: StateProposal,
    *,
    accepted: bool,
    semantic_memory: Any | None = None,
) -> StateWriteResult:
    """落地一次已获准的状态写入；未知 op 返回 accepted=False。"""
    if proposal.op in {"set_fact", "delete_fact"}:
        return await _apply_fact_write(task_store, proposal, accepted=accepted)
    if proposal.op == "soul_change":
        return await _apply_soul_change(task_store, proposal, accepted=accepted)
    if proposal.op in {
        "create_task",
        "update_task_status",
        "mark_task_waiting",
        "resume_task",
        "update_task_data",
        "update_task_result",
        "amend_task",
        "add_run",
        "update_run",
    }:
        return await _apply_task_write(task_store, proposal, accepted=accepted)
    if proposal.op == "add_semantic_memory":
        return await _apply_semantic_write(
            semantic_memory,
            proposal,
            accepted=accepted,
        )

    _log.warning(
        "[metabolic] 未知 op=%r，跳过（key=%r source=%r）",
        proposal.op,
        proposal.key,
        proposal.source,
    )
    return StateWriteResult(ledger_key=proposal.key, accepted=False, reason="unknown_op")


async def _apply_fact_write(
    task_store: TaskStoreViewProtocol,
    proposal: StateProposal,
    *,
    accepted: bool,
) -> StateWriteResult:
    if proposal.op == "set_fact":
        await task_store.set_fact(
            proposal.key,
            proposal.value,
            scope=proposal.scope,
        )
        _log.debug(
            "[metabolic] set_fact key=%r scope=%r source=%r",
            proposal.key,
            proposal.scope,
            proposal.source,
        )
        return StateWriteResult(ledger_key=proposal.key, accepted=accepted)

    await task_store.delete_fact(proposal.key)
    _log.debug(
        "[metabolic] delete_fact key=%r source=%r",
        proposal.key,
        proposal.source,
    )
    return StateWriteResult(ledger_key=proposal.key, accepted=accepted)


async def _apply_soul_change(
    task_store: TaskStoreViewProtocol,
    proposal: StateProposal,
    *,
    accepted: bool,
) -> StateWriteResult:
    """人格/灵魂层 fact 落地：key 必须是 soul 前缀。"""
    if not str(proposal.key).startswith("soul:"):
        return StateWriteResult(
            ledger_key=proposal.key,
            accepted=False,
            reason="soul_change key must start with 'soul:'",
        )
    await task_store.set_fact(
        proposal.key,
        proposal.value,
        scope=proposal.scope,
    )
    return StateWriteResult(ledger_key=proposal.key, accepted=accepted)


async def _apply_task_write(
    task_store: TaskStoreViewProtocol,
    proposal: StateProposal,
    *,
    accepted: bool,
) -> StateWriteResult:
    data = proposal.value if isinstance(proposal.value, dict) else {}
    if proposal.op == "create_task":
        task_id = await task_store.add_task(**data)
        _log.debug(
            "[metabolic] create_task id=%r source=%r",
            task_id,
            proposal.source,
        )
        return StateWriteResult(result=task_id, ledger_key=f"task:{task_id}", accepted=accepted)

    if proposal.op == "update_task_status":
        await task_store.update_status(
            int(proposal.key),
            str(data.get("status") or ""),
            data.get("next_step"),
            current_step=data.get("current_step"),
            model_tier=data.get("model_tier"),
            result_json=data.get("result_json"),
        )
        _log.debug(
            "[metabolic] update_task_status task_id=%r status=%r source=%r",
            proposal.key,
            data.get("status"),
            proposal.source,
        )
        return StateWriteResult(ledger_key=proposal.key, accepted=accepted)

    if proposal.op == "mark_task_waiting":
        await task_store.mark_waiting(
            int(proposal.key),
            wait_kind=str(data.get("wait_kind") or ""),
            wait_key=str(data.get("wait_key") or ""),
            wait_json=data.get("wait_json"),
            current_step=data.get("current_step"),
            next_step=data.get("next_step"),
            result_json=data.get("result_json"),
        )
        _log.debug(
            "[metabolic] mark_task_waiting task_id=%r wait_kind=%r source=%r",
            proposal.key,
            data.get("wait_kind"),
            proposal.source,
        )
        return StateWriteResult(ledger_key=proposal.key, accepted=accepted)

    if proposal.op == "resume_task":
        await task_store.resume_task(
            int(proposal.key),
            status=str(data.get("status") or "resumed"),
            current_step=data.get("current_step"),
            next_step=data.get("next_step"),
            result_json=data.get("result_json"),
        )
        _log.debug(
            "[metabolic] resume_task task_id=%r status=%r source=%r",
            proposal.key,
            data.get("status") or "resumed",
            proposal.source,
        )
        return StateWriteResult(ledger_key=proposal.key, accepted=accepted)

    if proposal.op == "update_task_data":
        await task_store.update_task_data(int(proposal.key), data)
        _log.debug(
            "[metabolic] update_task_data task_id=%r source=%r",
            proposal.key,
            proposal.source,
        )
        return StateWriteResult(ledger_key=proposal.key, accepted=accepted)

    if proposal.op == "update_task_result":
        await task_store.update_task_result(
            int(proposal.key),
            proposal.value if isinstance(proposal.value, dict) else {"value": proposal.value},
        )
        _log.debug(
            "[metabolic] update_task_result task_id=%r source=%r",
            proposal.key,
            proposal.source,
        )
        return StateWriteResult(ledger_key=proposal.key, accepted=accepted)

    if proposal.op == "add_run":
        data = proposal.value if isinstance(proposal.value, dict) else {}
        run_id = await task_store.add_run(
            task_id=int(data.get("task_id") or 0),
            run_type=str(data.get("run_type") or "tool_chain"),
            worker_type=str(data.get("worker_type") or "tool-chain-worker"),
            status=str(data.get("status") or "running"),
            input_json=(data.get("input_json") if isinstance(data.get("input_json"), dict) else {}),
            output_json=(data.get("output_json") if isinstance(data.get("output_json"), dict) else {}),
            log_text=str(data.get("log_text") or ""),
            error_text=str(data.get("error_text") or ""),
            tool_name=str(data.get("tool_name") or ""),
            session_id=str(data.get("session_id") or ""),
            model_tier=str(data.get("model_tier") or ""),
            progress=str(data.get("progress") or ""),
            extras=(data.get("extras") if isinstance(data.get("extras"), dict) else {}),
        )
        _log.debug(
            "[metabolic] add_run key=%r run_id=%r source=%r",
            proposal.key,
            run_id,
            proposal.source,
        )
        return StateWriteResult(result=run_id, ledger_key=f"run:{run_id}", accepted=accepted)

    if proposal.op == "update_run":
        data = proposal.value if isinstance(proposal.value, dict) else {}
        await task_store.update_run(
            int(proposal.key),
            task_id=data.get("task_id") if data.get("task_id") is not None else None,
            status=(str(data.get("status")) if data.get("status") is not None else None),
            output_json=(data.get("output_json") if isinstance(data.get("output_json"), dict) else None),
            log_text=(str(data.get("log_text")) if data.get("log_text") is not None else None),
            error_text=(str(data.get("error_text")) if data.get("error_text") is not None else None),
            session_id=(str(data.get("session_id")) if data.get("session_id") is not None else None),
            model_tier=(str(data.get("model_tier")) if data.get("model_tier") is not None else None),
            progress=(str(data.get("progress")) if data.get("progress") is not None else None),
            extras=(data.get("extras") if isinstance(data.get("extras"), dict) else None),
        )
        _log.debug(
            "[metabolic] update_run run_id=%r status=%r source=%r",
            proposal.key,
            data.get("status"),
            proposal.source,
        )
        return StateWriteResult(ledger_key=f"run:{proposal.key}", accepted=accepted)

    result = await task_store.amend_task(
        int(proposal.key),
        title=data.get("title"),
        goal=data.get("goal"),
        priority=data.get("priority"),
        amendment_reason=str(data.get("amendment_reason") or ""),
    )
    _log.debug(
        "[metabolic] amend_task task_id=%r accepted=%r source=%r",
        proposal.key,
        result,
        proposal.source,
    )
    return StateWriteResult(result=result, ledger_key=proposal.key, accepted=accepted)


async def _apply_semantic_write(
    semantic_memory: Any | None,
    proposal: StateProposal,
    *,
    accepted: bool,
) -> StateWriteResult:
    if semantic_memory is None or not callable(getattr(semantic_memory, "upsert", None)):
        return StateWriteResult(
            ledger_key=proposal.key,
            accepted=False,
            reason="semantic_memory_unavailable",
        )
    data = proposal.value if isinstance(proposal.value, dict) else {}
    from store.semantic import MemoryNode

    created_at = str(data.get("created_at") or "").strip() or datetime.now(UTC).isoformat()
    node = MemoryNode(
        id=str(data.get("id") or proposal.key),
        kind=str(data.get("kind") or "observation"),
        title=str(data.get("title") or ""),
        body=str(data.get("body") or ""),
        activation=float(data.get("activation", 0.5)),
        valence=float(data.get("valence", 0.5)),
        importance=float(data.get("importance", 0.0)),
        tags=[str(tag) for tag in data.get("tags", [])] if isinstance(data.get("tags"), list) else [],
        source=str(data.get("source") or proposal.source or ""),
        created_at=created_at,
    )
    semantic_memory.upsert(node)
    _log.debug(
        "[metabolic] add_semantic_memory node_id=%r source=%r",
        node.id,
        proposal.source,
    )
    return StateWriteResult(result=node.id, ledger_key=f"semantic:{node.id}", accepted=accepted)
