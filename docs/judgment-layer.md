# 判断层（Judgment Layer）

**更新日期：** 2026-05-16

> 判断层是 lingzhou 的**认知控制核心**。它负责整合信息、决定下一步、并把复杂执行交给执行面。

---

## 1. 职责

当前判断层做三件事：

1. **组装判断上下文（bundle）**
2. **选择模型 tier / provider 并调用 LLM**
3. **输出 `JudgmentOutput` 驱动后续执行**

长期目标上，它还应承担：

4. **决定是否创建 run**（而不是所有动作都由主环直接执行）
5. **决定问题属于单环还是双环**（交给 MetaReflection）

## 2.5. 工具元数据

工具通过 `ToolManifest` 自声明属性，减少硬编码：

```python
@tool(ToolManifest(
    name="file.read",
    progress_category="info",   # mutation | info
    prefer_tier="reader",        # reader | reasoner
))
```

- `progress_category`: 声明工具是变更类(mutation)还是信息类(info)，供进展判断使用
- `prefer_tier`: 声明工具推荐在哪个 tier 执行，供路由决策使用
新增工具只需加这两行声明，无需修改 loop.py / judgment.py

---

## 2. 当前输入

`_assemble_context()` 当前已经整合：

- active task
- **self model** (uptime, token usage, cost estimate, billing mode)
- **team view** (reader/reasoner/repair architecture with delegation guide)
- percept / perception replay
- emotion
- ethos
- judgment signals
- hard boundaries
- working memory
- episodic memory
- semantic memory
- failures
- skills
- tools
- user_message
- current time

这使 Judgment 已经具备很强的“认知控制面”基础。

---

## 3. 当前输出

```python
@dataclass
class JudgmentOutput:
    decision: str              # act | pause | wait
    chosen_action_id: str      # 工具名
    params: dict[str, Any]
    rationale: str
    reflection: str
    reply_to_user: str
    next_step: str
    model_strategy: dict[str, Any]
```

### `model_strategy` 当前已支持

- `next_phase_tier`
- `next_idle_gap_secs`
- `routing_overrides`
- `thinking_override`

这是现有判断层很强的一点：

> LLM 不只是“选工具”，还可以跨 tick 调整自己的推理姿态。

---

## 4. 当前 tier 路由机制

目前采用：

- `reader`：低成本读取/枚举类工具
- `reasoner`：写入/复杂推理/高风险动作
- `repair`：修复层

### 当前做法

当前 tier 主要按**工具类型**推断：

```python
if current_action in _REASONER_TOOLS:
    return "reasoner"
if current_action in _READER_TOOLS:
    return "reader"
```

### 当前问题

这在“单步工具调用”上有效，但在“长任务”上会出现问题：

- 同一个 task 内不同步骤频繁切换模型
- reasoning 风格不稳定
- 上下文连续性被打断

### 正确方向

> **从 tool-level routing 升级到 task-level routing。**

即：
- task 默认有一个 `model_tier`
- 某些 step 再做 override
- 不再每一步都从工具类型重新猜一次

---

## 5. 最佳目标：Judgment 负责创建 Run，而不是亲自背所有执行

当前流程更像：

```
JudgmentOutput → ExecutionLayer.dispatch() → 工具直接执行
```

更好的目标应该是：

```
JudgmentOutput
  ├─ 简单只读动作 → 直接执行
  ├─ 快速回复 → 直接生成 reply
  └─ 复杂执行 → 创建 Run 交给 Worker
```

### 也就是说，Judgment 未来要多一个决策分叉：

- **direct action**
- **spawn run**
- **meta reflection trigger**

---

## 6. 与双环学习的关系

当前 Judgment 只是“做决定”。

但长期上，Judgment 不应该独自承担“质疑自己”的工作。  
真正的双环应该拆出去给 `MetaReflection`：

### Ring 1（单环）
- 这次工具为什么失败？
- 参数/超时/路径要怎么改？

### Ring 2（双环）
- 为什么这个问题总被分到 reader？
- 为什么这个 task 总被拆坏？
- 为什么这条 skill 总在误导判断？
- 为什么这个阈值会把任务过早推入 wait？

因此：

> Judgment 负责“决策”，MetaReflection 负责“反思决策框架”。

---

## 7. 当前状态评估

| 维度 | 评价 |
|------|------|
| 上下文整合能力 | 很强 |
| tier 路由能力 | 可用但粒度不对 |
| 跨 tick 姿态调控 | 强 |
| 直接决策能力 | 正常 |
| run 调度能力 | 尚未形成 |
| 双环质疑能力 | 尚未形成 |

---

## 8. 后续演进方向

### 近期（P0/P1）
1. 引入 task-level routing
2. Judgment 能选择“创建 run”而不是只选工具
3. 增加 multimodal run 的判断能力

### 中期（P1/P2）
4. Judgment 输出可触发 MetaReflection
5. 区分 direct action / run creation / meta reflection
6. 与运行结果回流打通

---

## 9. 设计原则

1. **Judgment 是控制面，不是执行器**
2. **task-level routing 优先于 tool-level routing**
3. **复杂执行要走 run，而不是永远在主环内串行推进**
4. **双环学习不应混在 Judgment 里偷做，而应单独建模**
