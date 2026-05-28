---
name: task-continuity
aliases: task.continuity
description: "任务连续性技能。Use when 当前任务已有 next_step、current_step、task inbox 或 steering 信号，需要决定继续推进还是根据新证据转向。"
compatibility: Designed for Lingzhou task runtime with active_task / inbox steering.
tags: continuity, task
triggers: next_step, 继续推进, 当前任务
match_terms: current_step, task inbox, steering, old plan
match_rules: |
  any: next_step | 继续推进 | 当前任务 => 0.7
  any: current_step | task inbox | steering | old plan => 1.0
state_rules: |
  has_active_task => 0.35
  has_next_step => 0.85
---
## 续推 vs 转向 判断矩阵

| 信号 | 行动 |
|---|---|
| `next_step` 清晰 + 无新指令 + 无 inbox 打断 | 续推：`task.advance` 执行下一步 |
| inbox 出现 `⚠️ 转向指令` | 优先处理：认可则 `task.update` 修改计划，否则在 `rationale` 说明暂缓原因 |
| 新用户指令与 `next_step` 明显不同 | 本轮以用户指令为主；在 `reflection` 说明原任务暂缓 |
| 证据显示目标已达成但未标记完成 | `task.complete`；不要惯性续推 |
| `next_step` 已执行但无进展（循环迹象） | 停止续推，重新规划；触发 `failure-reflection` 分析 |

## 连续性维护规则

1. **每步完成后立即更新**：`task.advance(next_step="下一步描述")`，连续性来自事实而非惯性
2. **多步任务（>3 步）**：用 `task.plan` 维护结构化计划，不要仅靠散落 `next_step`
3. **阶段切换时**：更新 `next_step` 的同时，在 `reflection` 记录"上一步结果"，供后续 tick 参考
4. **`source=self_drive` 任务**：得出结论（有发现 or 维持现状）后必须 `task.complete`；不允许续命挂 `in_progress`

## 反例黑名单

| 反模式 | 正确做法 |
|---|---|
| inbox 有信号但仍机械执行旧 `next_step` | 先判断 inbox 是否改变方向，再决定行动 |
| 每轮推进但不更新 `next_step` | `task.advance` 必须携带最新 `next_step` |
| 自驱任务评估完毕后仍续命 | 结论明确 → 立刻 `task.complete` |
| 多步任务散落在单条 `next_step` | >3 步 → 用 `task.plan` 维护 |

## task.complete 使用守护

**判断标准**：`task.goal` 中描述的产出是否真实存在（文件已写入/命令已执行/用户明确确认）？

| 情形 | 行动 |
|---|---|
| 目标产出已真实存在 | `task.complete` |
| 只是"读了文件/看了目录"未实际写入 | 不应 `task.complete`，用 `task.advance` 继续 |
| 不确定目标是否达成 | `task.advance(next_step="...")` 继续，而不是提前结束 |
| `source=self_drive` 任务评估完毕 | **必须立即 `task.complete`**，不管结论是"发现改进点"还是"维持现状" |

> **自驱任务空转陷阱**：不要用 `task.update(next_step="低功耗监听/等待指令")` 续命——这会让任务永远挂 `in_progress`，自驱信号被压制，无法触发新探索。"维持现状"本身就是有效完成结论。