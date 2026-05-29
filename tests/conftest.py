"""共享 fixtures 与 helpers，供 tests/ 下所有测试使用。"""
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

# ── helpers ──────────────────────────────────────────────────────────────────

def _proj_root() -> Path:
    return Path(__file__).parent.parent


def _test_config(
    *,
    act: bool = True,
    debug: bool = False,
    workspace_dir: str = "",
    shell_timeout: int = 5,
    shell_max_output_chars: int = 200,
) -> Any:
    return cast(
        "Any",
        SimpleNamespace(
            loop=SimpleNamespace(
                act=act,
                debug=debug,
                workspace_dir=workspace_dir,
                max_tool_chain_workers=8,
                max_exec_workers=4,
                max_multimodal_workers=2,
                max_llm_workers=4,
            ),
            thresholds=SimpleNamespace(
                shell_timeout=shell_timeout,
                shell_max_output_chars=shell_max_output_chars,
                durable_failure_threshold=3,
                durable_failure_ttl_sec=7200,
                task_duplicate_reuse_score=0.66,
                task_similarity_context_score=0.45,
            ),
        ),
    )


def _tool_ctx(
    *,
    act: bool = True,
    debug: bool = False,
    workspace_dir: str = "",
    shell_timeout: int = 5,
    shell_max_output_chars: int = 200,
    wm: Any = None,
    task_store: Any = None,
    episodic: Any = None,
    semantic: Any = None,
    emotion: Any = None,
    active_task: Any = None,
):
    from tools.registry import ToolContext

    return cast("Any", ToolContext)(
        config=cast(
            "Any",
            _test_config(
                act=act,
                debug=debug,
                workspace_dir=workspace_dir,
                shell_timeout=shell_timeout,
                shell_max_output_chars=shell_max_output_chars,
            ),
        ),
        wm=cast("Any", wm),
        task_store=cast("Any", task_store),
        episodic=cast("Any", episodic),
        semantic=cast("Any", semantic),
        emotion=cast("Any", emotion),
        active_task=cast("Any", active_task),
    )


def _execution_layer(reg, *, debug: bool = False):
    from core.execution import ExecutionLayer

    return ExecutionLayer(reg, _test_config(debug=debug))


@lru_cache(maxsize=1)
def _tool_registry():
    from tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.discover(_proj_root() / "tools")
    return reg


def _judgment_output(**kwargs: Any) -> Any:
    from core.judgment import JudgmentOutput

    return cast("Any", JudgmentOutput)(**kwargs)


