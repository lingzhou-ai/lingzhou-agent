from __future__ import annotations

import re

from .common import (
    _INTERLOCUTOR_TYPE_HINTS,
    _SELF_NAME_PATTERNS,
    _TOPIC_PUNCT_PATTERN,
    normalize_text,
    split_text_sentences,
)
from .models import ExtractedSignals


def extract_signals(resolver: object, message: str) -> ExtractedSignals:
    sigs = ExtractedSignals()
    cleaned = re.sub(r"\s+", " ", message).strip()
    cleaned = _TOPIC_PUNCT_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) >= resolver._thresholds.reference_topic_anchor_min_chars:
        sigs.topic_anchors.append(cleaned)
    return sigs


def extract_source_traits(message: str, *, chat_id: str = "", source_hint: str = "") -> list[str]:
    traits: list[str] = []

    def _add(trait: str) -> None:
        normalized = trait.strip()
        if normalized and normalized not in traits:
            traits.append(normalized)

    if chat_id:
        channel = chat_id.split(":", 1)[0].strip().lower()
        if channel:
            _add(f"channel={channel}")

    lowered_source = f" {source_hint.lower()} " if source_hint else ""
    for kind, tokens in _INTERLOCUTOR_TYPE_HINTS.items():
        if any(token.isascii() and f" {token} " in lowered_source for token in tokens if token.isascii()) or any((not token.isascii()) and token in source_hint for token in tokens):
            _add(f"source_kind={kind}")
    if source_hint.strip():
        compact_source = re.sub(r"\s+", " ", source_hint.strip())
        _add(f"route={compact_source}")

    lowered_message = f" {message.lower()} " if message else ""
    for kind, tokens in _INTERLOCUTOR_TYPE_HINTS.items():
        if any(token.isascii() and f" {token} " in lowered_message for token in tokens if token.isascii()):
            _add(f"counterparty={kind}")
            continue
        if any((not token.isascii()) and token in message for token in tokens):
            _add(f"counterparty={kind}")

    return traits


def extract_identity_cues(message: str, *, chat_id: str = "", source_hint: str = "") -> dict[str, list[str]]:
    text = normalize_text(message)
    if not text:
        return {
            "names": [],
            "preferences": [],
            "explicit": [],
            "source_traits": extract_source_traits(message, chat_id=chat_id, source_hint=source_hint),
        }

    names: list[str] = []
    for pattern in _SELF_NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)

    preferences: list[str] = []
    explicit: list[str] = []
    for sentence in split_text_sentences(text):
        if any(token in sentence for token in ("我喜欢", "我偏好", "我更喜欢", "请用", "以后用", "先给结论", "直接说结论")) and sentence not in preferences:
            preferences.append(sentence)
        if any(token in sentence for token in ("记住", "别忘了", "请记得")) and sentence not in explicit:
            explicit.append(sentence)

    return {
        "names": names,
        "preferences": preferences,
        "explicit": explicit,
        "source_traits": extract_source_traits(message, chat_id=chat_id, source_hint=source_hint),
    }
