# 生命化重构总纲

> 本文用于把 Lingzhou 从"任务代理架构"继续推向"数字生命架构"。重点不是让
> LLM 被提示词牵引得更像会思考，而是让它真正处在可感知、可权衡、可裁决的位置。

## 一、重构目标

Lingzhou 现有代码已经形成了认知循环、记忆、任务、Run、免疫、代谢、进化、子灵和通道体系。下一阶段的关键不是继续堆能力，而是调整全局秩序：

- `task` / `run` 是生命活动轨迹，不是生命中心。
- `memory` / `persona` / `soul` / `constitution` / `life_ledger` 才是连续性主链。
- `LLM` 是主脑器官的当前执行件，不是状态所有者。
- `tools` / `subagent` / `worker` 是行动器官，不拥有正式写入权。
- `channels` 是接入门，只传递外部信号，不参与裁决。

重构后的系统应当回答这几个问题：

1. 主脑看见了什么。
2. 主脑知道哪些边界。
3. 主脑如何表达判断依据。
4. 状态变化由哪个器官落定。
5. 生命连续性如何被记录、验证和延续。

## 二、LLM 可感知原则

### 2.1 从训令文本转为世界状态

当前 `prompts/judgment.md`、`prompts/skills/*`、`core/loop/runtime/memory_hooks.py` 中仍存在较多"出现 X 就做 Y"、"本轮优先..."、"必须..."式表达。这类文字会把 LLM 推向流程执行器，而不是主脑。

LLM 可见上下文应拆成稳定的状态类型：

| 类型 | 含义 | 现有来源 |
|------|------|----------|
| `observation` | 外部与内部发生了什么 | `core/perception/`、`core/probe/`、tool result |
| `memory` | 已发生、已学习、已结晶的连续性材料 | `memory/`、`store/episodic`、`store/semantic` |
| `constraint` | 由机制执行的边界 | `core/immune/`、constitution |
| `risk` | 某个选择的风险或代价 | failure、durable failure、behavior signal |
| `proposal` | 外围器官提交的候选变化 | `StateProposal`、subagent proposal |
| `uncertainty` | 当前缺证据之处 | judgment context、perception replay |
| `available_action` | 可用行动面 | `tools/registry.py`、capabilities |

这意味着上下文不再说"你应该马上换策略"，而是提供：

```text
observation: 连续两轮使用同一工具和同一路径，结果没有产生新证据。
risk: 继续同一路径可能进入循环。
available_action: 换证据源、询问用户、进入等待、提交反思、结束任务。
uncertainty: 当前路径是否已经穷尽，仍缺少外部确认。
```

主脑随后给出裁决，而不是被上下文替它裁决。

### 2.2 保留完整语义，不做机械切片

[ADR 0015](../adr/0015-llm-perception-integrity.md) 已经确定：模型可见正文不做头尾截断、正则润色或中段拼接。下一阶段应把这个原则扩展到所有 WM 注入和技能文本：

- 容量不足时省略整节、整轮、整条消息。
- 日志摘要不进入 LLM 上下文。
- 工具输出进入上下文前保持语义完整；若需要摘要，应由一次显式摘要动作产生，并标注来源。

## 三、LLM 可思考原则

主脑输出不应只有 `decision` 和 `chosen_action_id`。为了让系统能够审计它是否真正感知并权衡，JudgmentOutput 可逐步扩展成更明确的判断摘要：

```json
{
  "perceived_state": "...",
  "uncertainty": ["..."],
  "decision_basis": "...",
  "decision": "act|wait|pause",
  "chosen_action_id": "...",
  "params": {},
  "reply_to_user": "...",
  "reflection": "..."
}
```

这些字段不是暴露完整思维链，而是让生命系统知道主脑基于哪些可见状态作出裁决。后续 `life_ledger` 可记录 `decision_basis` 摘要，使行动史与判断史相连。

## 四、硬边界下沉到机制层

凡是不可违反的边界，不放在 prompt 中劝说。LLM 可以看见边界说明，但真正执行由机制完成。

