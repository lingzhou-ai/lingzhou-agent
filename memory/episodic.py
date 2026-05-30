"""Backward-compatible import shim for legacy path memory.episodic.

Canonical implementation moved to store.episodic. Keep this module so
old deployments/import paths continue working during upgrades.
"""

from __future__ import annotations

from store.episodic import (  # re-export legacy symbols
    SRC_EXECUTION,
    SRC_HUMAN,
    SRC_INFERENCE,
    SRC_REFLECTION,
    SRC_SYSTEM,
    EpisodicMemory,
)

__all__ = [
    "EpisodicMemory",
    "SRC_HUMAN",
    "SRC_INFERENCE",
    "SRC_EXECUTION",
    "SRC_SYSTEM",
    "SRC_REFLECTION",
]
