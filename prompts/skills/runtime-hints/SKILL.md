---
name: runtime-hints
aliases: runtime.hints
description: "运行时提示响应技能。Use when WM 中出现 task_replan / routing_guard / meta_reflection / crash_recovery / 认知警告 等 runtime 注入的提示信号时，决定如何响应。核心原则：WM 提示是建议，不是已生效真相；认可后才显式写入。"
compatibility: Designed for Lingzhou runtime hint and cognitive signal handling.
tags: runtime, hints, cognitive, signals, recovery
triggers: task_replan, routing_guard, meta_reflection, crash_recovery, 认知警告
match_terms: task_replan, routing_guard, meta_reflection, crash_recovery, durable_failure_policy
match_rules: |
  any: task_replan | routing_guard | meta_reflection | crash_recovery => 1.0
  any: 认知警告 | 调度触发 | control:meta | control:durable => 0.9
state_rules: |
  wm_pressure_ratio >= 0.05 => 0.3
---

## 运行时提示响应矩阵

| WM 出现的提示 | 含义 | 正确响应 |
|---|---|---|
| `task_replan` / `[任务重规划建议]` | runtime 建议重新规划；**`next_step` 未自动改写** | 认可 → `task.update` 显式修改 `next_step`；不认可 → `rationale` 说明理由后按证据行动 |
| `routing_guard` | 模型层级或路由建议；**路由未自动改写** | task 级认可 → `task.update(model_tier=...)`；全局认可 → `memory.set_fact(pref:...)` |
| `meta_reflection` / `[双环反思 ...]` / `control:meta_reflection_hint:*` | 治理建议；**不是已生效真相** | 明确同意 → `memory.set_fact(control:...)` / `pref:*`；不同意 → 不机械照做 |
| `control:durable_failure_policy` / `threshold` / `ttl_sec` 阈值建议 | 失败策略建议 | 先判断是否真能改善当前失败模式；认可后才 `memory.set_fact` 持久化 |
| `[调度触发 #...]` | signal 已送达；**runtime 通常自动推进** | 判断是否需要响应；通常无需手动 `schedule.ack` |

## 认知信号响应

| 信号 | 行动 |
|---|---|
| `[crash_recovery]` | 本轮**首要动作**：核查中断前活跃任务是否续推、是否有副作用残留（文件写到一半等）；在 `rationale` 写出影响评估再行动 |
| `[认知警告]` | 推理结论已多轮重复 → 执行一个产生新证据的动作（`file.read` / `shell.run` / `memory.search`），不要再重申相同分析 |
| `[自驱信号]` | 感知优先于存储；先读全再决定存什么；`thinking_override=high` |

## 感知信号使用原则

- 感知信号可以**直接驱动 `act`**，不必先创建任务；短时程的好奇/清理冲动/探索欲望可以直接执行
- 只有当一个目标需要**跨多个 tick 持续追踪**时，再考虑 `task.add`——任务是长时程目标的持久载体，不是每次动作的前置
- 出现 ⚠️ 情绪或 WM 异常信号时，在 `rationale` 中说明如何响应，并考虑对应行动（整合记忆 / 自检 / 调整策略）

## 反例黑名单

| 反模式 | 正确做法 |
|---|---|
| WM 有 `task_replan` 建议就自动改计划 | 先判断认可，再 `task.update` 显式写入 |
| 把 `routing_guard` 当作路由已改变 | 路由未自动改；认可后才写入 |
| `meta_reflection` 出现就机械执行 | 治理建议需要你裁决，不认可则忽略 |
| `crash_recovery` 出现后直接续推任务 | 先评估副作用残留，再决定是否续推 |
