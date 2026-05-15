# lingzhou 系统蓝图

**更新日期：** 2026-05-15  
**状态：** 当前实现 + 目标架构（去历史包袱版）

---

## 1. 定位

lingzhou 是一个**数字生命种子**。  
它不应该优先做成“多通道聊天壳”，也不应该优先做成“工具大全”。

它应该先把三件事做到最对：

1. **能持续地理解并推进目标**
2. **能把复杂执行异步丢出去，不阻塞认知主环**
3. **能从失败中学习：既修手段，也质疑前提**

因此，lingzhou 的正确方向不是“先做更多入口”，而是：

> **认知控制面 + 运行平面 + 双环学习器**

---

## 2. 核心设计立场

### 2.1 Task 是目标单元，不是执行单元
Task 回答：**要完成什么**。

它应该承载：
- title
- goal
- priority
- chain_id
- parent_task_id
- current_step
- next_step
- status

Task 不应该直接承担所有执行细节。

### 2.2 Run 是执行单元
Run 回答：**这一次具体怎么执行**。

Run 应该承载：
- 属于哪个 task
- 由什么 worker 执行
- 输入是什么
- 当前状态是什么
- 进度如何
- 日志/结果/错误是什么

一个 Task 可以对应多个 Run。

### 2.3 Worker 是执行器，不是人格化子代理
Worker 回答：**由谁执行**。

当前阶段不应该先做“会话人格化子代理系统”，而应该先做可观测、可取消、可并行的执行器：
- exec worker
- tool-chain worker
- llm worker
- multimodal worker

### 2.4 主环是控制面，不是万能执行器
认知主环（CognitionLoop）的职责是：
- 感知
- 情绪更新
- 价值观约束
- 判断与计划
- 创建 Run
- 监控 Run
- 根据 Run 结果调整 Task
- 学习与进化

主环不应该亲自执行所有复杂动作。

### 2.5 双环学习必须独立出来
进化不等于双环学习。

- **单环学习**：怎么把这次事情做对（修工具/修 prompt/修参数）
- **双环学习**：我判断这件事的方法是否本身有问题（质疑 task 分解、tier 分类、阈值、技能、防线）

lingzhou 的目标是同时具备二者。

---

## 3. 最佳架构（无历史包袱版）

```
┌────────────────────────────────────────────────────────────────┐
│                 Cognitive Control Plane                        │
│                                                                │
│  Perception → Emotion → Ethos → Judgment → Plan → Monitor     │
│                                                                │
│  输出：Task 调整 / Run 创建 / 用户回复 / 学习触发              │
└──────────────────────┬─────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────────┐
│                      Execution Plane                           │
│                                                                │
│  Run / Job lifecycle                                           │
│    pending → running → succeeded / failed / cancelled          │
│                                                                │
│  Workers:                                                      │
│    • exec-worker                                               │
│    • tool-chain-worker                                         │
│    • llm-worker                                                │
│    • multimodal-worker                                         │
└──────────────────────┬─────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────────┐
│                     Meta-Learning Plane                        │
│                                                                │
│  Ring 1: Single-loop learning                                  │
│    修工具 / 修 prompt / 修参数 / 修流程                         │
│                                                                │
│  Ring 2: Double-loop learning                                  │
│    质疑 tier 分类 / 任务拆分 / 阈值 / skill 防线 / 判断框架     │
│                                                                │
│  输出：Fix / Rule Revision / Threshold Revision / Rollback     │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. 当前实现 vs 目标架构

### 4.1 当前已经具备

| 组件 | 状态 | 说明 |
|------|------|------|
| 认知主环 | ✅ | `core/loop.py` 完整执行感知→判断→执行→记忆 |
| 情绪系统 | ✅ | OCC + Core Affect + Regulation |
| Ethos | ✅ | 5 维度 EMA + hard_axioms |
| Judgment | ✅ | reader/reasoner/repair 路由 |
| TaskStore | ✅ | JSON-first SQLite，支持 chain/wait/result 等扩展字段 |
| file/edit/exec/process/schedule | ✅ | 核心工具链已可用 |
| 自进化 | ✅ | importlib.reload 热替换 |

### 4.2 当前还缺

| 组件 | 状态 | 说明 |
|------|------|------|
| Run 抽象 | ❌ | 现在只有 task，没有正式的执行单元 |
| Worker 层 | ❌ | 当前复杂动作仍由主环直接触发 |
| 自主循环内环 | ⚠️ | 仅 chat 模式有连续工具调用 |
| 双环学习器 | ❌ | evolution 目前主要还是单环纠错 |
| 进化验证/回滚 | ❌ | 改动后缺少效果验证与自动回滚 |
| 视觉/多模态 | ❌ | 感知层尚不完整 |

---

## 5. 核心实体模型（最佳版本）

### 5.1 Task（目标单元）

```python
Task:
  id
  title
  goal
  priority
  status
  chain_id
  parent_task_id
  current_step
  next_step
  source
  state_json
  result_json
