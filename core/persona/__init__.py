"""core.persona — 人格层（身份启动、SelfModel、PersonaEngine）。"""
from __future__ import annotations

from .engine import PersonaEngine
from .identity_bootstrap import IdentityBootstrapManager
from .self_model import SelfModel, fmt_self_model

__all__ = [
    "IdentityBootstrapManager",
    "PersonaEngine",
    "SelfModel",
    "fmt_self_model",
]