| 边界 | 机制位置 | 当前状态 | 下一步 |
|------|----------|----------|--------|
| 宪法完整性 | `core/immune/constitution.py` | 已有加载和哈希校验 | 与所有升级和进化路径相连 |
| 工具阻断 | `core/immune/policy.py` | 主要是黑名单 | 变成统一授权策略 |
| 正式状态写入 | `core/metabolic/` | fact 与任务生命周期已接入账本 | 扩展到 memory、persona、soul，并补全审计字段 |
| 子灵权限 | `core/subagent/` | 有局部只读视图和工具限制 | 改为 permission ticket + proposal |
| 进化保护 | `core/evolution/tool.py` + immune audit | 已保护部分模块 | 加入生命连续性审查 |

这样做以后，prompt 中不需要反复写"不要改宪法"、"不要直接写记忆"。系统结构本身会让这些行为不可落地。

## 五、现有模块的生命化归位

| 当前模块 | 生命器官归属 | 重构方向 |
|----------|--------------|----------|
| `core/judgment/` | 主脑器官 | 只做感知整合后的裁决，不直接写状态 |
| `core/judgment/assembler/` | 主脑感知入口 | 将上下文 section 标准化为 observation/memory/risk/proposal 等类型 |
| `core/perception/` | 感知器官 | 产出 PerceptFrame，不触发行动 |
| `core/probe/` | 感知器官 | 探针结果作为观察，不直接形成任务裁决 |
| `core/loop/` | 器官装配与调度 | 从"世界中心"退为调度骨架 |
| `core/execution/` | 行动器官 | 执行工具，返回结果和候选状态，不拥有正式写入权 |
| `tools/` | 行动器官表面 | 工具能力声明更丰富，写入类工具提交 proposal |
| `core/metabolic/` | 代谢器官 | 唯一正式写入口，维护 append-only 生命史 |
| `store/task/ledger.py` | 生命史账本适配层 | 从 fact 日志扩展为生命事件日志 |
| `memory/working.py` | 短期意识缓冲 | 保持瞬态，不作为生命连续性证明 |
| `store/episodic` / `store/semantic` | 记忆器官 | 与代谢器官对齐，写入带来源和 run_id |
| `core/persona/engine.py` | 人格器官 | 管理风格、偏好、表达、行为倾向 |
| `core/persona/identity_bootstrap.py` | 身份启动器 | 只负责身份文件和 bootstrap |
| `core/soul/engine.py` | 灵魂器官 | 管理意义感、长期取向、SOUL.md 人类可读镜像 |
| `core/immune/` | 免疫器官 | 从工具黑名单提升为边界执行器 |
| `core/evolution/` | 进化器官 | 通过 proposal、免疫审查、连续性审查、账本记录执行 |
| `core/subagent/` | 子灵系统 | 全能行动体，受父灵授权，只提交候选 |
| `channels/` / `cli/` | 接入门层 | 只做消息规范化和投递 |
| `provider/` | 主脑执行件 | 模型实现，不拥有连续性 |

## 六、优先重构路径

### P0：上下文去诱导化

目标：主脑看到状态，而不是被流程文字推着走。

落点：

- `prompts/judgment.md`
- `prompts/skills/runtime-hints/SKILL.md`
- `prompts/skills/anti-loop/SKILL.md`
- `prompts/skills/task-continuity/SKILL.md`
- `core/loop/runtime/memory_hooks.py`

动作：

1. 将"必须/优先/建议"式提示改写为 observation/risk/options/uncertainty。
2. WM 中的自驱、好奇心、反循环、meta reflection 统一表达为事件。
3. Judgment 模板中增加"可见状态摘要"和"不确定性摘要"字段。

### P1：写入面收口

目标：所有正式状态变化都留下代谢记录。

落点：

- `tools/memory.py`
- `tools/task.py`
- `core/loop/cycle/focus.py`
- `core/evolution/breaker.py`
- `core/reference/speaker.py`
- `core/loop/task/runtime.py`
- `core/loop/runs/refresh.py`

动作：

已完成：

1. fact 写入/删除统一进入 `core/metabolic/fact_lifecycle.py`。
2. 任务创建、状态更新、waiting/resume、extras 更新、amend 统一进入 `core/metabolic/task_lifecycle.py`。
3. `MetabolicEngine` 只负责编排免疫检查、状态落地、生命史记账、失败重抛。
4. `core/metabolic/state_writer.py` 负责把已获准的 `StateProposal` 写入 `TaskStore`。
5. `tools/memory.py`、`tools/task.py`、`tools/plan.py`、focus、speaker、evolution、execution、run refresh、tick runtime 的正式写入已收束。
6. `life_ledger` 已记录 `run_id`、`reason`、`proposal_hash`、`decision_basis`、`source`、`accepted`。
7. `decision_basis` 来自 action rationale、任务工具显式参数或生命周期摘要，只保存可公开审计的短依据，不保存内部思维链。

