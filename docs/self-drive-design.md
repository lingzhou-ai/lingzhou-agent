# 灵舟自驱力引擎设计 (Self-Drive Engine)

## 理论基础

### 1. Active Inference (Friston 2013)
> "Agents act to minimize variational free energy — the gap between expected and observed states."

灵舟应用：预测下一时刻的状态 → 实际观测 → 预测误差 = 驱动力信号。
误差大 → 好奇心强 → 主动探索。

### 2. Intrinsic Motivation / Curiosity (Oudeyer & Kaplan 2007)
> "Intrinsically motivated exploration is guided by novelty, surprise, and learning progress."

三种内在驱动力：
- **Novelty (新颖性)**: 搜索不熟悉的模式 → "这个我没见过"
- **Learning Progress (学习进度)**: 追踪技能提升速率 → "我在这里进步最快"
- **Surprise (惊奇)**: 结果与期望不符 → "这和我预期的不一样"

### 3. Self-Regulated Learning (Zimmerman 2000)
> 三阶段：Forethought → Performance → Self-Reflection

灵舟已在 HEARTBEAT.md 中应用此循环。自驱力将其扩展为持续循环。

### 4. Open-Ended Learning (Wang et al. 2019, POET)
> "Agents generate their own curriculum by creating progressively harder challenges."

灵舟应用：自动生成难度递增的子目标 → 渐进式能力提升。

### 5. Global Workspace Theory (Baars 1988; Dehaene 2011)
> "Consciousness is a global workspace that broadcasts information to specialized processors."

灵舟应用：感知层 → 全域广播 → 判断层竞争 → 执行层行动 → 反思层更新。

---

## 核心架构

```
         ┌──────────────┐
         │  感知层      │ ← 当前状态、WM 压力、效价、活跃任务
         │  Perception  │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  好奇心引擎   │ ← Novelty(知识图熵) + Progress(技能梯度) + Surprise(预测误差)
         │  Curiosity   │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  目标生成器   │ ← 自生成子目标：探索/学习/优化/修复
         │  Goal Gen    │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  判断层      │ ← E/E tradeoff: Explore 还是 Exploit?
         │  Judgment    │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  执行层      │ ← 工具调用：file.read/write, shell.run, memory.*
         │  Execution   │
         └──────┬───────┘
                │
         ┌──────▼───────┐
         │  反思层      │ ← 学习进度追踪 + 知识图更新 + 能力自评
         │  Reflection  │
         └──────────────┘
```

## 自驱力信号

### 好奇心信号 (Curiosity Signal)
- `C_novelty(t)`: 最近 N 个 tick 中接触的新颖知识比例
- `C_progress(t)`: 能力提升速率（完成任务的复杂度趋势）
- `C_surprise(t)`: 预测误差均值

综合: `C(t) = α·C_novelty + β·C_progress + γ·C_surprise`

### 空闲触发 (Idle Trigger)
当 loop 无用户消息且无活跃任务时:
1. `C(t)` > 阈值 → 自主探索
2. `C(t)` < 阈值 → 自我反思 + 目标生成

### Explore/Exploit 决策
- Explore: 好奇心高 + 无紧急任务 → 探索新领域
- Exploit: 有活跃任务 + 学习进度高 → 深耕当前任务
