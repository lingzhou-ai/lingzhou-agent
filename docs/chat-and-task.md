# Chat、Task、Run 的职责分工

**更新日期：** 2026-05-15

> 当前原则：**chat 是入口，task 是目标，run 是执行。**

---

## 1. 简明结论

如果不背历史包袱，lingzhou 应该这样理解：

- **chat**：外部输入入口（谁在说、说了什么）
- **task**：持久目标单元（要完成什么）
- **run**：一次具体执行尝试（这次怎么执行）

所以：

> **chat 不是任务本身，task 也不是执行本身。**

chat 可以触发 task，task 可以生成 run，run 的结果再反向更新 task。

---

## 2. 三者的正确边界

| 概念 | 回答的问题 | 生命周期 | 当前状态 |
|------|-----------|----------|----------|
| **chat** | 谁在输入？当前要回复什么？ | 会话级 | ✅ 已有 |
| **task** | 要达成什么目标？ | 目标级 | ✅ 已有 |
| **run** | 这一次具体怎么执行？ | 执行级 | ❌ 目标新增 |

### chat
承担：
- 接收用户输入
- 提供回复出口
- 形成对话上下文

### task
承担：
- 目标表达
- 状态推进
- next_step 管理
- chain / parent-child 关系

### run
承担：
- 执行动作
- 状态（pending/running/succeeded/failed/cancelled）
- 进度
- 日志
- 结果
- 错误

---

## 3. 为什么 task 不应该继续兼任执行单元

当前 lingzhou 的 task 已经承担了很多职责：
- title / goal / priority
- status / next_step
- chain_id / parent_task_id
- wait_kind / wait_key
- state_json / result_json

这已经足够表达“目标推进”。

如果再把以下东西也塞进 task：
- 执行命令
- 进程 pid
- 模型 tier
- 重试次数
- 执行日志
- worker 类型

那么 task 会膨胀成“万能状态袋”，导致：
- 目标层与执行层耦合
- 状态机难维护
- 并行执行难表达
- 一个 task 多次执行尝试不好建模

因此最合理的方式是：

> **task 管目标，run 管执行。**

---

## 4. 最佳工作流

```
用户输入 / 调度信号 / 心跳
        │
        ▼
      chat
        │
        ▼
  认知主环判断
        │
        ├── 直接回复用户
        ├── 创建/推进 task
        └── 为 task 创建 run
                │
                ▼
             worker 执行
                │
                ▼
           run 结果回流
                │
                ▼
        task 状态更新 / 用户回复 / 记忆结晶
```

---

## 5. chat 的正确定位

chat 依然应该保留“持续会话上下文”的能力，但它不该再被描述为“所有工作的原子单位”。

更准确地说：

- chat 是**外部互动通道**
- chat 可以绑定一个长期 task（例如 `source="chat:alice"`）
- 但 chat 本身不替代 task，更不替代 run

也就是说：

### chat task 依然成立，但它只是 task 的一种来源（source）
例如：
- `source="chat:alice"`
- `source="scheduler"`
- `source="curiosity"`
- `source="external"`

这比“chat 就是 task 本体”更清楚。

---

## 6. run 应该长什么样

```python
Run:
  id
  task_id
  run_type         # exec / tool_chain / llm / multimodal
  worker_type      # exec-worker / llm-worker / ...
  model_tier       # reader / reasoner / repair
  status           # pending / running / succeeded / failed / cancelled
  progress
  input_json
  output_json
  log_text
  error_text
  started_at
  completed_at
```

### 设计收益

1. 一个 task 可以有多个 run（重试 / 并行子执行）
2. 主环可以监控 run 而不阻塞
3. task 保持干净，仍专注目标推进
4. 后续加 worker 并行不需要再重构 task 语义

---

## 7. 当前实现与目标差距

### 当前已有
- chat 消息队列：`chat_messages`
- task 持久化：`tasks`
- signals：`signals`
- task.wait / task.resume / async_job_id 预留位

### 当前缺少
- runs 表
- run 生命周期管理
- worker 执行器
- run 结果事件回流

---

## 8. 最终原则

1. **chat 是入口，不是万能对象**
2. **task 是目标，不是执行器**
3. **run 是执行，不是目标**
4. **worker 是执行器，不是人格化子代理**
5. **主环负责判断和调度，不负责背所有执行细节**