```

### 5.2 Run（执行单元）

```python
Run:
  id
  task_id
  run_type          # exec / tool_chain / llm / multimodal
  worker_type       # exec-worker / llm-worker / ...
  model_tier        # reader / reasoner / repair
  status            # pending / running / succeeded / failed / cancelled
  progress
  input_json
  output_json
  log_text
  error_text
  started_at
  completed_at
```

### 5.3 MetaReflection（双环学习记录）

```python
MetaReflection:
  id
  target_kind       # tool / prompt / threshold / routing / task_split / skill
  trigger           # failure_pattern / success_pattern / drift / contradiction
  loop_level        # single / double
  diagnosis
  proposal
  verification_plan
  decision          # apply / defer / rollback
  created_at
```

---

## 6. 主循环应该怎么工作（最佳版本）

### Tick 流程

1. **感知**：读取 active task、run 状态变化、外部消息、调度信号、工作记忆压力
2. **情绪更新**：从预测误差/失败数/控制感推导 EmotionState
3. **价值观约束**：Ethos + hard_axioms 限制策略空间
4. **判断**：决定
   - 继续当前 task
   - 创建新 task
   - 创建 run
   - 调整已有 run
   - 回复用户
   - 触发单环/双环学习
5. **执行调度**：
   - 简单读操作可在环内直接做
   - 复杂执行通过 Run 丢给 Worker
6. **结果整合**：把 run 结果写回 task/result_json，必要时生成 reflection
7. **学习**：
   - 工具/参数问题 → 单环
   - 规则/拆分/分类问题 → 双环

---

## 7. 双环学习的正确边界

### 单环（Single-loop）
问：**怎么把这次做对？**
- 工具代码有 bug 吗？
- prompt 解析失败了吗？
- timeout/参数/路径要调整吗？
- retry/backoff 要修改吗？

### 双环（Double-loop）
问：**我做事的前提是不是错了？**
- 为什么这个 task 总被拆坏？
- 为什么这个问题总被分到 reader tier？
- 为什么这条 skill 总在误导判断？
- 为什么这个阈值老让任务过早 wait？

### 当前阶段不做的
- 三环（价值观/存在意义层面的系统级再定义）
- 多通道优先化
- 重型 session/agent 社交系统
- 复杂沙箱系统

这些都不是当下最对的事情。

---

## 8. 多模态与视觉的地位

视觉/多模态不是锦上添花，而是**感知层补全**。

如果 lingzhou 只能处理文本，它的感知层就是残缺的。  
因此视觉能力优先级应高于：
- 多通道
- 沙箱
- 复杂插件系统

最小正确形态：
- `image.analyze`
- 单图/多图输入
- 结构化返回（caption / OCR / objects / summary）
- 作为主环可创建的 `multimodal` run 类型

---

## 9. 当前阶段的优先级原则

### 先做
1. 视觉/多模态
2. 自主循环内环（不只 chat 模式）
3. Task-level model routing
4. Run 抽象
5. Worker 执行器
6. Run 状态回流 task
7. 双环学习器
8. 进化验证 + 回滚

### 后做
9. 多通道
10. 复杂沙箱
11. 重型插件生态
12. 三环/存在主义层面演化

---

## 10. 设计准则

1. **不要引入比问题更重的抽象**
2. **Task 是目标，Run 是执行，Worker 是执行器**
3. **主环优先做判断与调度，不亲自背所有执行**
4. **双环学习必须单独建模，不能混在“自进化”里偷换概念**
5. **多模态优先于多通道**
6. **只做当前最对的事情，不为未来幻想加结构**

---

## 11. 文档关系

- `ROADMAP-2026.5.15.md`：当前实施路线图
- `chat-and-task.md`：Task / Run / Chat 分工
- `judgment-layer.md`：判断层当前机制与目标升级方向
- `memory-architecture.md`：四层记忆当前实现与 Run/MetaReflection 扩展点
- `schema-evolution.md`：SQLite schema 当前状态与未来增加 runs/meta_reflections 的策略
