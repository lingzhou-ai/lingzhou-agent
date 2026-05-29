from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.config import Config
    from core.evolution import EvolutionEngine
    from core.execution import ExecutionLayer
    from core.judgment import JudgmentLayer, JudgmentOutput
    from core.loop import CognitionLoop
    from core.perception import EmotionState, Percept, PerceptionLayer
    from core.skill import SkillRegistry


_EXPORTS: dict[str, tuple[str, str]] = {
    "Config": ("core.config", "Config"),
    "CognitionLoop": ("core.loop", "CognitionLoop"),
    "PerceptionLayer": ("core.perception", "PerceptionLayer"),
    "EmotionState": ("core.perception", "EmotionState"),
    "Percept": ("core.perception", "Percept"),
    "JudgmentLayer": ("core.judgment", "JudgmentLayer"),
    "JudgmentOutput": ("core.judgment", "JudgmentOutput"),
    "ExecutionLayer": ("core.execution", "ExecutionLayer"),
    "EvolutionEngine": ("core.evolution", "EvolutionEngine"),
    "SkillRegistry": ("core.skill", "SkillRegistry"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'core' has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))

__all__ = [
    "CognitionLoop",
    "Config",
    "EmotionState",
    "EvolutionEngine",
    "ExecutionLayer",
    "JudgmentLayer",
    "JudgmentOutput",
    "Percept",
    "PerceptionLayer",
    "SkillRegistry",
]
