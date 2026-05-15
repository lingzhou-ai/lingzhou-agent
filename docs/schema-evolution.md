# Schema 演化策略

**更新日期：** 2026-05-15

> lingzhou 当前采用 **JSON-first + 启动时自动迁移**。目标不是“设计完美 schema”，而是：**能稳、能演进、能少改历史数据。**

---

## 1. 当前核心原则

1. **启动时自动迁移**
2. **优先 JSON-first，不频繁 ALTER**
3. **只做向前兼容，不做破坏性迁移**
4. **SQLite WAL 是基础设施默认值**

---

## 2. 当前真实表结构

### tasks

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'pending',
    priority   TEXT    NOT NULL DEFAULT 'normal',
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    data       TEXT    NOT NULL DEFAULT '{}'
);
```

`data` 中承载：
- goal
- source
- next_step
- chain_id
- parent_task_id
- current_step
- wait_kind / wait_key
- state_json / wait_json / result_json
- async_job_id
- extras...

### failures

```sql
CREATE TABLE IF NOT EXISTS failures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,
    dismissed  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    data       TEXT    NOT NULL DEFAULT '{}'
);
```

### facts

```sql
CREATE TABLE IF NOT EXISTS facts (
    key        TEXT PRIMARY KEY,
    value      TEXT    NOT NULL DEFAULT '',
    scope      TEXT    NOT NULL DEFAULT 'general',
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

### signals

```sql
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    run_at      TEXT    NOT NULL,
    repeat_secs INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'pending',
    payload     TEXT    NOT NULL DEFAULT '{}',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

### chat_messages

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    session_id TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'pending',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

---

## 3. 当前迁移策略

### 3.1 旧列式 schema → JSON-first

`task_store._migrate()` 当前已经支持：
- 读取旧 tasks/failures 列式数据
- DROP 旧表
- 按 JSON-first 重建
- 回填旧数据

这意味着：

> lingzhou 的主状态表已经从“频繁补列”转向“稳定主列 + data JSON 扩展”。

### 3.2 仍然保留幂等索引补齐

当前会自动补齐索引：
- `idx_tasks_status`
- `idx_tasks_title`
- `idx_failures_active`
- `idx_failures_kind`
- `idx_signals_pending`
- `idx_chat_pending`

---

## 4. 为什么当前方案是对的

对于 lingzhou 这种快速演化系统，频繁 `ALTER TABLE ADD COLUMN` 不是最优解。  
因为：
- task 附属字段会不停变化
- run/meta reflection 等结构还在探索
- 过早固化列会制造未来迁移负担

所以当前对 `tasks/failures` 采用 JSON-first 是正确的。

---

## 5. 最佳下一步（无历史包袱）

在当前 schema 上，最应该新增的不是更多 task 列，而是**新表**：

### 5.1 runs 表（执行单元）

```sql
CREATE TABLE runs (
    id           TEXT PRIMARY KEY,
    task_id      INTEGER NOT NULL,
    run_type     TEXT NOT NULL,
    worker_type  TEXT NOT NULL,
    model_tier   TEXT NOT NULL DEFAULT 'reasoner',
    status       TEXT NOT NULL DEFAULT 'pending',
    progress     REAL NOT NULL DEFAULT 0,
    input_json   TEXT NOT NULL DEFAULT '{}',
    output_json  TEXT NOT NULL DEFAULT '{}',
    log_text     TEXT NOT NULL DEFAULT '',
    error_text   TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_runs_task_status ON runs(task_id, status);
```

### 5.2 meta_reflections 表（双环学习记录）

```sql
CREATE TABLE meta_reflections (
    id                 TEXT PRIMARY KEY,
    target_kind        TEXT NOT NULL,
    trigger            TEXT NOT NULL,
    loop_level         TEXT NOT NULL,
    diagnosis          TEXT NOT NULL,
    proposal           TEXT NOT NULL,
    verification_plan  TEXT NOT NULL DEFAULT '',
    decision           TEXT NOT NULL DEFAULT 'defer',
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_meta_reflections_loop ON meta_reflections(loop_level, created_at);
```

---

## 6. 为什么是“新表”而不是继续塞进 tasks.data

因为：

- **Task 是目标单元**
- **Run 是执行单元**
- **MetaReflection 是学习单元**

它们不是同一层语义。

如果全部塞进 `tasks.data`：
- 查询复杂
- 状态机混乱
- 并行 run 很难表达
- 学习记录不独立

所以：

> `tasks` 继续 JSON-first，`runs` 和 `meta_reflections` 作为新表单独落地，是当前最优解。

---

## 7. WAL 与并发

当前已经启用：

```python
PRAGMA journal_mode=WAL
PRAGMA foreign_keys=ON
```

这为未来的：
- 主循环
- worker 执行器
- chat 交互
- run 状态轮询

提供了基本并发读写能力。

---

## 8. 设计原则

1. **状态主表继续 JSON-first**
2. **新语义层级用新表，不把所有东西塞进 tasks.data**
3. **迁移必须自动、幂等、可重复运行**
4. **先增加 runs / meta_reflections，再讨论更复杂 schema**
