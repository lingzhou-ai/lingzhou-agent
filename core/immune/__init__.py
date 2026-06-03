"""core/immune/ — 免疫器官。

公理 A4：任何违反宪法的行为必须被免疫器官硬阻断，不属于外围自治，属于宪法执行。
阻断时机：工具调用前 / 候选写入提交前 / 子灵授权签发时 / 主脑升级请求时。
"""
from core.immune.constitution import (
    extract_constitution_boundaries,
    get_constitution_hash,
    get_constitution_text,
    load_constitution,
)
from core.immune.policy import (
    _DEFAULT_BLOCKED_TOOLS,
    _READONLY_ALLOWED_LOCAL_MEMORY_TOOLS,
    _READONLY_ALLOWED_TASK_TOOLS,
    _READONLY_BLOCKED_TOOL_NAMES,
    check_tool_blocked,
    is_readonly_blocked_tool,
)

__all__ = [
    "_DEFAULT_BLOCKED_TOOLS",
    "_READONLY_ALLOWED_LOCAL_MEMORY_TOOLS",
    "_READONLY_ALLOWED_TASK_TOOLS",
    "_READONLY_BLOCKED_TOOL_NAMES",
    "check_tool_blocked",
    "extract_constitution_boundaries",
    "get_constitution_hash",
    "get_constitution_text",
    "is_readonly_blocked_tool",
    "load_constitution",
]
