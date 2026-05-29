"""core/loop/runtime 包入口，保持兼容导出。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    from .main import ChainState, CognitionLoop
except ModuleNotFoundError:
    _legacy_name = "core.loop._runtime_legacy"
    _legacy_path = Path(__file__).resolve().parents[1] / "runtime.py"
    _spec = importlib.util.spec_from_file_location(_legacy_name, _legacy_path)
    if _spec is None or _spec.loader is None:
        raise
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_legacy_name] = _module
    _spec.loader.exec_module(_module)
    ChainState = _module.ChainState
    CognitionLoop = _module.CognitionLoop

__all__ = ["ChainState", "CognitionLoop"]
