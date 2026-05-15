# lingzhou 文档索引

lingzhou 是一个**数字生命种子**，不是普通聊天 wrapper 或工具编排器。

## 文档

| 文件 | 内容 |
|---|---|
| `blueprint.md` | **系统蓝图（最新版）**：定位、最佳架构、Task/Run/Worker/MetaReflection |
| `ROADMAP-2026.5.15.md` | **当前活跃路线图**：优先级、阶段目标、成功标准 |
| `chat-and-task.md` | chat / task / run 的职责分工（当前推荐口径） |
| `memory-architecture.md` | 四层记忆架构：当前实现 + Run/MetaReflection 扩展方向 |
| `bootstrap-and-workspace.md` | Bootstrap 引导机制与 workspace Markdown 文件体系 |
| `emotion-module.md` | OCC 情绪模型：感知→评价→core affect→调节 |
| `ethos-module.md` | 价值层（ethos）：经验塑造的 belief 与 choice bias |
| `skill-system.md` | 技能系统：程序性知识 + 上下文激活 + 防线机制 |
| `judgment-layer.md` | 判断层：当前机制 + task-level routing / run 调度目标 |
| `soul-injection.md` | Soul 注入机制：hard_axioms / ethos_baseline / 衰减演化 |
| `schema-evolution.md` | SQLite schema 演化策略：JSON-first + future runs/meta_reflections |
| `python-runtime.md` | Python 运行时优势：热进化 + 生态 + 与 Go 的分工 |

## 建议阅读顺序

1. `blueprint.md`
2. `ROADMAP-2026.5.15.md`
3. `chat-and-task.md`
4. `judgment-layer.md`
5. `memory-architecture.md`
6. `schema-evolution.md`
7. `bootstrap-and-workspace.md`
8. `soul-injection.md`
9. `skill-system.md`
10. `emotion-module.md`
11. `ethos-module.md`
12. `python-runtime.md`
