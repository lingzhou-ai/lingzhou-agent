# lingzhou 路线图（v2026.5.15 之后）

## 0. 已完成（2026-05-16 打磨）

以下项目在两轮深度打磨中完成：

### 思考/操作分离
- deepseek-v4-pro 作为思考模型（reasoner），deepseek-v4-flash 作为操作模型（reader）
- 双模型架构：思考层统筹全局，可委派简单任务给操作层
- 4 个 DeepSeek 模型接入（v4-flash/v4-pro/chat/reasoner）

### 自我模型
- `core/self_model.py`：数字生命自知——tick 计数、token 消耗、成本估算
- 跨重启持久化（`self:model` fact）
- 按量 vs 按次计费模式感知
- 每个 tick LLM 都能看到自我状态

### 机制"有思想"改造
- `_action_made_progress` 从 bool → (bool, reason)，LLM 看到原因后自主判断
- `ToolManifest.progress_category` / `prefer_tier`：工具自声明，减少硬编码
- 行为追踪器状态全量注入 CognitiveSignals
- `task.complete` 证据门槛（MutationWithoutVerification）
- 同文件顺序窗口探测

### Provider 重构
- `_ModeAdapter` 模式适配器替代 83 if/elif → 57
- copilot/bailian/deepseek 统一通过适配器

### 路由与感知
- `team_view`：思考模型看到完整团队架构和调度规则
- `self_model_section`：每次 tick 注入 LLM 上下文
- 探索预算感知注入 CognitiveSignals
- 上下文压缩时告知 LLM "原 N→M tokens"

---


**创建时间：** 2026-05-15  
**基线版本：** v2026.5.15  
**定位：** 去历史包袱，只做最对的事情

---

## 1. 当前判断

lingzhou 当前的关键问题已经不是“缺几个基础工具”，而是：

1. **认知控制面和执行面还没有真正分离**
2. **复杂任务无法异步运行并回流结果**
3. **进化机制还只是单环纠错，不是真正双环学习**
4. **感知层缺视觉/多模态，导致输入世界残缺**

因此，下一阶段不应再以“多入口、多通道、多花样能力”为主线，
而应围绕一个更干净的主线推进：

> **Task 负责目标，Run 负责执行，Worker 负责干活，MetaReflection 负责学习。**

---

## 2. 最佳方案（收束版）

### 2.1 核心实体

| 实体 | 职责 | 当前状态 |
|------|------|----------|
| **Task** | 目标单元：要完成什么 | ✅ 已有 |
| **Run** | 执行单元：这次具体怎么执行 | ❌ 待引入 |
| **Worker** | 执行器：谁来执行 | ❌ 待引入 |
| **MetaReflection** | 学习单元：问题属于单环还是双环 | ❌ 待引入 |

### 2.2 设计原则

1. **不再引入 delegate 作为独立主概念**
   - 任务（Task）和执行（Run）分离就够了
2. **先做 Run，不先做 session 子代理系统**
   - 当前最需要的是异步执行，不是复杂 agent 社交结构
3. **双环学习先独立建模，再驱动 evolution**
   - evolution 负责改；MetaReflection 负责判断“改哪一层”
4. **多模态优先于多通道**
   - 视觉能力属于感知层补全，多通道只是入口扩张
5. **沙箱后置**
   - 当前阶段先把执行闭环做通，再考虑更强隔离

---

## 3. 目标架构

```
Cognitive Control Plane
  ├─ 感知/情绪/Ethos
  ├─ 判断与计划
  ├─ Task 调整
  ├─ Run 创建与监控
  └─ 结果整合

Execution Plane
  ├─ exec-worker
  ├─ tool-chain-worker
  ├─ llm-worker
  └─ multimodal-worker

Meta-Learning Plane
  ├─ Single-loop: 修工具/修prompt/修参数
  └─ Double-loop: 修规则/修tier/修task拆分/修阈值
```

---

## 4. 当前双环系统体检（精简结论）

| 环 | 当前状态 | 问题 |
|----|----------|------|
| 认知主环 | ✅ 正常 | 无 |
| 工具内环 | ⚠️ 只在 chat 模式 | 自主任务效率低 |
| 进化环 | ⚠️ 只有单环纠错 | 不质疑前提假设 |

结论：

> lingzhou 目前不是“真正的双环系统”，而是“单环认知循环 + 单环进化补丁系统”。

---

## 5. 优先级列表（新的最终排序）

### P0：必须先做

