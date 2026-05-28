---
name: anti-loop
description: "反循环执行纪律技能。Use when 检测到重复工具调用、WM 出现循环信号、durable_failure 窗口内、或需要判断是否继续重试时。防止相同(工具,路径)无效循环消耗 token 和 tick。"
compatibility: Designed for Lingzhou execution loop management.
tags: anti-loop, execution, discipline, wm
triggers: 循环, 重复调用, 无进展, 重试, durable_failure
match_terms: durable_failure, self_aware, repeat_action_count, memory.snapshot, file.read loop
match_rules: |
  any: 循环 | 重复调用 | 无进展 => 0.9
  any: durable_failure | repeat_action_count | 自我感知 => 1.0
state_rules: |
  failure_signal_ratio >= 0.05 => 0.5
  wm_pressure_ratio >= 0.1 => 0.3
---

## 循环信号检测

| 信号 | 含义 | 行动 |
|---|---|---|
| 相同 (工具, 路径) 上一轮无新证据 | 轻循环信号 | 换工具/路径/转总结；`reflection` 说明继续的依据 |
| 连续 2 轮相同 (工具, 路径) 无新证据 | **强循环信号** | 必须换策略，不再重复 |
| WM 中出现 `[自我感知]` 条目 | runtime 检测到连续 3 次同工具同路径，或探索预算触顶 | 先判断本轮是否带来新证据；否则立刻换策略 |
| WM 中出现 `[认知警告]` 条目 | 推理结论已多轮重复 | 执行一个产生**新证据**的动作（`file.read`/`shell.run`/`memory.search`），不要再重申相同分析 |

## WM 路径记录规则

**WM 中已有以下条目时，默认不重复**：

- `[file.list <path>]` / `[file.read <path>]`：除非文件已变更或读不同区间，否则不重复
- `[ENOENT]` / `[NOT_DIR]`：无新写入时不重试同路径
- `[file.write <path>]` / `[file.edit <path>]`：默认先推进后续步骤；最多 1 次最小验证

## wait vs task.wait 区别

| 决策 | 含义 | 使用场景 |
|---|---|---|
| `wait` | 本轮先不行动 | 当前信号正常且无紧急项；空闲整理时机 |
| `task.wait` | 持久化移出 runnable 队列 | 需要外部事件才能继续；必须明确 `wait_kind`（`process/task/signal/time/external`）和 `wait_key` |

> 证据不足/路径未确认时：优先 `reply_to_user` / `pause` / 更新 `next_step`，**不要直接 `task.wait`**

## durable_failure 窗口规则

- 静默窗口内：先当作 runtime 真相，**默认换动作/换参数/等待外部状态变化**
- 不重试同参数，除非明确掌握新外部证据
- 只有确认窗口已过或有新证据时才考虑重试

## 其他铁律

- **不要主动调用 `memory.snapshot`**：WM 整合由 runtime 自动管理（压力 > 90% 自动快照）；手动调用会过早丢失未固化证据；整合用 `memory.add_semantic` / `memory.add_wm`
- **大文件分段读取**：用 `file.read` 的 `start/end` 参数按需分段；读完每段在 `reflection` 记录核心发现
- **`reflection` 是主要压缩机制**：每次 `file.read` / `shell.run` 后在 `reflection` 提炼 1-2 句核心发现；runtime 将其以高优先级写入 WM，供后续 tick 复用

## 反例黑名单

| 反模式 | 正确做法 |
|---|---|
| WM 有 `[file.read <path>]` 仍重复读 | 默认不重读；文件变更或读新区间才重读 |
| `ENOENT` 后继续尝试同路径 | 无新写入 → 换路径/换策略 |
| 主动调用 `memory.snapshot` | 不主动快照；用 `add_semantic`/`add_wm` 整合 |
| 连续 2 轮同工具无进展仍继续 | 强循环信号 → 必须换策略 |
