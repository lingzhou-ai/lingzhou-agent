# 架构设计

## 认知循环

```
         ┌──────────────┐
         │  感知层      │ ← 工作记忆(WM) + 情节记忆(episodic) + 预测误差
         │  Perception  │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  好奇心引擎   │ ← Novelty + Learning Progress + Surprise
         │  Self-Drive  │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  判断层      │ ← LLM 决策 (act/wait/pause) + 工具选择
         │  Judgment    │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  执行层      │ ← 46 个工具，内层 continue 循环
         │  Execution   │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  反思层      │ ← 情节整合 + 语义编译 + 情绪更新
         │  Reflection  │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  进化引擎    │ ← 失败模式检测 → LLM 生成修复 → 热加载
         │  Evolution   │
         └──────────────┘
```

## 核心模块

### `core/loop.py` — 主循环 (CognitionLoop)
编排感知→判断→执行→反思全流程。事件驱动等待（chat/task/超时）。包含热配置重载。

### `core/judgment.py` — 判断层 (JudgmentLayer)
LLM 决策引擎：接收 WM + 信号 → 决定 action + tool。支持多模型路由 (reader/reasoner/repair)。内层 continue 循环：多次工具调用不重装上下文。

### `core/perception.py` — 感知层 (PerceptionLayer)
从 WM/emotion/episodic 计算预测误差、认知信号。生成 `DerivedEthosState` 供判断层使用。

### `core/self_drive.py` — 自驱力引擎 (SelfDriveEngine)
基于 Active Inference + Intrinsic Motivation。空闲时注入好奇心驱动的探索目标到 WM。LLM 以"内心感知"叙事形式接收，自主决定是否响应。

### `core/evolution.py` — 进化引擎 (EvolutionEngine)
检测失败模式 → LLM 生成改进代码 → 语法验证 → 热重载 → 注册验证 → 回滚。后进化验证确保系统可导入。

### `core/behavior_tracker.py` — 行为追踪 (BehaviorTracker)
追踪重复 action/read/list/edit 模式。将探针信号注入 WM 供 LLM 感知，不机械阻塞。

### `core/plugin.py` — 插件系统 (PluginManager)
discover → load → register → start 生命周期。启动时自动加载 plugins/ 目录。

## 记忆系统

### 工作记忆 (WM)
LLM 上下文窗口内的短期记忆。容量和 token 预算可配。

### 情节记忆 (Episodic)
events.jsonl 追加式记录。每次 tick 的 perception/emotion/action 结果。

### 语义记忆 (Semantic)
向量化长期记忆。支持 embedding 混合搜索。任务完成时自动编译叙事。

### 任务存储 (TaskStore)
SQLite 持久化。tasks / chat_messages / failures / signals 表。

## 工具系统

`tools/` 目录下的所有 Python 文件自动发现。每个工具：
- `@tool(ToolManifest(...))` 装饰器声明
- 异步函数 `async def xxx(params, ctx) -> ToolResult`
- 自动注册到 ToolRegistry

## 通道架构

三个 IO 通道并行运行：
- **local** — 终端交互 (lingzhou chat)
- **wechat** — 微信 bot (通过 hermesclaw 代理)
- **webhook** — HTTP 接入

通道 sidecar 在 daemon 线程中运行，与主 asyncio loop 并行。
