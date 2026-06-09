from __future__ import annotations

from core.cortex import build_cortex_workspace, format_cortex_workspace
from store.task import Failure, Run, Task


def test_cortex_workspace_derives_task_context_from_existing_artifacts():
    task = Task(
        id=42,
        title="完善大脑皮层",
        status="in_progress",
        priority="normal",
        created_at="2026-06-09T00:00:00+00:00",
        goal="让长任务不只依赖短期工作记忆",
        current_step="接入 judgment context",
        next_step="补测试并验证",
        extras={
            "plan": [
                {"step": "审查 WM 和 judgment 链路", "status": "completed"},
                {"step": "加入任务级 cortex workspace", "status": "in_progress"},
            ]
        },
    )
    recent_runs = [
        Run(
            id=7,
            task_id=42,
            run_type="tool",
            worker_type="reasoner",
            status="completed",
            created_at="2026-06-09T00:01:00+00:00",
            tool_name="exec",
            progress="已找到 context 注入点",
        )
    ]
    failures = [
        Failure(
            id=3,
            kind="context_too_cramped",
            dismissed=False,
            created_at="2026-06-09T00:02:00+00:00",
            summary="近期上下文无法稳定承载任务状态",
            task_id="42",
        )
    ]

    workspace = build_cortex_workspace(
        task=task,
        recent_runs=recent_runs,
        context_facts=[("task:42:proxy", "授权代理已接入配置")],
        failures=failures,
    )
    text = format_cortex_workspace(workspace)

    assert "task_id=42 status=in_progress" in text
    assert "goal=让长任务不只依赖短期工作记忆" in text
    assert "1. [completed] 审查 WM 和 judgment 链路" in text
    assert "task:42:proxy: 授权代理已接入配置" in text
    assert "run#7 [completed] exec: 已找到 context 注入点" in text
    assert "context_too_cramped: 近期上下文无法稳定承载任务状态" in text


def test_cortex_workspace_prefers_explicit_cortex_result_state():
    task = Task(
        id=9,
        title="任务",
        status="running",
        priority="normal",
        created_at="2026-06-09T00:00:00+00:00",
        result_json={
            "cortex": {
                "plan": [{"step": "显式计划", "status": "active"}],
                "evidence": ["显式证据"],
                "progress": ["显式进展"],
                "failures": ["显式失败"],
                "open_questions": ["显式问题"],
            }
        },
        extras={"plan": [{"step": "派生计划", "status": "pending"}]},
    )

    text = format_cortex_workspace(build_cortex_workspace(task=task))

    assert "[active] 显式计划" in text
    assert "显式证据" in text
    assert "显式进展" in text
    assert "显式失败" in text
    assert "显式问题" in text
    assert "派生计划" not in text
