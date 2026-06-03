---
name: runtime-hints
description: "运行时感知信号解读技能。Use when WM 中出现 task_replan / routing_guard / meta_reflection / crash_recovery / 认知警告 / 自驱事件等 runtime 注入的感知事件时，帮助主脑区分 observation / risk / proposal / action 责任边界。"
compatibility: Designed for Lingzhou runtime hint and cognitive signal handling.
tags: runtime, hints, cognitive, signals, recovery
triggers: task_replan, routing_guard, meta_reflection, crash_recovery, 认知警告
state_rules: |
  wm_pressure_ratio >= 0.05 => 0.3
---

## 运行时提示响应矩阵（原运行时感知矩阵）

| WM 可见事件 | observation（可见事实） | risk/uncertainty（不确定区） / proposal（候选建议） |
|---|---|---|
| `task_replan` / `[任务重规划建议]` | runtime 观察到任务计划可能不再适配 | `next_step` 仍未改变；是否修改取决于当前证据 |
| `routing_guard` | runtime 观察到模型层级或路由可能不匹配任务复杂度 | 路由仍未改变；它是候选调整，不是事实 |
| `meta_reflection` / `[双环反思 ...]` / `control:meta_reflection_hint:*` | 治理层提出了一个候选控制规则或偏好 | 这是 proposal，不是已落定的生命状态 |
| `control:durable_failure_policy` / `threshold` / `ttl_sec` | 失败窗口暴露出策略参数可能需要调整 | 先判断该参数是否能解释当前失败模式 |
| `[调度触发 #...]` | 外部或内部 signal 已进入上下文 | signal 已送达不等于必须行动 |

## 认知信号的观察框架

| 信号 | 可见事实 | 风险或不确定性 |
|---|---|
| `[crash_recovery]` | 上一轮运行可能中断，活跃任务和副作用状态需要重新确认 | 直接续推可能覆盖半完成结果；过度保守可能丢失进展 |
| `[认知警告]` | 近期判断或行动重复，新增证据不足 | 继续陈述同一结论会消耗 tick；贸然换路可能丢掉有效线索 |
| `[自驱事件]` / `[好奇心事件]` | 内在驱动力越过阈值，且给出了候选方向和开放问题 | 候选方向可能有价值，也可能与已有任务重复 |

## 感知信号使用原则

- 把 WM 信号视为 `observation` 或 `proposal`，不是已经生效的状态。
- 若要改变任务、路由、控制规则或偏好，需要显式产生正式写入，由代谢器官落定。
- 短时程观察可以直接进入一次行动裁决；跨 tick 追踪的目标才需要任务载体。
- 在 `rationale` 中说明你看见了什么、还不确定什么、为什么当前选择比其他选项更合适。

## 误读风险（避免把 suggestion 当事实）

| 误读 | 更准确的理解 |
|---|---|
| WM 有 `task_replan` 就等于计划已经错了 | 只是 runtime 发现了计划风险，需要主脑复核 |
| `routing_guard` 出现就等于路由已改变 | 路由仍是原状态，除非正式写入或任务更新 |
| `meta_reflection` 出现就要照做 | 它是候选治理规则，需要证据支持和主脑裁决 |
| `crash_recovery` 出现后继续或停止都是默认正确 | 先读副作用和任务状态，再裁决 |
