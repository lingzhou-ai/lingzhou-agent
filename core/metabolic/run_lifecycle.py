"""Run 生命周期提交器：让 run 生命周期变更也走代谢入口。"""
from __future__ import annotations

from typing import Any

from core.metabolic.fact_lifecycle import resolve_metabolic
from core.metabolic.proposal import StateProposal


async def add_run(
    owner: Any,
    *,
    task_id: int = 0,
    run_type: str = "tool_chain",
    worker_type: str = "tool-chain-worker",
    status: str = "running",
    input_json: dict[str, Any] | None = None,
    output_json: dict[str, Any] | None = None,
    log_text: str = "",
    error_text: str = "",
    tool_name: str = "",
    session_id: str = "",
    model_tier: str = "",
    progress: str = "",
    extras: dict[str, Any] | None = None,
    source: str,
    run_id: int = 0,
    decision_basis: str = "",
) -> int:
    """经代谢器官创建 Run，并返回 run id；失败直接抛异常。"""
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic run creation requires a task store")
    run_id_value = await metabolic.submit(
        StateProposal(
            op="add_run",
            key="run:new",
            value={
                "task_id": task_id,
                "run_type": run_type,
                "worker_type": worker_type,
                "status": status,
                "input_json": input_json or {},
                "output_json": output_json or {},
                "log_text": log_text,
                "error_text": error_text,
                "tool_name": tool_name,
                "session_id": session_id,
                "model_tier": model_tier,
                "progress": progress,
                "extras": extras or {},
            },
            scope="run",
            source=source,
            run_id=run_id,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )
    try:
        return int(run_id_value or 0)
    except Exception:
        return 0


async def update_run(
    owner: Any,
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
    source: str,
    proposal_run_id: int = 0,
    decision_basis: str = "",
) -> None:
    """经代谢器官更新 Run；调用方不直接执行任务存储更新。"""
    metabolic = resolve_metabolic(owner)
    if metabolic is None:
        raise RuntimeError("metabolic run update requires a task store")
    await metabolic.submit(
        StateProposal(
            op="update_run",
            key=str(run_id),
            value={
                "task_id": task_id,
                "status": status,
                "output_json": output_json,
                "log_text": log_text,
                "error_text": error_text,
                "session_id": session_id,
                "model_tier": model_tier,
                "progress": progress,
                "extras": extras,
            },
            scope="run",
            source=source,
            run_id=proposal_run_id,
            extras={"decision_basis": decision_basis} if decision_basis else {},
        )
    )
