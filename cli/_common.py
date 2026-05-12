"""cli/_common.py — CLI 公共工具：console、_load_cfg、PROJECT_ROOT。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from core.config import Config

# cli/ 的上一级就是项目根目录
PROJECT_ROOT: Path = Path(__file__).parent.parent

console = Console()


def load_cfg(config: Path) -> "Config":
    from core.config import Config
    return Config.load(config)