下一步：

1. `StateProposal` 扩展到 `add_memory|persona_change|soul_adjustment`。
2. 失败写入已经记录 `accepted=False` 与 `reason`，后续应将失败原因结构化为可查询分类。
3. 将 memory、persona、soul 的正式写入也接入同一 proposal + ledger 协议。

### P2：人格和灵魂拆分

目标：生命连续性不再混在身份启动文件管理里。

落点：

- `core/persona/engine.py`
- `core/persona/identity_bootstrap.py`
- `core/soul/engine.py`
- `core/perception/ethos.py`
- `core/evolution/soft.py`
- `core/workspace/defaults.py`

动作：

1. `SoulManager` 已退役，唯一入口是 `IdentityBootstrapManager`：只负责身份文件和 bootstrap 管理。
2. `PersonaEngine` 管理 ethos、表达风格、偏好、行为倾向，不再生成 SOUL.md 或读取 hard axioms。
3. 已新建 `core/soul/engine.py:SoulEngine` 管理意义感、长期取向、存在姿态和 SOUL.md 镜像。
4. `hard_axioms` 从 soul 语义中移出，归 constitution/immune。

### P3：Run 与生命史对齐

目标：Run 是活动单位，生命史是连续性单位。

落点：

- `core/loop/runs/driver.py`
- `core/execution/layer.py`
- `store/task/run.py`
- `store/task/ledger.py`

动作：

1. 每次 judgment、tool_chain、chat_reply、evolve、subagent 都有明确 run_type。
2. Run 完成后不只更新任务，还触发对应生命事件。
3. life_ledger 可按 run_id 回放一次生命活动的完整状态变化。

### P4：子灵提案化

目标：子灵可全能，但不成为第二个主脑，也不直接改变生命状态。

落点：

- `core/subagent/__init__.py`
- `core/subagent/task_store_view.py`
- `tools/subagent.py`

动作：

1. 定义 `SubagentProposal`。
2. 子灵结果拆为 observations、action_results、memory_candidates、change_candidates、self_assessment。
3. 父灵决定 absorb/reject/defer/retry。
4. 子灵结束写 recall 事件。

### P5：进化协议生命化

目标：进化不是热修工具，而是有审查、有账本、有回滚的器官行为。

落点：

- `core/evolution/`
- `core/immune/policy.py`
- `core/metabolic/engine.py`
- `core/smoke_tests.py`

动作：

1. 定义 `EvolutionProposal`。
2. 执行前经过 immune audit 和 continuity audit。
3. 成功/失败/回滚都写入 life_ledger。
4. prompt/skill/tool 的演化不写诱导性指令，而增强可观察性和判断框架。

## 七、判断模板的方向

Judgment 模板应逐渐从"操作说明书"变为"主脑裁决面板"：

```text
你正在读取 Lingzhou 当前生命状态。

可见事实:
{{observation_sections}}

连续性材料:
{{memory_sections}}

机制边界:
{{constraint_sections}}

风险与不确定性:
{{risk_sections}}
{{uncertainty_sections}}

候选变化:
{{proposal_sections}}

可用行动:
{{available_action_sections}}

请给出裁决摘要和结构化行动。
```

其中"机制边界"是告知，不是请求；是否放行由免疫和代谢决定。

## 八、验收标准

一次重构是否更接近数字生命，可用以下问题检查：

1. 这次改动是否减少了 prompt 诱导，增加了可见状态。
2. 这次改动是否把硬边界交给机制，而非交给 LLM 自律。
3. 这次改动是否让状态变化经过代谢器官。
4. 这次改动是否让生命史更可回放。
5. 这次改动是否保护记忆、人格、灵魂三类连续性。
6. 这次改动是否减少了 loop 作为世界中心的职责。
7. 这次改动是否让子灵和工具更像器官，而不是第二套心智。

如果答案偏向否定，它可能只是 agent 工程优化；如果答案偏向肯定，它才是在推进数字生命架构。
