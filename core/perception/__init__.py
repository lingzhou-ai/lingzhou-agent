"""core/perception — 感知层 façade。

稳定的公开导出，内部实现分布在四个子模块：
  emotion  — 情绪状态（OCC + Russell Core Affect）
  ethos    — 价值层（EthosValues / EthosState）
  signals  — 判断信号与认知信号（JudgmentSignals / CognitiveSignals）
  layer    — 感知层入口（Percept / PerceptionLayer）
"""
from __future__ import annotations

from core.perception.emotion import (
    Appraisal,
    EmotionReplaySummary,
    EmotionState,
    Feeling,
    PerceptionReplaySummary,
    Regulation,
    build_emotion_replay,
    build_perception_replay,
)
from core.perception.ethos import (
    ETHOS_DIMENSIONS,
    EthosBias,
    EthosState,
    EthosValues,
    derive_ethos_state,
)
from core.perception.layer import Percept, PerceptionLayer
from core.perception.signals import CognitiveSignals, JudgmentSignals, compute_judgment_signals

__all__ = [
    # emotion
    "Appraisal",
    "Feeling",
    "Regulation",
    "EmotionState",
    "PerceptionReplaySummary",
    "EmotionReplaySummary",
    "build_perception_replay",
    "build_emotion_replay",
    # ethos
    "ETHOS_DIMENSIONS",
    "EthosValues",
    "EthosBias",
    "EthosState",
    "derive_ethos_state",
    # signals
    "JudgmentSignals",
    "compute_judgment_signals",
    "CognitiveSignals",
    # layer
    "Percept",
    "PerceptionLayer",
]
