"""lingzhou.py — 源码兼容入口，实际 CLI 实现在 cli.main。"""
from __future__ import annotations

from cli.main import app, app_callback, main

__all__ = ["app", "app_callback", "main"]


if __name__ == "__main__":
    main()
