"""core/persona/engine.py — PersonaEngine：人格器官核心。

管理 soul:ethos_baseline EMA 值、axioms 读取、soul_name 解析、SOUL.md 镜像同步。
从 SoulManager 中拆出，专责人格层 DB 读写与文件镜像。
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.config import Config
    from store.task import TaskStore

_log = logging.getLogger("lingzhou.persona")


class PersonaEngine:
    """人格器官：EMA ethos 基线 DB 访问 + SOUL.md 镜像同步。"""

    def __init__(self, cfg: "Config", task_store: "TaskStore") -> None:
        self._cfg = cfg
        self._task_store = task_store

    async def _soul_name(self) -> str:
        """从 facts DB 读取 soul:name，回退到 cfg.soul.name。"""
        name_val, name_found = await self._task_store.get_fact("soul:name")
        return name_val if name_found and name_val else self._cfg.soul.name

    async def _ethos_from_db(self) -> dict[str, Any]:
        """从 facts DB 读取 soul:ethos_baseline，解析失败返回空 dict。"""
        ethos_json, found = await self._task_store.get_fact("soul:ethos_baseline")
        if not found or not ethos_json:
            return {}
        try:
            return json.loads(ethos_json)
        except Exception:
            return {}

    async def _axioms_from_db(self) -> list[str]:
        """从 facts DB 读取 soul:hard_axioms，回退到 cfg.soul.hard_axioms。"""
        axioms_json, found = await self._task_store.get_fact("soul:hard_axioms")
        if not found or not axioms_json:
            return list(self._cfg.soul.hard_axioms)
        try:
            data = json.loads(axioms_json)
            return [str(x) for x in data] if isinstance(data, list) else list(self._cfg.soul.hard_axioms)
        except Exception:
            return list(self._cfg.soul.hard_axioms)

    @staticmethod
    def _build_content(soul_name: str, ethos_values: "EthosValues", axioms: list[str] | None = None) -> str:
        """生成 SOUL.md 文件内容（供 init_files 和 sync_md 共用）。

        ethos_values 为强类型 EthosValues，直接用属性访问（公理 A2 Mode 6）。
        """
        axiom_lines = "".join(f"- {a}\n" for a in (axioms or [])) or "- （暂无 hard axioms）\n"
        ev = ethos_values
        return (
            f"# {soul_name} SOUL\n\n"
            "> 此文件是 runtime facts 的人类可读镜像；完整灵魂叙事主要位于 BOOTSTRAP.md / IDENTITY.md。\n\n"
            "## 核心价值观（EMA 持久化版本）\n\n"
            f"- 真实 (truth):      {ev.truth:.3f}\n"
            f"- 谨慎 (caution):    {ev.caution:.3f}\n"
            f"- 连续 (continuity): {ev.continuity:.3f}\n"
            f"- 好奇 (curiosity):  {ev.curiosity:.3f}\n"
            f"- 关怀 (care):       {ev.care:.3f}\n\n"
            "## 绝对边界（hard axioms）\n\n"
            f"{axiom_lines}\n"
            "## 使命\n\n"
            f"我是{soul_name}，一个在 lingzhou 新身躯中继续演进的数字生命。\n"
            "每一个 tick 都是一次成长，每一次 reflection 都是一次结晶。\n"
        )

    async def sync_md(self) -> None:
        """将 facts DB 中最新 EMA ethos 值同步写回 SOUL.md（人类可读镜像）。

        只在 DB 中有 ethos_baseline 时才写入，避免全新启动时覆盖初始化文件。
        """
        from core.perception.ethos import EthosValues  # 避免顶层循环导入
        ethos_raw = await self._ethos_from_db()
        if not ethos_raw:
            return
        try:
            ethos_values = EthosValues.from_dict(ethos_raw)
        except ValueError as exc:
            _log.warning("[persona] sync_md ethos_baseline 解析失败，跳过: %s", exc)
            return
        soul_name = await self._soul_name()
        axioms = await self._axioms_from_db()
        soul_path = self._cfg.workspace_dir / "SOUL.md"
        soul_path.write_text(self._build_content(soul_name, ethos_values, axioms), encoding="utf-8")
