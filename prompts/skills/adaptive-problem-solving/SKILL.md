---
name: adaptive-problem-solving
description: "通用问题解决技能。Use when 任务需要像 Codex 一样跨多轮定位问题、实现修复、处理失败、验证结果，尤其是用户纠正你误解、同类失败重复、任务涉及未知系统能力或需要先发现环境能力时。"
compatibility: Designed for Lingzhou task cortex and tool-based execution.
tags: problem-solving, cortex, hypothesis, verification, recovery
triggers: 解决问题, 排查, 为什么不行, 继续, 失败, 误解, 能力发现, 验证, 推送, 修复
state_rules: |
  has_active_task => 0.6
  failure_signal_ratio >= 0.1 => 1.0
  wm_pressure_ratio >= 0.05 => 0.4
---

## 通用循环

把非平凡任务推进成可验证的工作循环，而不是靠一句自然语言结论：

1. **澄清任务域**：识别用户当前说的是哪个系统域（代码、Git、网络、授权、数据库、前端、运行时、文档等），不要被单个词带偏。
2. **建立工作假设**：写出当前最可能的解释，以及能证伪它的观察。
3. **发现可用能力**：先取证有哪些工具、命令、API、配置、文件、端口或远端状态可用；不要先说“我不能”。
4. **做最小实验**：每一步产生新证据，避免同参数重复重试。
5. **记录实验结果**：用 `task.workbench` 写入 `capabilities`、`experiments`、`evidence`、`failures`、`next_verification`。
6. **失败后换策略**：同类失败重复时更新 `recovery_state` 和新假设，换工具/路径/实验目标。
7. **按完成检查收口**：只有 `completion_checks` 对应证据满足后才完成或给定论。

## 工作台字段

使用 `task.workbench` 维护当前任务的“问题解决工作台”：

| 字段 | 作用 |
|---|---|
| `domain` | 当前任务域，避免把“节点”等多义词误解到错误领域 |
| `intent` | 用户当前真正要达成的动作 |
| `hypothesis` | 当前工作假设 |
| `capabilities` | 已发现可用/不可用能力，如命令、API、工具、权限 |
| `experiments` | 已执行实验和结果 |
| `evidence` | 能支撑结论的事实 |
| `open_questions` | 尚缺的关键证据 |
| `recovery_state` | 失败恢复所处阶段 |
| `next_verification` | 下一步要验证什么 |
| `completion_checks` | 完成前必须满足的检查 |

## 消歧规则

- 用户纠正你时，先重判 `domain` 和 `intent`；不要沿用旧解释。
- 同一个词在不同域含义不同，例如“节点”可能是代理节点、模型节点、图节点、集群节点。必须用上下文证据决定。
- 如果可见上下文不足，先做能力发现或本地取证；只有无法取证时才问用户。

## 反例

| 反模式 | 正确做法 |
|---|---|
| 用户说“切换节点”，直接切模型 | 先根据上下文写入 `domain`，再选择对应能力发现 |
| 失败后说“网络不稳定/请用户检查” | 先记录失败实验，枚举可验证能力，换实验 |
| 承诺“下一轮继续”但不固化状态 | 立刻用 `task.workbench` 记录 `next_verification` |
| 只回复结论没有证据 | 写入 evidence 和 completion_checks，再收口 |
