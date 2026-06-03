"""事实生命周期提交器：为 fact 写入/删除提供通俗稳定的代谢入口。"""
from __future__ import annotations

from typing import Any

from core.metabolic.engine import MetabolicEngine
from core.metabolic.proposal import StateProposal


def resolve_metabolic(
    owner: Any = None,
    task_store: Any = None,
    semantic_memory: Any = None,
) -> Any | None:
    """从 ctx、loop、MetabolicEngine 或 TaskStore 中解析可用的代谢器官。"""
    if owner is not None and callable(getattr(owner, "submit", None)):
        owner_semantic = getattr(owner, "_semantic_memory", None)
        if owner_semantic is not None or semantic_memory is None:
            return owner

        owner_store = (
            task_store
            or getattr(owner, "task_store", None)
            or getattr(owner, "_task_store", None)
        )
        if owner_store is not None:
            return MetabolicEngine(owner_store, semantic_memory=semantic_memory)
        return owner
    metabolic = getattr(owner, "metabolic", None) or getattr(owner, "_metabolic", None)
    if metabolic is not None:
        return metabolic

    store = task_store or getattr(owner, "task_store", None) or getattr(owner, "_task_store", None)
    if store is None and (
        callable(getattr(owner, "ledger_append", None))
        or callable(getattr(owner, "set_fact", None))
    ):
        store = owner
    if store is None:
        return None
    semantic = semantic_memory or getattr(owner, "semantic", None) or getattr(owner, "_semantic", None)
    return MetabolicEngine(store, semantic_memory=semantic)


async def submit_fact(
    owner: Any,
    *,
    key: str,
    value: Any,
    scope: str = "system",
    source: str,
    run_id: int = 0,
    decision_basis: str = "",
    task_store: Any = None,
) -> bool:
    """经代谢器官提交 fact 写入；没有可用存储时返回 False。"""
    metabolic = resolve_metabolic(owner, task_store)
    if metabolic is None:
        return False
    await metabolic.submit(
        StateProposal(
            op="set_fact",
            key=key,
            value=value,
            scope=scope,
            source=source,
            run_id=run_id,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )
    return True


async def delete_fact(
    owner: Any,
    *,
    key: str,
    scope: str = "system",
    source: str,
    run_id: int = 0,
    decision_basis: str = "",
    task_store: Any = None,
) -> bool:
    """经代谢器官提交 fact 删除；没有可用存储时返回 False。"""
    metabolic = resolve_metabolic(owner, task_store)
    if metabolic is None:
        return False
    await metabolic.submit(
        StateProposal(
            op="delete_fact",
            key=key,
            value="",
            scope=scope,
            source=source,
            run_id=run_id,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )
    return True
