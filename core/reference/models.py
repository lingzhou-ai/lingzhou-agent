from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedSignals:
    """轻量预热阶段提取的检索信号。"""

    topic_anchors: list[str] = field(default_factory=list[str])


@dataclass
class ResolvedEntity:
    """经 LLM 推理确认的实体链接结果。"""

    node_id: str
    title: str
    kind: str
    confidence: float
    snippet: str
    signal_types: list[str]
    relationship_note: str = ""


@dataclass
class ResolvedSpeaker:
    """当前交互对象的画像识别结果。"""

    node_id: str
    title: str
    confidence: float
    snippet: str
    evidence: list[str] = field(default_factory=list)
    relationship_note: str = ""
    signal_types: list[str] = field(default_factory=list)
    provisional: bool = False
    search_anchors: list[str] = field(default_factory=list)
    source_traits: list[str] = field(default_factory=list)
