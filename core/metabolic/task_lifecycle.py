"""任务生命周期提交器：让任务创建、等待、恢复、修正都经过代谢器官。"""
from __future__ import annotations

from typing import Any

from core.metabolic.fact_lifecycle import resolve_metabolic
from core.metabolic.proposal import StateProposal


async def create_task(
    owner: Any,
    *,
    proposal_source: str,
    decision_basis: str = "",
    **data: Any,
) -> int:
    """经代谢器官创建任务，并返回新任务 id。"""
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic task creation requires a task store")
    task_id = await metabolic.submit(
        StateProposal(
            op="create_task",
            key="task:new",
            value=data,
            scope="task",
            source=proposal_source,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )
    return int(task_id)


async def update_task_status(
    owner: Any,
    task_id: int,
    *,
    status: str,
    source: str,
    next_step: str | None = None,
    current_step: str | None = None,
    model_tier: str | None = None,
    result_json: dict[str, Any] | None = None,
    decision_basis: str = "",
) -> None:
    """经代谢器官更新任务状态和步骤。"""
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic task update requires a task store")
    await metabolic.submit(
        StateProposal(
            op="update_task_status",
            key=str(task_id),
            value={
                "status": status,
                "next_step": next_step,
                "current_step": current_step,
                "model_tier": model_tier,
                "result_json": result_json,
            },
            scope="task",
            source=source,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )


async def mark_task_waiting(
    owner: Any,
    task_id: int,
    *,
    wait_kind: str,
    source: str,
    wait_key: str = "",
    wait_json: dict[str, Any] | None = None,
    current_step: str | None = None,
    next_step: str | None = None,
    result_json: dict[str, Any] | None = None,
    decision_basis: str = "",
) -> None:
    """经代谢器官将任务切入 waiting。"""
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic task wait requires a task store")
    await metabolic.submit(
        StateProposal(
            op="mark_task_waiting",
            key=str(task_id),
            value={
                "wait_kind": wait_kind,
                "wait_key": wait_key,
                "wait_json": wait_json,
                "current_step": current_step,
                "next_step": next_step,
                "result_json": result_json,
            },
            scope="task",
            source=source,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )


async def resume_task(
    owner: Any,
    task_id: int,
    *,
    source: str,
    status: str = "resumed",
    current_step: str | None = None,
    next_step: str | None = None,
    result_json: dict[str, Any] | None = None,
    decision_basis: str = "",
) -> None:
    """经代谢器官恢复 waiting/blocked 任务。"""
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic task resume requires a task store")
    await metabolic.submit(
        StateProposal(
            op="resume_task",
            key=str(task_id),
            value={
                "status": status,
                "current_step": current_step,
                "next_step": next_step,
                "result_json": result_json,
            },
            scope="task",
            source=source,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )


async def update_task_data(
    owner: Any,
    task_id: int,
    data: dict[str, Any],
    *,
    source: str,
    decision_basis: str = "",
) -> None:
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic task data update requires a task store")
    await metabolic.submit(
        StateProposal(
            op="update_task_data",
            key=str(task_id),
            value=data,
            scope="task",
            source=source,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )


async def update_task_result(
    owner: Any,
    task_id: int,
    result_json: dict[str, Any],
    *,
    source: str,
    decision_basis: str = "",
) -> None:
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic task result update requires a task store")
    await metabolic.submit(
        StateProposal(
            op="update_task_result",
            key=str(task_id),
            value=result_json if isinstance(result_json, dict) else {"value": result_json},
            scope="task",
            source=source,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )


async def amend_task(
    owner: Any,
    task_id: int,
    *,
    source: str,
    title: str | None = None,
    goal: str | None = None,
    priority: str | None = None,
    amendment_reason: str,
    decision_basis: str = "",
) -> bool:
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic task amendment requires a task store")
    result = await metabolic.submit(
        StateProposal(
            op="amend_task",
            key=str(task_id),
            value={
                "title": title,
                "goal": goal,
                "priority": priority,
                "amendment_reason": amendment_reason,
            },
            scope="task",
            source=source,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )
    return bool(result)
