from __future__ import annotations

# source_type 常量（Johnson & Raye 1981 来源监控）
SRC_HUMAN = "human"
SRC_INFERENCE = "inference"
SRC_EXECUTION = "execution"
SRC_SYSTEM = "system"
SRC_REFLECTION = "reflection"


def source_from_role(role: str) -> str:
    """从 role 自动派生 source_type（默认推断）。"""
    mapping = {
        "user": SRC_HUMAN,
        "assistant": SRC_INFERENCE,
        "assistant_reply": SRC_INFERENCE,
        "consolidation": SRC_SYSTEM,
        "reflection": SRC_REFLECTION,
        "tool": SRC_EXECUTION,
        "system": SRC_SYSTEM,
    }
    return mapping.get(role, SRC_INFERENCE)
