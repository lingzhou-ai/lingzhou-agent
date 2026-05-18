"""core.loop - 稳定 façade，统一导出 loop 包的兼容入口。"""

from .runtime import (
    CognitionLoop,
    _infer_valence_from_text,
    _next_thinking_override,
    _perception_replay_fallback,
    _prefer_tier_for_task,
    _resolve_thinking_override,
    _should_continue_within_tick,
    _task_model_tier,
    _thinking_floor,
)
from .logging import (
    DEFAULT_LOG_REPLY_CHARS,
    _clip_reply_for_log,
    _clip_signal_text,
    _fallback_reply_for_user,
    _format_action_feedback_line,
    _strip_memory_context,
    _summarize_state_delta,
)
from .postprocess import (
    _SUCCESS_STALL_TRACK_TOOLS,
    _write_success_stall_meta_reflection,
)
from .progress import (
    _PROGRESS_INFO_TOOLS,
    _PROGRESS_MUTATION_TOOLS,
    _action_key_param,
    _action_made_progress,
    _has_failure_markers,
    _looks_like_path_probe_output,
    _result_fingerprint,
    _shell_run_made_progress,
)
from core.run_refresh import _refresh_running_runs
from core.task_runtime import (
    _consume_task_runtime_hints,
    _ingest_actionable_meta_reflections,
    _sync_task_progress_state,
)

__all__ = [
    "CognitionLoop",
    "DEFAULT_LOG_REPLY_CHARS",
    "_SUCCESS_STALL_TRACK_TOOLS",
    "_PROGRESS_INFO_TOOLS",
    "_PROGRESS_MUTATION_TOOLS",
    "_action_key_param",
    "_action_made_progress",
    "_clip_reply_for_log",
    "_clip_signal_text",
    "_consume_task_runtime_hints",
    "_fallback_reply_for_user",
    "_format_action_feedback_line",
    "_has_failure_markers",
    "_infer_valence_from_text",
    "_ingest_actionable_meta_reflections",
    "_looks_like_path_probe_output",
    "_next_thinking_override",
    "_perception_replay_fallback",
    "_prefer_tier_for_task",
    "_refresh_running_runs",
    "_resolve_thinking_override",
    "_result_fingerprint",
    "_shell_run_made_progress",
    "_should_continue_within_tick",
    "_strip_memory_context",
    "_summarize_state_delta",
    "_sync_task_progress_state",
    "_task_model_tier",
    "_thinking_floor",
    "_write_success_stall_meta_reflection",
]
