from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class EvolutionResult:
    success: bool
    target: str = ""
    reason: str = ""
    new_code: str = ""


@dataclass
class EvolutionProposal:
    """进化提案（三审协议传递载体）——变更范围、预期效果、回滚路径。"""

    tool_name: str
    tool_path: Path
    new_src: str
    current_src: str
    feedback: str
    attempt: int = 0


def _verification_fact_key(target: str) -> str:
    return f"evolution:verify:{target}"


def _breaker_fact_key(target: str) -> str:
    return f"evolution:breaker:{target}"


def _global_breaker_fact_key() -> str:
    return "evolution:breaker:global"


def _parse_ts(raw: str) -> datetime:
    text = (raw or "").strip()
    if not text:
        return datetime.fromtimestamp(0, UTC)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return datetime.fromtimestamp(0, UTC)


def _verification_outcome(baseline: dict[str, int], observed: dict[str, int], min_runs: int) -> str:
    observed_runs = int(observed.get("runs", 0) or 0)
    observed_failures = int(observed.get("failures", 0) or 0)
    observed_successes = int(observed.get("successes", 0) or 0)
    baseline_failures = int(baseline.get("failures", 0) or 0)
    baseline_runs = max(int(baseline.get("runs", 0) or 0), 1)
    baseline_failure_rate = baseline_failures / baseline_runs
    observed_failure_rate = observed_failures / max(observed_runs, 1)

    if observed_runs < min_runs:
        return "pending"
    if observed_failures > 0 and observed_successes == 0 and observed_failure_rate >= baseline_failure_rate:
        return "regressed"
    return "verified"


def _clean_old_backups(tool_path: Path, keep: int = 3) -> None:
    """清理旧备份文件，保留最新 keep 个。"""

    parent = tool_path.parent
    stem = tool_path.stem
    backups = sorted(
        list(parent.glob(f"{stem}.backup-*"))
        + list(parent.glob(f"{stem}.lingzhou-backup")),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
    )
    for old in backups[:-keep] if len(backups) > keep else []:
        with contextlib.suppress(Exception):
            old.unlink(missing_ok=True)


def _smoke_failure_artifact_paths(module_path: Path) -> tuple[Path, Path]:
    stem = module_path.stem
    parent = module_path.parent
    return (
        parent / f".{stem}.smoke-failed.py",
        parent / f".{stem}.smoke-failed.log",
    )


def _clear_smoke_failure_artifacts(module_path: Path) -> None:
    for artifact in _smoke_failure_artifact_paths(module_path):
        with contextlib.suppress(Exception):
            artifact.unlink(missing_ok=True)


def _persist_smoke_failure_artifacts(
    module_path: Path,
    staged_source: str,
    detail: str,
) -> tuple[Path | None, Path | None]:
    source_path, log_path = _smoke_failure_artifact_paths(module_path)
    saved_source: Path | None = source_path
    saved_log: Path | None = log_path
    try:
        source_path.write_text(staged_source, encoding="utf-8")
    except Exception:
        saved_source = None
    try:
        log_path.write_text(detail, encoding="utf-8")
    except Exception:
        saved_log = None
    return saved_source, saved_log


def _summarize_smoke_failure_preview(text: str, limit: int = 320) -> str:
    preview = " ".join((text or "").split())
    return preview


def _format_smoke_failure_message(
    *,
    rel_path: str,
    detail: str,
    source_artifact: Path | None,
    log_artifact: Path | None,
) -> str:
    header_parts = [f"module={rel_path}"]
    if source_artifact is not None:
        header_parts.append(f"failed_source={source_artifact}")
    if log_artifact is not None:
        header_parts.append(f"failed_log={log_artifact}")
    head = "smoke test failed | " + " | ".join(header_parts)
    return head + "\n\n" + detail


def _smoke_failure_summary(text: str) -> str:
    first_line = (text or "").splitlines()[0].strip()
    if not first_line:
        return "smoke test failed"
    return first_line


__all__ = [
    "EvolutionProposal",
    "EvolutionResult",
    "_breaker_fact_key",
    "_clean_old_backups",
    "_clear_smoke_failure_artifacts",
    "_format_smoke_failure_message",
    "_global_breaker_fact_key",
    "_parse_ts",
    "_persist_smoke_failure_artifacts",
    "_smoke_failure_artifact_paths",
    "_smoke_failure_summary",
    "_summarize_smoke_failure_preview",
    "_verification_fact_key",
    "_verification_outcome",
]
