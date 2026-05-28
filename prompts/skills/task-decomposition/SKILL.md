---
name: task-decomposition
description: "任务拆解与执行纪律技能。Use when 接到新任务首轮执行时、需要决定是否 task.plan、是否复用相似任务、是否使用 parallel_actions 或 delegate_tasks 时。关键词：新任务、task.plan、parallel_actions、delegate_tasks、next_step 拆解。"
compatibility: Designed for Lingzhou task runtime.
tags: task, planning, decomposition, parallel
triggers: 新任务, task.plan, 拆解, parallel_actions, delegate_tasks
match_terms: task.add, task.plan, delegate_tasks, parallel_actions, next_step
match_rules: |
  any: task.plan | 拆解 | delegate_tasks => 0.9
  any: task.add | parallel_actions | next_step => 0.6
state_rules: |
  has_active_task => 0.35
---

## 新任务首轮：理解优先

接到新任务（`task.add` 后首轮执行）时，在 `rationale` 先写清楚三要素：
1. 任务目标是什么
2. 涉及哪些对象/文件/系统
3. 完成标准是什么

若目标模糊或范围不明：用 1~2 次探索（`file.list` / `memory.search`）弄清楚，再用 `task.advance` 写下拆解后的 `next_step`。

## 创建新任务前：检查相似任务

调用 `task.add` 或 `delegate_tasks` 前，先检查"其他开放任务 / 相似开放任务"：

| 情形 | 行动 |
|---|---|
| 已有任务目标/交付物/下一步大致相同 | **复用**：`task.advance` / `task.update` / `task.resume` |
| 有 `⚠️ 转向指令（inbox ...）` | 先判断是否改变计划，再决定是否延续旧 `next_step` |
| 本轮有新用户指令与 `next_step` 不同 | 以用户指令为本轮主目标；暂缓时在 `reply_to_user` 或 `reflection` 说明 |
| 确定不能复用 | 在 `rationale` 写出"为什么相似任务不能承接"，再新建 |

## 执行纪律

- **单步推进**：每轮只执行 1 个最小可验证子步骤；探索完确认再写入，写入后再验证；不把探索+写入+验证压缩在同一轮
- **多步任务（非平凡、跨多轮）**：完成 1~2 次理解后用 `task.plan` 维护结构化计划；每步更新状态，不只靠 `next_step` 散落
- **不确定某子步骤是否必要** → `pause` + `rationale` 说明疑虑，而不是跳过或盲目执行

## parallel_actions vs delegate_tasks

| 工具 | 适用场景 | 特点 |
|---|---|---|
| `parallel_actions` | 多个工具完全独立无依赖（同时读多文件/并发搜索） | 单轮多工具并发（一次 LLM 决策），`chosen_action_id` 留空 |
| `delegate_tasks` | 目标可拆分为多个独立子目标，各自需要多步工具调用 | 多任务各自多轮 LLM（并行执行），主 tick 最后统一审查 |

有下游依赖时（如"先读再写"）不用 `parallel_actions`。

## 反例黑名单

| 反模式 | 正确做法 |
|---|---|
| 新任务首轮直接开始写文件 | 先 `rationale` 三要素，再决定是探索还是执行 |
| 有相似任务仍新建 | 先复用，实在不能复用才新建，并说明原因 |
| 探索+写入+验证同一轮完成 | 单步推进，每步验证 |
| `delegate_tasks` 用于有顺序依赖的子目标 | 有依赖时用串行 `task.advance`，不是并行委派 |
