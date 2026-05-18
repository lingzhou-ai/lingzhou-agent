"""core/probe/executor.py — 探针执行器（shell / http / python）。

每种执行器都是无状态的，接收 ProbeConfig 返回 (output, error)。
所有阻塞操作通过 asyncio.to_thread 隔离，不阻塞事件循环。
"""
from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import sys
from contextlib import redirect_stdout
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import ProbeConfig

_log = logging.getLogger("lingzhou.probe")

# 探针执行超时（秒）
DEFAULT_TIMEOUT_SEC = 30


async def execute_probe(cfg: "ProbeConfig", timeout: int = DEFAULT_TIMEOUT_SEC) -> tuple[str, str | None]:
    """执行探针，返回 (output, error)。output 为空字符串表示无输出。"""
    try:
        if cfg.kind == "shell":
            return await _run_shell(cfg.spec, timeout)
        elif cfg.kind == "http":
            return await _run_http(cfg.spec, timeout)
        elif cfg.kind == "python":
            return await _run_python(cfg.spec, timeout)
        else:
            return "", f"未知探针类型: {cfg.kind}"
    except asyncio.TimeoutError:
        return "", f"超时（>{timeout}s）"
    except Exception as exc:
        return "", str(exc)


async def _run_shell(cmd: str, timeout: int) -> tuple[str, str | None]:
    def _blocking() -> tuple[str, str | None]:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout or "").strip()
            error = (result.stderr or "").strip() if result.returncode != 0 else None
            return output, error
        except subprocess.TimeoutExpired:
            raise asyncio.TimeoutError()
        except Exception as exc:
            return "", str(exc)

    return await asyncio.to_thread(_blocking)


async def _run_http(url: str, timeout: int) -> tuple[str, str | None]:
    try:
        import httpx  # type: ignore[import]
    except ImportError:
        return "", "httpx 未安装，无法使用 http 类型探针"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.text.strip()[:4096], None
    except httpx.HTTPError as exc:
        return "", str(exc)


async def _run_python(code: str, timeout: int) -> tuple[str, str | None]:
    """在受限沙盒中执行 Python 代码片段。stdout 作为输出。

    沙盒限制：只开放 print / len / range / int / float / str / list / dict /
    math / datetime 等安全内置。不允许 import os/sys/subprocess 等危险模块。
    """

    def _blocking() -> tuple[str, str | None]:
        import math
        import datetime as _dt

        safe_globals: dict = {
            "__builtins__": {
                "print": print,
                "len": len,
                "range": range,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "abs": abs,
                "min": min,
                "max": max,
                "sum": sum,
                "round": round,
                "sorted": sorted,
                "reversed": reversed,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "isinstance": isinstance,
                "type": type,
                "repr": repr,
                "math": math,
                "datetime": _dt,
            }
        }
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                exec(compile(code, "<probe>", "exec"), safe_globals)  # noqa: S102
            return buf.getvalue().strip(), None
        except Exception as exc:
            return buf.getvalue().strip(), str(exc)

    return await asyncio.to_thread(_blocking)
