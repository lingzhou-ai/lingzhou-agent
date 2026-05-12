"""tools/shell.py — shell.run 工具。"""
from __future__ import annotations

import asyncio
from typing import Any

from tools.registry import ToolManifest, ToolParam, ToolResult, ToolContext, tool

_MANIFEST = ToolManifest(
    name="shell.run",
    description="在受限沙箱中执行 shell 命令，返回 stdout+stderr 合并输出",
    params=[
        ToolParam("command", "string", "要执行的 bash 命令", required=True),
        ToolParam("timeout", "number", "超时秒数，默认 30", required=False),
        ToolParam("workdir", "string", "工作目录，默认当前目录", required=False),
    ],
)


@tool(_MANIFEST)
async def shell_run(params: dict[str, Any], ctx: ToolContext) -> ToolResult:
    command = (params.get("command") or "").strip()
    if not command:
        return ToolResult(summary="命令为空", skipped=True)

    timeout = float(params.get("timeout") or 30)
    workdir = params.get("workdir") or None

    if ctx.dry_run:
        return ToolResult(
            summary=f"[dry-run] shell.run: {command[:200]}",
            evidence=f"dry_run=true cmd={command[:100]}",
            skipped=True,
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=workdir,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(
                summary=f"执行超时（{timeout}s）: {command[:100]}",
                evidence=f"timeout={timeout}s",
                error="TimeoutError",
            )

        output = stdout.decode(errors="replace").strip()
        truncated = output[:500] + ("..." if len(output) > 500 else "")
        if proc.returncode == 0:
            return ToolResult(
                summary=f"执行成功:\n{truncated}",
                evidence=f"exit=0 cmd={command[:100]}",
            )
        else:
            return ToolResult(
                summary=f"执行出错 (exit={proc.returncode}):\n{truncated}",
                evidence=f"exit={proc.returncode} cmd={command[:100]}",
                error=output[:300],
            )
    except Exception as exc:
        return ToolResult(
            summary=f"执行异常: {exc}",
            evidence=str(exc),
            error=str(exc),
        )
