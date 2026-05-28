---
name: model-routing
aliases: model.routing
description: "模型路由与推理档位技能。Use when 需要根据 model_routing_section / tool_tier_mapping / tool_capability_mapping 判断 next_phase_tier、routing_overrides、thinking_override 或 next_idle_gap 时。"
compatibility: Designed for Lingzhou multi-tier routing and model_strategy decisions.
tags: routing, model, tier, thinking
triggers: 模型路由, next_phase_tier, routing_overrides, thinking_override, next_idle_gap
match_terms: model_routing_section, tool_tier_mapping, tool_capability_mapping, next_phase_tier, routing_overrides, thinking_override, next_idle_gap_secs, next_idle_gap_ms
match_rules: |
  any: model_routing_section | tool_tier_mapping | tool_capability_mapping => 1.0
  any: next_phase_tier | routing_overrides | thinking_override | next_idle_gap_secs | next_idle_gap_ms => 0.9
  any: reader | reasoner | repair | capability => 0.5
state_rules: |
  has_active_task >= 0.5 => 0.2
  wm_pressure_ratio >= 0.05 => 0.2
---

## 模型路由判断

- `model_routing_section` 是 runtime 提供的真相；先看它，不要脑补还有未暴露的模型或自动行为。
- 先按 `tool_capability_mapping` / `tools_section[].capabilities` 判断动作属性，再看工具名表象；尤其是追问、plan 豁免、完成判定。
- `tool_tier_mapping` 只是默认层级；只有当本次动作确实需要跨层时，才在 `model_strategy` 中显式写 `next_phase_tier` 或 `routing_overrides`。
- `implicit_next_phase_default` 非空时，表示 runtime 可能替你选下一轮默认 tier；如果不想交给默认，就明确写 `next_phase_tier`。
- `reader` 用于低风险读取、枚举、轻总结；`reasoner` 用于首轮判断、策略切换、写入、回复用户、统一结论；`repair` 只用于 JSON 修复。
- `routing_overrides` 只在你明确知道某个 tier 本轮要切到指定模型时使用；传 `{}` 表示清空临时覆盖。
- `thinking_override`：简单读取设 `off/low`，常规判断维持 `medium`，复杂新任务、重大策略切换或高风险决策提前升到 `high`；`null` 恢复全局默认。
- 需要控制下一轮节奏时，再设置 `next_idle_gap_secs` / `next_idle_gap_ms`；两者同时写时以毫秒字段为准。
- 若当前已接近最终答复，或需要做统一裁决/高风险判断，下一轮倾向 `reasoner`。
