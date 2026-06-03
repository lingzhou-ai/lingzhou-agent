---
name: task-continuity
description: "任务连续性观察框架。Use when 当前任务已有 next_step、current_step、task inbox 或 steering 信号，需要先判断继续推进是否仍可解释当前证据。"
compatibility: Designed for Lingzhou task runtime with active_task / inbox steering.
tags: continuity, task
triggers: next_step, 继续推进, 当前任务
state_rules: |
  has_active_task => 0.35
  has_next_step => 0.85
---
## 连续性状态判断（观察 → 风险 → 候选动作）

### 观察面

- `next_step` 清晰、任务源未变、且无冲突 inbox：可把现有链路作为当前动作候选。
- `inbox` 或 steering 带来方向性信息：先确认是否会改变目标解释，不要默认照旧。
- 证据显示目标已完成：确认是否有可复核产出（写入、命令副作用、用户确认）后再闭环。

### 风险面

- `next_step` 持续执行但无新增可验证事实：重复推进可能进入空转循环。
- 任务指令与新消息冲突：单步续推会把旧目标硬延续到新上下文。
- 自驱任务 `in_progress` 持续很久未产出：会压低自驱回路，延迟新探索信号。

### 可选动作

| 观察-风险组合 | 你更适合的动作 |
|---|---|
| 证据匹配当前 `next_step` | `task.advance(next_step=...)` 或补齐下一步可验证动作 |
| inbox 明确改变方向 | `task.update` / `task.steer` 后重建决策链 |
| 新用户指令与当前目标偏离 | `task.amend` 调整目标后再推进 |
| 目标已达成且证据可复核 | `task.complete` |
| 循环无进展但尚未失效 | 触发 `failure-reflection` 或 `task.wait` 收敛证据 |

## 连续性状态更新建议

1. 每次可验证变化后再更新 `next_step`，把“继续”建立在新事实而非惯性上。  
2. 多步任务（>3 步）优先用 `task.plan` 管理，避免单线 `next_step` 失真。  
3. 阶段切换时，同步记录“上一步结果”到 `reflection`，让下一个 tick 能沿着可读谱系继续。  
4. `source=self_drive` 任务若评估后确认“有发现”或“维持现状”，更清晰的结果通常是 `task.complete`，而不是挂起等待。

## 自驱任务空转提醒

- `task.update(next_step="低功耗监听/等待指令")` 常是空转信号的惯性表达。
- 更稳妥的表达是：在可复核条件下做出明确结论并 `task.complete`，或在有新证据前 `task.wait` 进入可恢复状态。
