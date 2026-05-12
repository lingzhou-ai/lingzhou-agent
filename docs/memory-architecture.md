# 记忆架构

> lingzhou 实现了四层记忆体系，对应不同的遗忘速率和检索代价。

---

## 1. 四层记忆概览

```
┌─────────────────────────────────────────┐
│  Working Memory (WM)                    │  最快 — 有界优先级堆
│  容量上限 cfg.memory.wm_capacity         │  evict 最低优先级项
├─────────────────────────────────────────┤
│  Episodic Memory                        │  叙事流 — 不可变 append
│  task-{id}.md  events.jsonl            │  O(n) 扫描，未来 FTS5
├─────────────────────────────────────────┤
│  Semantic Memory                        │  知识节点 — 激活衰减
│  nodes/*.json                           │  ACT-R 多锚点检索
├─────────────────────────────────────────┤
│  Procedural / SQL State                 │  ACID 真相 — tasks/failures/facts
│  memory.db                             │  状态机，schema 自动演化
└─────────────────────────────────────────┘
```

---

## 2. Working Memory（工作记忆）

### 位置
`memory/working.py` → `WorkingMemory`

### 特征
- 有界优先级堆（`heapq`），容量来自 `cfg.memory.wm_capacity`
- 超容量时自动 evict 最低优先级项
- `pressure` 属性：`len / capacity` → [0, 1]，驱动感知层阈值调整
- 存储：`WMEntry(key, value, priority, source, added_at)`

### 用途
- 当前轮次的关键中间结果
- 判断层的 `wm_section` 注入
- 工具通过 `memory.add_wm(key, value, priority)` 写入

### 设计原则
**WM 是认知焦点，不是持久存储。**  
重要内容应显式写入 episodic / semantic / facts。

---

## 3. Episodic Memory（情节记忆）

### 位置
`memory/episodic.py` → `EpisodicMemory`

### 两种接口

#### 3.1 Markdown 叙事流（task-{id}.md）
```
~/.lingzhou/workspace/memory/task-42.md
---
[2026-05-09T12:00:00] assistant (tool_result) [valence=0.3]
工具 file.read 返回内容...
```
- 写入：`record(role, content, task_id, source_type, affect)`
- 读取：`load_for_context(task_id, max_chars)` → 末尾 N 字符注入判断层
- Tulving 4 要素绑定：时间戳 + 角色 + 情感 + 内容

#### 3.2 SQLite 结构化事件（events 表，JSONL 为降级备用）

```jsonl
// 主路径：SQLite events 表（优先）
INSERT INTO events(event_type, ts, data) VALUES (?, ?, ?)

// 降级备用：DB 不可用时 append 到 events.jsonl
{"event_type": "perception", "data": {...}, "ts": "..."}
```
- 写入：`record_event(event_type, data)` → 写 SQLite，降级时写 JSONL
- 读取：`list_events(event_type, limit)` → **O(log n) 索引扫描**（`ORDER BY id DESC LIMIT ?`）
- 轮转：写入后自动触发 `_rotate_events_db()`，每种 event_type 只保留最新 `max_events` 条

### 已知问题 & 演化路径

| 问题 | 当前状态 | 备注 |
|---|---|---|
| events.jsonl 无界增长 | 主路径已迁移 SQLite，JSONL 仅降级用 | ✅ 已解决 |
| list_events O(n) | O(log n) 索引扫描 | ✅ 已解决 |
| task-{id}.md 无大小限制 | load_for_context 末尾截断 | 待实现分段摘要 |

---

## 4. Semantic Memory（语义记忆）

### 位置
`memory/semantic.py` → `SemanticMemory`

### 存储格式
```json
// 内部存储：SQLite nodes 表（WAL 模式）
// + nodes/*.json 文件（向后兼容，sync_to_disk 写出）
{
  "id": "learned_insight_20260509_120000",
  "kind": "learned_insight",
  "title": "reflection 摘要",
  "body": "当工具连续失败 3 次时...",
  "tags": ["tool", "failure", "pattern"],
  "activation": 0.8,
  "valence": -0.2,
  "created_at": "2026-05-09T12:00:00"
}
```

