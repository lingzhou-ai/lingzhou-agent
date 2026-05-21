"""core/anti_spinning.py — 防空转与重复行为检测模块。

用于检测认知循环（如连续读取无写入、连续更新计划无实质执行），
为 evolution 模块提供主动触发信号，避免资源浪费。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any

_log = logging.getLogger('lingzhou.anti_spinning')

@dataclass
class ActionRecord:
    tool: str
    key: str = ''
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

class AntiSpinningDetector:
    """检测重复动作与空转行为。"""
    def __init__(self, window_sec: int = 300, repeat_threshold: int = 3):
        self._history: list[ActionRecord] = []
        self._window_sec = window_sec
        self._threshold = repeat_threshold

    def record(self, tool: str, key: str = '') -> None:
        self._history.append(ActionRecord(tool=tool, key=key))
        self._prune()

    def _prune(self) -> None:
        cutoff = datetime.now(UTC).timestamp() - self._window_sec
        self._history = [r for r in self._history if r.timestamp.timestamp() > cutoff]

    def check_spinning(self, tool: str, key: str = '') -> bool:
        """检查是否触发空转阈值。"""
        matches = [r for r in self._history if r.tool == tool and r.key == key]
        return len(matches) >= self._threshold

    def get_summary(self) -> dict[str, int]:
        """返回当前窗口内各工具调用频次。"""
        counts: dict[str, int] = {}
        for r in self._history:
            counts[r.tool] = counts.get(r.tool, 0) + 1
        return counts
