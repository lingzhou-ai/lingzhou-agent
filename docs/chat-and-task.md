# Chat 与 Task 的职责分工

> 核心设计原则：**chat 是门，也是房间。task 是所有工作的原子单位。**

---

## 1. 简明结论

`chat` 是 lingzhou 与外部世界的唯一对话通道。它同时承担两个角色：

- **门**：`lingzhou chat --name alice` 启动一条对话通道，loop 可以感知到有人在说话
- **房间**：loop 为这条通道创建一个长期存活的 chat task（`source="chat:alice"`），对话历史就是任务叙事，跨重启可续接

门和房间不再分离。启动一个 chat = 建立一个持久的对话任务。

---

## 2. Chat 的完整生命周期

```
lingzhou chat --name alice
  │
  ├── 首次启动: 在 tasks 表创建 chat task
  │     title  = "chat:alice"
  │     goal   = "持续响应 alice 的对话需求"
  │     source = "chat:alice"
  │     status = in_progress  ← 不会自动完成，直到用户关闭
  │
  ├── 用户输入 "帮我看一下这段代码"
  │     → 追加到 task-N.md: [user] 帮我看一下这段代码
  │     → 唤醒 loop（更新 chat task next_step）
  │
  ├── loop 下一个 tick 拾取该 chat task
  │     → load_for_context("N") 读取完整对话历史
  │     → LLM 生成回复
  │     → 追加到 task-N.md: [assistant] 这段代码...
  │     → 写入 chat_replies WHERE chat_id="alice"
  │
  ├── chat 进程轮询 chat_replies，打印回复，标记 consumed
  │
  └── 用户 Ctrl+C 退出 chat 进程
        → task 保持 in_progress（下次 chat --name alice 续接）
        → 若用户运行 lingzhou chat --name alice --close，才标记 done
```

---

## 3. 多 chat 并行

loop 是全局认知主体，不做 chat 间的上下文隔离——这是设计意图，不是缺陷：

| 场景 | 行为 |
|---|---|
| alice 和 小张同时发消息 | 两个 chat task 竞争 loop，按优先级/时间排队 |
| loop 处理 alice 的消息时 | LLM 上下文以 alice 的 chat task 叙事为主轴，其他 chat 不干扰 |
| 回复路由 | `chat_replies` 按 `chat_id` 过滤，各自只收到自己的回复 |
| 信息量暴增 | `load_for_context` 的 `max_chars` 末尾截取自动控量，与普通 task 完全一致 |

---

## 4. Chat Task vs 普通 Task

| 属性 | 普通 task | chat task |
|---|---|---|
| 生命周期 | 有限，完成后 done | 长期，用户关闭才 done |
| goal | 具体目标 | "持续响应 X 的对话需求" |
| source | `external` / `gateway:webhook` 等 | `chat:<name>` |
| 叙事内容 | 推进记录 + 工具结果 | `[user]` / `[assistant]` 对话流 |
| 优先级 | 任意 | 默认 `high`，有消息时 bump |

---

## 5. 上下文压缩机制（输入侧）

lingzhou 的压缩重点不是"限制最终回复长度"，而是"控制哪些内容进入输入上下文"。

对比其他系统：
- Hermes：以进程为边界，把 SOUL / HERMES / workspace 约定注入启动上下文，chat 历史全量存 messages 表
- OpenClaw：以 AGENTS / MEMORY / chat transcript 做分层注入，靠 startup 压缩与重注入维持局部上下文
- lingzhou：以 DB facts / task / episodic / semantic 分层注入，靠任务叙事和记忆摘要维持跨 chat 连续性

当前 lingzhou 的输入侧按"层级 + 预算"来理解：

| 层级 | 进入位置 | 作用 |
|---|---|---|
| 启动引导 | `BOOTSTRAP.md` / `IDENTITY.md` | 冷启动协议、身份锚点 |
| 永久在线索引 | `facts["soul:*"]` | Soul 真相源、hard axioms |
| 任务上下文 | `task_section` / `next_step` | 任务主轴 |
| 叙事上下文 | `episodic_section` | 当前 chat/task 叙事流 |
| 语义记忆 | `memories_section` | 相关长期记忆召回 |
| 工作记忆 | `wm_section` | 当前轮高优先级结果 |
| 技能/护栏 | `skills_section` / `signals_section` | 认知防线与姿态 |

---

## 6. 实现映射

```python
# chat 启动时——创建或恢复 chat task
task = await task_store.get_chat_task("alice")
if task is None:
    task = await task_store.add_task(
        title="chat:alice",
        goal="持续响应 alice 的对话需求",
        priority="high",
        source="chat:alice",
    )

# 用户发消息——追加到 chat task 叙事
episodic.record(role="user", content=user_input, task_id=str(task.id))

# loop 处理 chat task——读取完整对话历史作为上下文
narrative = episodic.load_for_context(task_id=str(task.id), max_chars=4000)

# loop 生成回复——写入 chat_replies
if task.source.startswith("chat:"):
    chat_id = task.source[5:]  # "chat:alice" → "alice"
    await store.add_chat_reply(chat_id, task.id, reply_content)

# loop 追加 assistant 回复到叙事（保持对话历史完整）
episodic.record(role="assistant", content=reply_content, task_id=str(task.id))
```

### 叙事连续性（Ricoeur 1984）

```
chat alice 第 1 次启动
  └→ task-42.md: [user]      帮我看一下这段代码
  └→ task-42.md: [assistant] 这段代码第 3 行有个边界问题...

chat alice 退出（进程退出），loop 继续运行

chat alice 第 2 次启动（次日）
  └→ get_chat_task("alice") → 恢复 task 42
  └→ load_for_context("42") → 读取完整 task-42.md，包含上次对话
  └→ [user]      昨天那个问题你有新想法吗？
  └→ [assistant] 有，我在昨晚的认知循环里又考虑了一遍...
```