### 检索算法（ACT-R 多锚点）
```python
def retrieve_multi_anchor(anchors, top_k, convergence_bonus):
    # FTS5 候选集预过滤（_fts5_ok 时启用，O(log n)）
    candidates = fts5_filter(query)  # 返回命中节点 ID
    # 对每个节点计算：
    score = keyword_overlap(node, anchors) * 0.7 + effective_activation(node, decay_lambda) * 0.3
    # 多锚点命中额外加 convergence_bonus
```

### 激活衰减（已实现）

**理论基础**：Ebbinghaus 遗忘曲线。检索时动态计算有效激活值，不写回 DB（避免频繁 IO）。

```python
# memory/semantic.py
def effective_activation(node: MemoryNode, decay_lambda: float) -> float:
    if decay_lambda <= 0:
        return node.activation
    days = (datetime.now(UTC) - node.created_at).days
    return node.activation * math.exp(-decay_lambda * days)
```

`decay_lambda` 从 `cfg.memory.semantic_decay_lambda` 传入，默认 0.1（每天衰减约 10%）。

### reflection 写回（已实现）

`core/loop.py` step 7/7b 在每次判断后直接写入语义记忆：

```python
# core/loop.py
if action.reflection:
    semantic.upsert(MemoryNode(
        id=f"insight_{md5(action.reflection)[:10]}",
        kind="learned_insight",
        body=action.reflection,
        activation=0.9,
        valence=emotion.valence,
        tags=["reflection", task.title[:20]],
    ))

# 每 chat_crystallize_every 轮触发事件结晶（kind="event" 节点）
if turns % crystallize_every == 0:
    semantic.upsert(MemoryNode(id=f"event-task{task.id}-{date}", kind="event", ...))
```

`store_reflection(kind, insight, valence)` 方法也存在，是 `upsert(MemoryNode(kind="learned_insight", ...))` 的便捷封装。

---

## 5. SQL State（过程记忆 / 状态机）

### 位置
`memory/task_store.py` → `TaskStore`

### 三张表

| 表 | 用途 | 特点 |
|---|---|---|
| `tasks` | 任务状态机 | ACID，`_migrate()` 自动 ADD COLUMN |
| `failures` | 工具失败记录 | `task_id` 边界过滤，`dismiss_failure` 豁免 |
| `facts` | KV 存储（soul / 配置 / 计数） | `scope` 字段分类，`get_fact / set_fact` |

### facts 的典型键

```
soul:hard_axioms        → 不可违反的原则列表（JSON）
soul:ethos_baseline     → EthosValues 基线（JSON，EMA 演化）
soul:name               → "灵舟"
loop:cycle_count        → 当前总循环计数
```

### 自动 schema 演化（_reconcile_columns 模式）

```python
async def _migrate(self):
    existing = {row[1] for row in await db.execute("PRAGMA table_info(tasks)")}
    for col, ddl in EXPECTED_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE tasks ADD COLUMN {ddl}")
```

新增字段永远向后兼容，旧数据自动获得 DEFAULT 值。

---

## 6. 四层交互图

```
loop.py (每 tick)
  │
  ├─ perception.sense(wm) → 读 WM pressure → 写 episodic event
  │
  ├─ judgment.decide(...)
  │    ├─ wm_section       ← WorkingMemory.snapshot()
  │    ├─ episodic_section ← EpisodicMemory.load_for_context(task_id)
  │    ├─ memories_section ← SemanticMemory.retrieve_multi_anchor(...)
  │    └─ task/failures    ← TaskStore.get_active() / list_failures()
  │
  └─ execution.dispatch(action)
       ├─ memory.add_wm    → WM
       ├─ memory.add_semantic → Semantic
       ├─ memory.set_fact  → SQL facts
       └─ task.*           → SQL tasks
```

---

## 7. 设计规则摘要

1. **WM 是焦点，不是持久化**——重要结论应写 semantic/facts
2. **Episodic 不可变**——永远 append，叙事连续性来自 task_id 锚定
3. **Semantic 需要衰减**——没有遗忘的记忆会导致旧知识干扰检索
4. **SQL 是真相**——任务状态、Soul 基线、失败记录都在 DB
5. **四层分工不是冗余**——每层解决不同时间尺度的记忆问题
