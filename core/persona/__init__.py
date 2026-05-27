"""core/persona/ — 人格器官。

职责（严格限定于 Persona / 人格层）：
  - soul:ethos_baseline EMA 值的读取与写回（DB ↔ SOUL.md 镜像）
  - _soul_name / _ethos_from_db / _axioms_from_db 的 DB 访问
  - derive_ethos_state() 的数据源（EthosBaseline + DB EMA）
  - SOUL.md 人类可读镜像的生成与同步

不负责：
  - workspace 文件初始化 → SoulManager.init_files()
  - bootstrap 流程 → SoulManager.bootstrap()
  - hard_axioms 宪法边界 → 宪法器官 (core/immune/)
"""
from core.persona.engine import PersonaEngine

__all__ = ["PersonaEngine"]
