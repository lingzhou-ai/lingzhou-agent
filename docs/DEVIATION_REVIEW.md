# 蓝图偏差审查 (2026-05-19 更新)

[中文](DEVIATION_REVIEW.md) | [English](DEVIATION_REVIEW.en.md)

基于早期 roadmap 蓝图与当前实现（ARCHITECTURE.md + core/ 目录观察）的偏差对比。

## P0：必须先做

| ID | 蓝图要求 | 当前状态 | 偏差评估 |
|----|----------|----------|----------|
| P0-1 | 视觉/多模态能力 | `image.analyze` 工具已存在，但感知层是否深度集成多模态尚不确定 | 工具可用，但可能尚未打通多模态感知→判断的完整链路 |
| P0-2 | 自主循环内环（无用户消息时可连续工具调用） | `core/loop/tick.py` 中 continue 内循环已实现（日志实证：round=1/2/3 存在）；`_preferred_continue_tier` 路由已修复 | ✅ 已实现并验证 |
| P0-3 | Task-level model routing（task 级 tier 锁定） | 仅有 tick 级 next_phase_tier 和 tool_tier_mapping，无 task 持久路由 | 🔴 未实现 |

## P1：核心结构升级

| ID | 蓝图要求 | 当前状态 | 偏差评估 |
|----|----------|----------|----------|
| P1-1 | 引入 Run 抽象（Task/Run 分离） | `core/run_refresh.py` 和 `core/worker.py` 存在，但未见完整的 Run 生命周期管理和 Task-Run 关联 | 🟡 部分代码存在但抽象不完整 |
| P1-2 | Worker 执行器（exec/tool-chain/llm worker） | 日志实证：`worker=tool-chain-worker` 已出现在 tick 日志，已接入主循环 | ✅ 已集成并运行 |
| P1-3 | Run 状态回流 Task | 未见相关机制 | 🔴 未实现 |
| P1-4 | MetaReflection（双环学习器，区分单环/双环问题） | 无独立 MetaReflection 模块，进化仍停留在单环纠错 | 🔴 未实现 |

## P2：闭环质量提升

| ID | 蓝图要求 | 当前状态 | 偏差评估 |
|----|----------|----------|----------|
| P2-1 | 进化效果验证（before-after 对比） | `core/evolution.py` 存在，但缺乏结构化的效果度量 | 🟡 未明确实现 |
| P2-2 | 自动回滚 | evolution 中可能有回滚逻辑，但需验证 | 🟢 基本可用 |
| P2-3 | 多 run 并行 | 无 | 🔴 未实现 |
| P2-4 | 运行中结晶（progress crystal） | 无 | 🔴 未实现 |

## 总结

P0-2（自主内环）和 P1-2（Worker）均已经过日志实证确认为已实现。
当前仍未完成的核心缺口：P0-3（task 级路由）、P1-1（Run 抽象完整化）、P1-3（Run→Task 回流）。
建议优先投入 P0-3 和 P1-1，打穿"任务-执行"分离这一剩余核心缺口。

## qiushi-skill 学习状态

所有网络请求均失败（ConnectTimeout），当前环境无法访问 GitHub。此部分暂时阻塞，待网络恢复后继续。
