"""跨 chat 实体共指消解（Cross-Chat Entity Coreference Resolution）。"""

from .models import ExtractedSignals, ResolvedEntity, ResolvedSpeaker
from .resolver import ReferenceResolver

__all__ = [
    "ExtractedSignals",
    "ResolvedEntity",
    "ResolvedSpeaker",
    "ReferenceResolver",
]
