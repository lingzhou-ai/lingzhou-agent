# 记忆架构

**更新日期：** 2026-05-15

> lingzhou 当前已经具备四层记忆体系；下一阶段要解决的是如何让它服务 Task / Run / MetaReflection，而不是只停留在“存得下”。

---

## 1. 四层记忆概览

```
┌─────────────────────────────────────────────┐
│ Working Memory                              │
│ 有界优先缓存 / pressure 驱动               │
├─────────────────────────────────────────────┤
│ Episodic Memory                             │
│ task 叙事 + events 事件流                   │
├─────────────────────────────────────────────┤
│ Semantic Memory                             │
│ nodes + FTS5 + activation 衰减 + 向量混合   │
├─────────────────────────────────────────────┤
│ SQL State                                   │
│ tasks / failures / facts / signals / chat   │
└─────────────────────────────────────────────┘
```

---

## 2. 当前真实实现

### 2.1 Working Memory

位置：`memory/working.py`

当前特征：
- `WorkingMemory(capacity=cfg.memory.working_capacity, token_budget=cfg.effective_wm_token_budget())`
- pressure = 当前使用量 / 容量
- 用于：
  - 结果注入
  - 合成 reflection 注入
  - 心跳/调度信号注入
  - 行为防线提示

### 2.2 Episodic Memory

位置：`memory/episodic.py`

当前特征：
- `record(role, content, task_id, ...)`
- `record_event(event_type, data)`
- `load_for_context(task_id, max_chars)`
- perception / emotion 事件可持久化并回放
- task 叙事流是当前主上下文之一

### 2.3 Semantic Memory

位置：`memory/semantic.py`

当前特征：
- SQLite `nodes` 表 + FTS5 虚拟表
- `activation` 衰减（Ebbinghaus）
- `retrieve_multi_anchor()` 多锚点检索
- 已预留/接入 `embed_fn`，支持向量混合检索
- 当前 loop 会在 `embedding_model` 配置存在时注入 embed_fn

这意味着：

> lingzhou 当前已经不是“只有关键词检索”，而是 **FTS5 + activation + 可选向量混合**。

### 2.4 SQL State

位置：`memory/task_store.py`

当前表：
- `tasks`
- `failures`
- `facts`
- `signals`
- `chat_messages`

说明：
- 当前 schema 是 **JSON-first**，`tasks/failures` 的动态字段都放在 `data` JSON 中
- 已不是旧文档里那种多列式 schema

---

## 3. 四层分工（正确理解）

| 层 | 回答的问题 | 适合存什么 |
|----|-----------|-----------|
| Working Memory | 现在我最该看到什么？ | 当前轮结果、合成条目、信号、提示 |
| Episodic | 发生了什么？ | task 叙事、perception/emotion 事件 |
| Semantic | 我学到了什么？ | insight、event、task_summary、规则抽象 |
| SQL State | 当前真实状态是什么？ | task 状态、facts、signals、failures |

---

## 4. 当前缺口

### 4.1 还没有 Run 层记忆

当前 task 是目标层，但未来要引入 run 执行层。  
这意味着记忆系统也要能区分：

- `task narrative`：目标推进叙事
- `run logs`：一次执行尝试的日志和结果
- `meta reflection`：对失败模式的抽象诊断

### 4.2 结晶仍然偏“完成时刻”

当前已有：
- `reflection -> learned_insight`
- task 完成/失败时兜底 `task_summary`
- chat 周期性 `event` 结晶

但还缺：
- **长任务进行中的 progress crystal**
- **run 级执行结果结晶**
- **double-loop 反思沉淀**

---

## 5. 最佳方向：让记忆为 Task / Run / MetaReflection 服务

### 5.1 Task 级记忆
- task narrative（episodic）
- task_summary（semantic）
- task state/result（sql）

### 5.2 Run 级记忆（新增）
- run logs（sql 或 file）
- run result crystal（semantic）
- progress checkpoints（episodic event）

### 5.3 MetaReflection 级记忆（新增）
- failure pattern 抽象
- rule revision 提案
- threshold revision 提案
- rollback 决策记录

---

## 6. 推荐扩展

### 新增 kind
- `run_result`
- `progress_crystal`
- `meta_reflection`
- `rule_revision`

### 新增事件类型
- `run_started`
- `run_progress`
- `run_completed`
- `run_failed`
- `double_loop_reflection`

---

## 7. 当前状态评估

| 能力 | 状态 |
|------|------|
| WM 焦点控制 | ✅ |
| task 叙事 | ✅ |
| perception/emotion 回放 | ✅ |
| semantic insight 结晶 | ✅ |
| activation 衰减 | ✅ |
| FTS5 检索 | ✅ |
| 向量混合检索 | ✅ 已接入（配置驱动） |
| run 级记忆 | ❌ |
| double-loop 记忆 | ❌ |
| 运行中结晶 | ⚠️ 不完整 |

---

## 8. 设计原则

1. **记忆不只是“存”，还要支撑控制面决策**
2. **task / run / meta reflection 应分层沉淀，避免混成一锅**
3. **semantic 不应只存 insight，还要存 run 结果与规则修订**
4. **SQL 是真相，episodic 是叙事，semantic 是抽象**