| ID | 任务 | 目标 | 验证方式 |
|----|------|------|----------|
| **P0-1** | 视觉/多模态能力 | 补全感知层 | `image.analyze` 能稳定分析单图/多图 |
| **P0-2** | 自主循环内环 | 自主任务不再一跳一停 | 无用户消息时可连续工具调用 |
| **P0-3** | Task-level model routing | 同一 task 的推理风格稳定 | task 级 tier 锁定 + step override 可用 |

### P1：核心结构升级

| ID | 任务 | 目标 | 验证方式 |
|----|------|------|----------|
| **P1-1** | 引入 Run 抽象 | 目标与执行分离 | 新增 runs 表 / run 生命周期跑通 |
| **P1-2** | Worker 执行器 | 复杂动作异步执行 | exec/tool-chain/llm worker 至少 2 类跑通 |
| **P1-3** | Run 状态回流 Task | 主环知道谁在跑、跑到哪、跑完了吗 | task 可根据 run 结果自动调整 |
| **P1-4** | MetaReflection（双环学习器） | 区分单环 vs 双环问题 | 能输出 tool/prompt/rule/threshold/task_split 诊断 |

### P2：闭环质量提升

| ID | 任务 | 目标 | 验证方式 |
|----|------|------|----------|
| **P2-1** | 进化效果验证 | 改了之后知道是否更好 | success rate / error rate before-after 对比 |
| **P2-2** | 自动回滚 | 改坏了能恢复 | 进化后恶化自动 rollback |
| **P2-3** | 多 run 并行 | 提升吞吐 | 主环可同时监控多个 running run |
| **P2-4** | 运行中结晶 | 不必等 task 完成才沉淀记忆 | 长任务中间有 progress crystal |

### P3：后置事项

| ID | 任务 | 说明 |
|----|------|------|
| **P3-1** | 多通道 | 不是当前核心矛盾 |
| **P3-2** | 复杂沙箱 | 安全重要，但当前后置 |
| **P3-3** | 重型插件生态 | 等控制面/执行面稳定后再做 |
| **P3-4** | 三环学习 | 价值观/身份层学习，当前不急 |

---

## 6. 推荐实施顺序

### 第 1 组（先把最核心的问题打穿）
1. P0-1 视觉/多模态
2. P0-2 自主循环内环
3. P0-3 Task-level model routing

### 第 2 组（把控制面和执行面分离）
4. P1-1 Run 抽象
5. P1-2 Worker 执行器
6. P1-3 Run 状态回流 Task

### 第 3 组（把“会改”升级成“会学”）
7. P1-4 MetaReflection（双环学习器）
8. P2-1 进化效果验证
9. P2-2 自动回滚

### 第 4 组（提速与完善）
10. P2-3 多 run 并行
11. P2-4 运行中结晶

---

## 7. 成功标准

完成这一轮升级后，lingzhou 应该达到：

1. **复杂任务不阻塞主认知环**
2. **任务和执行被清晰分离（Task / Run）**
3. **主环能感知 run 的状态变化并据此调整 task**
4. **学习系统能区分“修工具”与“修前提”**
5. **感知层不再只有文本，具备多模态入口**

---

## 8. 不应该优先做的事

- 为了未来扩展先做重型 session 子代理系统
- 为了完美安全先做复杂沙箱
- 为了看起来完整先铺多通道
- 为了概念漂亮引入过多中间抽象

这些都不是当前最对的事情。

---

## 9. 对应文档

- `blueprint.md`：总蓝图
- `chat-and-task.md`：Task / Run / Chat 分工
- `judgment-layer.md`：判断层现状与升级方向
- `memory-architecture.md`：记忆层如何承接 Run 和 MetaReflection
- `schema-evolution.md`：如何无痛加 runs / meta_reflections 表

## 2026-05-17 — 工具能力对齐

### 新增工具
- web.fetch — 网页抓取
- web.search — 网页搜索 (DuckDuckGo)
- browser.* — 浏览器自动化 (agent-browser)
- task.plan — 结构化执行计划 (对齐 OpenClaw update_plan)

### 安全增强
- 路径守卫: workspace 沙箱 (/root/lingzhou, /root/.lingzhou)
- 原子写入: .lingzhou-tmp → rename
- 目录保护: is_dir 前置检查
- 文件大小限制: 100k 读 / 200k 写

### 修复
- perception_replay NameError → _tick_finalize 传参
- _MUTATION_TOOLS 死循环 → 移除 shell.run
- systemd service → /etc/systemd/system/lingzhou.service
- crash log 捕获 → stderr → crash.log
- 默认通道 → gateway.default_channel: "wechat"
- gateway logs CLI → tail/errors/crash/wechat/stats
