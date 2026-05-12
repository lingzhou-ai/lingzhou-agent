# Schema 演化策略

> lingzhou 的数据库结构随系统成长而演化，不需要手动 migration。

---

## 1. 核心原则

**永不手动迁移，永不破坏旧数据。**

lingzhou 采用**启动时自动对齐**策略：每次进程启动，`_migrate()` 检查当前 schema 与期望 schema 的差异，自动 `ALTER TABLE ADD COLUMN`。

---

## 2. 两种演化策略

### 策略 A：`ALTER TABLE ADD COLUMN`（新增可选字段）

适用于：字段类型已知、只会新增、永不 DROP 的功能扩展。

```python
# memory/semantic.py — SemanticMemory._migrate()（Hermes _reconcile_columns 模式）
def _migrate(self) -> None:
    existing = {row[1] for row in self._conn.execute("PRAGMA table_info(nodes)")}
    if "embedding" not in existing:
        self._conn.execute("ALTER TABLE nodes ADD COLUMN embedding TEXT")
        self._conn.commit()
```

**来源**：Hermes 的 `_reconcile_columns` 模式。  
**lingzhou 已实现**：`memory/semantic.py._migrate()` 中使用此模式向 `nodes` 表追加 `embedding` 列（向量混合检索扩展）。

---

### 策略 B：JSON-first `data` 列（动态扩展主存储）

适用于：任务/事件等主体字段随系统演化动态增减，不希望频繁迁移 schema。

```sql
-- tasks 表以 data TEXT JSON 作为主存储，取代多列方案
CREATE TABLE tasks (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending',
    priority   REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    data       TEXT NOT NULL DEFAULT '{}'   -- ← JSON blob，存所有动态字段
);
```

`task_store._migrate()` 在启动时检测旧版列式 schema（无 `data` 列）→ 执行 DROP+REBUILD+backfill，一次性迁移到 JSON-first 方案，之后再无需 schema 变更。

**适用场景**：
- 任务附属字段（`next_step`, `source`, `task_id`, `context` 等）
- 失败记录（`error`, `tool_id`, `task_id`）
- 实验性字段（正式化后仍保留在 JSON 内，无需 ALTER TABLE）

---

## 3. 当前表结构

### tasks
```sql
CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    goal        TEXT DEFAULT '',
    priority    INTEGER DEFAULT 5,
    status      TEXT DEFAULT 'pending',
    source      TEXT DEFAULT 'loop',      -- _reconcile_columns 自动添加
    next_step   TEXT DEFAULT '',          -- _reconcile_columns 自动添加
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### failures
```sql
CREATE TABLE failures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    summary     TEXT DEFAULT '',
    context     TEXT DEFAULT '',
    task_id     TEXT,                     -- _reconcile_columns 自动添加
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### facts
```sql
CREATE TABLE facts (
    key         TEXT PRIMARY KEY,
    value       TEXT DEFAULT '',
    scope       TEXT DEFAULT 'global',
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. 演化流程示意

```
v0.1 初始建表：tasks(id, title, status)
  ↓
v0.2 加 goal 字段：_migrate() 检测到缺失 → ALTER TABLE ADD COLUMN goal TEXT DEFAULT ''
  ↓
v0.3 加 source/next_step：同上，自动添加
  ↓
v1.0 加 meta blob：一次性 ALTER TABLE，之后所有动态扩展用 meta
```

每次启动，`_migrate()` 都会运行，幂等，无副作用（字段已存在就跳过）。

---

## 5. 不该做的事

| 做法 | 为什么不对 |
|---|---|
| 手动写 `migration_v2.sql` | 文件多了就会漏跑，顺序难维护 |
| 删表重建 | 破坏历史数据 |
| 在进程中途修改 schema | 并发问题，WAL 模式下危险 |
| 在 facts 里存大量结构化数据 | facts 是 KV，复杂结构应建独立表 |

---

## 6. WAL 模式

lingzhou 使用 SQLite 的 WAL（Write-Ahead Logging）模式：

```python
await db.execute("PRAGMA journal_mode=WAL")
```

**好处**：
- 读写并发：loop 和 interact 可以同时访问 DB（一写多读）
- 崩溃恢复：WAL 日志确保未提交事务可回滚
- 性能：写操作不阻塞读

**注意**：WAL 会产生 `-wal` 和 `-shm` 附属文件，这是正常的，不要删除。

---

## 7. 未来演化预留

| 待新增字段/表 | 建议方式 | 原因 |
|---|---|---|
| `tasks.meta` TEXT | 一次性 ALTER + 策略 B | 扩展性需求 |
| `sessions` 表 | 新建表 + `_migrate()` 添加 | 未来 interact 历史 |
| `nodes` 表（语义记忆 SQLite 化） | 新建表 | 当前 nodes/*.json 的 SQL 迁移 |
| `events` 表（events.jsonl 替代） | 新建表 + FTS5 虚拟表 | 解决 O(n) 扫描问题 |

---

## 8. 设计原则

1. **启动时自动对齐**——不要依赖用户手动运行迁移脚本
2. **幂等**——`_migrate()` 可以安全地重复运行 N 次
3. **向后兼容**——ADD COLUMN 只加，不改，不删
4. **meta blob 是逃生舱**——字段不确定时先用 meta，确定后再提升为独立列
5. **WAL 是标配**——多进程访问必须开 WAL
