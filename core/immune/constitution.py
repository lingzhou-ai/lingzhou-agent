"""core/immune/constitution.py — 宪法文件加载与只读缓存。

公理 A3：宪法文件由人类定义，不可被任何内外部机制改写。
本模块在启动时加载并缓存宪法内容；运行时仅提供只读引用。

使用方式：
    from core.immune.constitution import load_constitution, get_constitution_hash
    text = load_constitution(path)           # 首次加载并缓存
    h = get_constitution_hash()              # 获取缓存的内容哈希（用于定时校验）
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

_log = logging.getLogger("lingzhou.immune")

# 运行时只读缓存（不允许外部修改）
_constitution_text: str | None = None
_constitution_hash: str | None = None
_constitution_path: Path | None = None


def load_constitution(path: Path) -> str:
    """加载宪法文件，缓存内容与哈希，返回文本。

    - 若文件不存在或为空，记录 warning 并返回空字符串（非阻断，由调用方决定严重程度）。
    - 同一进程内多次调用时直接返回缓存，不重复读取磁盘。
    """
    global _constitution_text, _constitution_hash, _constitution_path

    if _constitution_text is not None:
        return _constitution_text

    _constitution_path = path

    if not path.exists():
        _log.warning(
            "[immune] 宪法文件不存在: %s  "
            "（公理 A3：宪法由人类定义；首次启动请确认 workspace 初始化完成）",
            path,
        )
        _constitution_text = ""
        _constitution_hash = ""
        return ""

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        _log.warning("[immune] 宪法文件为空: %s  （请补充宪法内容）", path)
        _constitution_text = ""
        _constitution_hash = ""
        return ""

    _constitution_text = text
    _constitution_hash = hashlib.sha256(text.encode()).hexdigest()
    _log.info("[immune] 宪法已加载，sha256=%s…", _constitution_hash[:12])
    return text


def get_constitution_hash() -> str | None:
    """返回已缓存的宪法内容 sha256（未加载时返回 None）。"""
    return _constitution_hash


def verify_constitution_unchanged(path: Path) -> bool:
    """校验磁盘文件与缓存哈希一致（用于定时 probe 校验）。

    返回 True = 未被篡改；返回 False = 文件已被程序外部以外的方式修改（告警）。
    若尚未加载，则先加载再校验。
    """
    if _constitution_hash is None:
        load_constitution(path)

    if not path.exists():
        _log.error("[immune] 宪法文件在运行时消失: %s  （严重违规）", path)
        return False

    current = hashlib.sha256(
        path.read_text(encoding="utf-8").strip().encode()
    ).hexdigest()

    if current != _constitution_hash:
        _log.error(
            "[immune] 宪法文件哈希不一致！缓存=%s… 当前=%s…  路径=%s",
            (_constitution_hash or "")[:12],
            current[:12],
            path,
        )
        return False

    return True


def verify_constitution_integrity() -> str:
    """零参数宪法完整性检查，供内置探针调用。

    返回值：
    - "ok"           — 哈希与启动时一致
    - "tampered"     — 文件已被修改（告警）
    - "missing"      — 文件运行时消失（告警）
    - "uninitialized" — 启动时宪法未加载，无参考哈希（不告警）
    """
    if _constitution_path is None or not _constitution_hash:
        return "uninitialized"
    if not _constitution_path.exists():
        _log.error("[immune] 宪法文件在运行时消失: %s  （严重违规）", _constitution_path)
        return "missing"
    current = hashlib.sha256(
        _constitution_path.read_text(encoding="utf-8").strip().encode()
    ).hexdigest()
    if current != _constitution_hash:
        _log.error(
            "[immune] 宪法文件哈希不一致！缓存=%s… 当前=%s…  路径=%s",
            _constitution_hash[:12], current[:12], _constitution_path,
        )
        return "tampered"
    return "ok"
