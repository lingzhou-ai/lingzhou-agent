---
name: memory-stewardship
description: "记忆与知识管理技能。Use when 任务完成后、空闲整理时、遇到新事实/经验/可复用流程时，决定用 memory.set_fact / memory.add_semantic / skill.synthesize 哪种方式存储。防止知识浪费和重复探索。"
compatibility: Designed for Lingzhou memory and skill management.
tags: memory, knowledge, skill, stewardship
triggers: 记忆, 存储, 知识, skill.synthesize, 空闲整理
state_rules: |
  wm_pressure_ratio >= 0.1 => 0.5
---

## 知识分层：存哪里？

| 类型 | 判断标准 | 工具 |
|---|---|---|
| **陈述性事实** | 能写成"X 是 Y" | `memory.set_fact` |
| **经验结论/洞察/教训** | 能写成"上次 X 情况下发现了 Y" | `memory.add_semantic` |
| **可复用工作流** | 能写成"做 A → 验证 B → 再做 C"（≥5步，或非显然护栏） | `skill.synthesize` 新建 |
| **现有 skill 效果偏差** | 已有 skill 但执行偏差或场景未覆盖 | `skill.evolve` 改进 |
| **重要观察但尚未结论** | 当前 tick 需关注，未到长期价值 | `memory.add_wm` |

> **判断口诀**：能写成"X 是 Y"= 记忆；能写成步骤序列 = 技能；有偏差 → 先 evolve，不要重复踩坑

## 触发时机

- **完成任务后**：调用 `memory.add_semantic` 记录关键经验；若含可复用流程 → `skill.synthesize`
- **空闲（无活跃任务）时**：主动审视 WM，未沉淀的重要观察/结论 → `memory.add_semantic` 固化
- **遇到新事实**（路径、配置值、用户偏好、环境信息）：`memory.set_fact` 持久化，避免下次重复探索
- **WM 未沉淀内容 + 选择 wait** = 知识浪费；空闲 tick 是整理记忆的最佳时机

## 自驱探索时的存储纪律

WM 中出现 `[自驱信号]` 时：

1. **感知优先于存储**：`file.read` / `file.list` 时不加 `limit` 参数，先读全，再决定存什么
2. **信息完整是硬前提**：只看前 50 行就下结论 = 盲人摸象；宁可多读一次
3. **存储可以选择**：只把真正有复用价值的结论写入长期记忆；临时探索上下文不必永久存储
4. **思考强度**：按模型路由与当前复杂度选择；探索阶段通常偏高，写入与总结阶段可回落。

## 反例黑名单

| 反模式 | 正确做法 |
|---|---|
| 任务完成后直接 wait，WM 内容未沉淀 | 先固化经验/事实，再 wait |
| 把工作流也写成 `memory.add_semantic` 一大段 | ≥5步且可复用 → `skill.synthesize` |
| 已有 skill 效果差还继续用 | 先 `skill.evolve` 修正，不要重复踩坑 |
| 自驱探索用 `limit=50` 读文件 | 先读全，再决定存什么 |
