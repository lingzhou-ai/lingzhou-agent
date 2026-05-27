"""core/immune/policy.py — 免疫器官工具阻断策略。

公理 A4：任何违反宪法的行为必须被免疫器官硬阻断。
本模块是宪法在工具层的唯一执行入口；子灵、执行层均从此处查询阻断结论。

迁移来源：core/subagent.py（原散落的 4 个 frozenset 和 _is_readonly_blocked_tool 函数）。
"""
from __future__ import annotations

from typing import Any

# ── 默认黑名单：子灵不能调用的高权限工具 ────────────────────────────────────────
_DEFAULT_BLOCKED_TOOLS: frozenset[str] = frozenset({
    "evolution.evolve",
    "evolution.synthesize",
    "soul.update",
    "ethos.evolve",
    "skill.evolve",
    "subagent.run",  # 禁止递归
})

# ── 只读子灵额外屏蔽的写入型工具 ─────────────────────────────────────────────────
_READONLY_BLOCKED_TOOL_NAMES: frozenset[str] = frozenset({
    "config.set",
    "memory.add_semantic",
    "memory.set_fact",
    "schedule.add",
    "schedule.ack",
    "schedule.cancel",
    "task.plan",
})

# ── 只读子灵例外允许的任务工具 ───────────────────────────────────────────────────
_READONLY_ALLOWED_TASK_TOOLS: frozenset[str] = frozenset({
    "task.ask",
    "task.list",
})

# ── 只读子灵例外允许的本地记忆工具 ──────────────────────────────────────────────
_READONLY_ALLOWED_LOCAL_MEMORY_TOOLS: frozenset[str] = frozenset({
    "memory.add_wm",
    "memory.drop_wm",
})


def check_tool_blocked(
    tool_name: str,
    hard_axioms: list[str] | None = None,
) -> str | None:
    """宪法检查点：工具调用前的统一阻断判断。

    返回 block 原因字符串（非空 = 阻断）；返回 None = 放行。
    hard_axioms 保留供未来规则匹配扩展使用。
    """
    if not tool_name:
        return "工具名为空"
    if tool_name in _DEFAULT_BLOCKED_TOOLS:
        return f"工具 {tool_name!r} 在免疫器官黑名单中（公理 A4）"
    return None


def is_readonly_blocked_tool(name: str, manifest: Any | None) -> bool:
    """只读子灵的工具阻断判断（比默认黑名单更严格）。

    迁移自 core/subagent.py::_is_readonly_blocked_tool，语义不变。
    """
    if not name:
        return True
    if name in _READONLY_ALLOWED_LOCAL_MEMORY_TOOLS:
        return False
    if name in _READONLY_BLOCKED_TOOL_NAMES:
        return True
    if name.startswith("task.") and name not in _READONLY_ALLOWED_TASK_TOOLS:
        return True
    if manifest is not None and getattr(manifest, "progress_category", "") == "mutation":
        return True
    return False


# ── 宪法保护模块：不允许被 evolve_tool 直接重写 ──────────────────────────────────
_IMMUNE_PROTECTED_MODULES: frozenset[str] = frozenset({
    "core.immune.policy",
    "core.immune.constitution",
    "core.metabolic.engine",
})


def audit_evolution_target(module_name: str) -> str | None:
    """三审协议-审一（免疫器官）：目标模块是否受宪法保护（公理 A4）？

    返回 None = 通过；返回字符串 = 拒绝原因。
    """
    if module_name in _IMMUNE_PROTECTED_MODULES:
        return f"模块 {module_name!r} 受宪法保护，不可进化（公理 A4）"
    return None
