"""core.paths — 灵舟路径工具。统一 workspace 和 data 目录引用。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_DATA_DIR: Path | None = None
_PROJECT_DIR = Path(__file__).resolve().parents[2]
_GENERATED_DIR: Path | None = None


def _select_data_dir() -> Path:
    candidates: list[Path] = []
    env_override = os.getenv("LINGZHOU_DATA_DIR")
    if env_override:
        candidates.append(Path(env_override).expanduser())
    candidates.extend(
        [
            Path("~/.lingzhou").expanduser(),
            Path.home() / ".cache" / "lingzhou",
            Path(tempfile.gettempdir()) / "lingzhou",
        ]
    )
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if os.access(candidate, os.W_OK):
            return candidate
    # 最后的回退：无可写目录时，以异常方式暴露问题
    fallback = candidates[-1]
    raise RuntimeError(f"数据目录 {fallback} 不可写")


def _set_data_dir() -> Path:
    global _DATA_DIR, _GENERATED_DIR
    _DATA_DIR = _select_data_dir()
    _GENERATED_DIR = _DATA_DIR / "generated"
    return _DATA_DIR


def _ensure_dir_writable(p: Path, name: str) -> None:
    """确保目录存在且可写，否则抛出明确异常。"""
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"无法创建{name}目录 {p}: {e}") from e
    if not os.access(p, os.W_OK):
        raise RuntimeError(f"{name}目录 {p} 不可写")


def project_root() -> Path:
    """项目根目录。"""
    if not _PROJECT_DIR.exists():
        raise RuntimeError(f"项目根目录不存在: {_PROJECT_DIR}")
    return _PROJECT_DIR


def data_dir() -> Path:
    """数据目录 ~/.lingzhou。"""
    if _DATA_DIR is None:
        _set_data_dir()
    assert _DATA_DIR is not None
    _ensure_dir_writable(_DATA_DIR, "数据")
    return _DATA_DIR


def generated_dir() -> Path:
    """生成文件目录 ~/.lingzhou/generated（运行期数据目录）。"""
    if _DATA_DIR is None:
        _set_data_dir()
    assert _GENERATED_DIR is not None
    _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    return _GENERATED_DIR
