# OpenClaw → lingzhou 迁移档案

本目录保存 **迁移期一次性工具、草案与映射文档**。

它们的定位是：
- 历史留痕
- 导入参考
- 回溯证据

它们**不是** lingzhou 当前核心运行时的一部分。

## 目录内容

- `scripts/migrate_openclaw_full_memory.py`：迁移期使用的全量导入脚本
- `migration_checklist.md`：迁移执行清单
- `migration_plan_openclaw_to_lingzhou.json`：早期迁移计划 JSON
- `openclaw_soul_mapping_draft.json`：灵魂映射草案
- `_migration_drafts/`：迁移草案文件

## 约束

1. 不要让本目录重新进入 lingzhou 的核心运行路径
2. 不要让本目录产物重新进入 `~/.lingzhou/workspace/`
3. 若未来需要迁移，只能作为参考模板，不应继续作为常驻兼容层
