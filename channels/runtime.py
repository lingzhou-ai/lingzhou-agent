from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .wechat import describe_wechat_channel, start_wechat_channel
from .webhook import describe_webhook_channel, start_webhook_channel

_CHANNEL_DESCRIBERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "wechat": describe_wechat_channel,
    "webhook": describe_webhook_channel,
}

_CHANNEL_STARTERS: dict[str, Callable[[dict[str, Any], str | Path], object]] = {
    "wechat": start_wechat_channel,
    "webhook": start_webhook_channel,
}


def describe_channel_runtime(channel: str, channel_cfg: dict[str, Any]) -> str:
    describer = _CHANNEL_DESCRIBERS.get(channel)
    if describer is None:
        raise ValueError(f"unsupported channel runtime: {channel}")
    return describer(channel_cfg)


def start_channel_runtime(channel: str, channel_cfg: dict[str, Any], db_path: str | Path) -> object:
    starter = _CHANNEL_STARTERS.get(channel)
    if starter is None:
        raise ValueError(f"unsupported channel runtime: {channel}")
    return starter(channel_cfg, db_path)