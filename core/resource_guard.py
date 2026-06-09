"""Runtime resource preflight guards."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any

DEFAULT_LOCAL_EMBED_MIN_AVAILABLE_MIB = 12 * 1024

_LOCAL_EMBED_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbuild[_-]?embeddings?\.py\b", re.IGNORECASE),
    re.compile(r"\bbuild[_-]?embeddings?\b", re.IGNORECASE),
    re.compile(r"\bsentence[_-]?transformers?\b", re.IGNORECASE),
    re.compile(r"\bBAAI/bge-m3\b", re.IGNORECASE),
    re.compile(r"\bbge-m3\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ResourceGuardResult:
    ok: bool
    reason: str
    available_mib: int | None
    required_mib: int
    matched: bool = True

    def as_metadata(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "available_mib": self.available_mib,
            "required_mib": self.required_mib,
            "matched": self.matched,
        }


def parse_mem_available_mib(meminfo_text: str) -> int | None:
    for line in str(meminfo_text or "").splitlines():
        if not line.startswith("MemAvailable:"):
            continue
        parts = line.split()
        if len(parts) < 2:
            return None
        try:
            return max(0, int(parts[1]) // 1024)
        except ValueError:
            return None
    return None


def available_memory_mib() -> int | None:
    proc_meminfo = "/proc/meminfo"
    if os.path.exists(proc_meminfo):
        try:
            with open(proc_meminfo, encoding="utf-8") as fh:
                return parse_mem_available_mib(fh.read())
        except OSError:
            return None

    try:
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=1.0)
        return max(0, int(out.strip()) // (1024 * 1024))
    except Exception:
        return None


def looks_like_local_embedding_command(command: str) -> bool:
    text = str(command or "")
    return any(pattern.search(text) for pattern in _LOCAL_EMBED_COMMAND_PATTERNS)


def local_embedding_memory_preflight(
    *,
    command: str | None = None,
    model: str | None = None,
    min_available_mib: int = DEFAULT_LOCAL_EMBED_MIN_AVAILABLE_MIB,
    guard_enabled: bool = True,
    available_mib: int | None = None,
) -> ResourceGuardResult:
    required = max(0, int(min_available_mib or 0))
    if not guard_enabled or required <= 0:
        return ResourceGuardResult(True, "guard_disabled", available_mib, required, matched=True)

    marker_text = " ".join(part for part in (command, model) if part)
    matched = bool(model) or looks_like_local_embedding_command(marker_text)
    if not matched:
        return ResourceGuardResult(True, "not_local_embedding_command", available_mib, required, matched=False)

    actual_available = available_memory_mib() if available_mib is None else available_mib
    if actual_available is None:
        return ResourceGuardResult(True, "memory_unknown", None, required, matched=True)
    if actual_available < required:
        return ResourceGuardResult(
            False,
            "insufficient_available_memory_for_local_embedding",
            actual_available,
            required,
            matched=True,
        )
    return ResourceGuardResult(True, "memory_preflight_passed", actual_available, required, matched=True)


def memory_guard_settings(config: Any | None) -> tuple[bool, int]:
    memory_cfg = getattr(config, "memory", None)
    enabled = bool(getattr(memory_cfg, "local_embed_command_guard", True))
    required = int(getattr(
        memory_cfg,
        "local_embed_min_available_mib",
        DEFAULT_LOCAL_EMBED_MIN_AVAILABLE_MIB,
    ) or 0)
    return enabled, required
