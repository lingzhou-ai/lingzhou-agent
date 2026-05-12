# 情绪模块

> lingzhou 的情绪不是装饰——它是认知调节信号。

---

## 1. 理论基础

lingzhou 采用 **OCC 情绪模型**（Ortony, Clore & Collins 1988）的精简实现：

```
事件评估（Appraisal）
  → 情绪感受（Feeling: valence + arousal）
    → 核心情感（CoreAffect: Russell 2D 环形空间）
      → 情绪调节（Regulation）
        → 主导情绪标签（dominant）
```

---

## 2. 情绪状态（EmotionState）

```python
@dataclass
class EmotionState:
    valence: float    = 0.6   # [0, 1]：负面(0) → 正面(1)
    arousal: float    = 0.5   # [0, 1]：平静 → 激活
    dominance: float  = 0.5   # [0, 1]：无力 → 主导
    appraisal: Appraisal      # OCC 评价维度（novelty / goal_congruence / control / certainty）
    feelings: list[Feeling]   # 离散情感列表（强度 < 0.15 过滤）
    dominant: str             # 强度最高的离散情感名称（"joy"|"fear"|"distress"|...）
    regulation: Regulation    # 调节策略对象（strategy + reason）
```

### Regulation（调节策略）
```python
@dataclass
class Regulation:
    strategy: str = "maintain"   # "maintain" | "down-regulate" | "up-regulate"
    reason: str = ""
```

### Appraisal（OCC 评价维度）
```python
@dataclass
class Appraisal:
    novelty: float         = 0.0  # 新奇度
    goal_congruence: float = 0.0  # 目标一致性（[-1,1]，唯一有符号的维度）
    control: float         = 0.0  # 控制感
    certainty: float       = 0.0  # 确定性
```

---

## 3. 情绪推导流程

```python
emotion.derive_from_signals(
    failure_count=failure_count,
    prediction_error=prediction_error,
    wm_pressure=wm_pressure,
    workspace_dirty=workspace_dirty,
    alpha=cfg.emotion.ema_alpha,
    high_error_streak=high_error_streak,
    replay_trend=replay.trend,
    task_status=task_status,
    has_next_step=has_next_step,
    has_active_task=has_active_task,
)
```

### 推导规则

| 输入信号 | 情绪影响 |
|---|---|
| `prediction_error` 高 | `goal_congruence` ↓，`novelty` ↑，`certainty` ↓ |
| `wm_pressure` 高 | `control` ↓，`certainty` ↓（wm_trust = 1 - wm_pressure）|
| `failure_count` > 0 | `goal_congruence` ↓，`distress` / `fear` 情感强度上升 |
| `has_next_step` | `hope` / `confidence` 情感强度上升 |
| `replay_trend == "recovering"` | `relief` 情感强度上升，`curiosity` 正向 |
| `task_status == "blocked"` | `frustration` 情感强度上升 |

`valence`/`arousal`/`dominance` 通过 EMA 平滑（`alpha = cfg.emotion.ema_alpha`），性格不因单次经历骤变。

### 调节逻辑
```
arousal > 0.75 or valence < 0.30  →  regulation.strategy = "down-regulate"（高唤醒或持续低效价）
recovering and valence < 0.55     →  regulation.strategy = "up-regulate"（感知趋势改善中）
其他                               →  regulation.strategy = "maintain"
```

---

## 4. 情绪重放摘要（EmotionReplaySummary）

判断层注入的不是原始情绪值，而是**情绪趋势摘要**：

```python
build_emotion_replay(emotion_events: list) -> EmotionReplaySummary
```

```python
@dataclass
class EmotionReplaySummary:
    samples: int              # 近 N 个事件数量
    down_regulate_streak: int # 连续 "down-regulate" 轮次（从最新往前统计）
    trend: str                # "insufficient_data" | "stable" | "recovering" | "worsening"
```

**设计意图**：LLM 不需要原始 `valence=-0.3` 数值，需要的是"我最近情绪持续低落，应该谨慎"这样的语言提示。

---

## 5. 情绪与判断层的连接

### 注入字段（当前）
```
{emotion_valence}    → 数值（[0,1]，正面程度）
{emotion_arousal}    → 数值（[0,1]，激活程度）
{emotion_dominant}   → 主导情绪标签（"joy" | "fear" | "distress" | ...）
{emotion_regulation} → 调节策略（"down-regulate" | "up-regulate" | "maintain"）
```

---

## 6. 情绪影响感知层

情绪通过 Ethos 层间接影响任务生成。具体机制如下：

每 tick，loop.py 在 `_maybe_curiosity_task()` 中根据 ethos 好奇心阈值（`ethos.values.curiosity`）确定性触发探索任务：

```python
# core/loop.py — _maybe_curiosity_task()
if idle_cycles >= cfg.thresholds.curiosity_idle_min_cycles:
    if ethos.values.curiosity >= cfg.thresholds.curiosity_idle_task:
        # 防重复：最近 10 任务中无未完成的 curiosity 任务
        await task_store.add_task(
            title="自主探索：回顾近期经历并整合语义记忆",
            source="curiosity",
        )
```

此外，情绪的调节策略（`regulation.strategy`）会出现在判断束中，LLM 据此自主决定是否在高压情绪状态下暂停/缩窄行动范围。

**设计意图**：情绪信号不直接命令任务生成，而是通过 Ethos 值影响行为倾向（EthosBias），再通过 LLM 判断层自主决定行动策略——保持 LLM 自主性的同时提供认知引导。

---

## 7. 情绪的情节记录

每 tick 情绪状态写入 SQLite events 表（`episodic.record_event("emotion", ...)`）：

```python
episodic.record_event("emotion", {
    "valence": emotion.valence,
    "arousal": emotion.arousal,
    "dominance": emotion.dominance,
    "dominant": emotion.dominant,
    "regulation_strategy": emotion.regulation.strategy,
    "regulation_reason": emotion.regulation.reason,
    "cycle": cycle_count,
})
```

用于构建 `EmotionReplaySummary`（读取近 8 个情绪事件，分析趋势）。

---

## 8. 与 Ethos 的关系

情绪和 Ethos 相互影响，但不等同：

```
Ethos（价值观）→ 影响情绪调节方向
  care_for_user 高 → regulation 偏向 "approach"
  cautious_action 高 → regulation 偏向 "inhibit"

情绪（当前状态）→ 影响 Ethos 偏差
  持续负面情绪 → EthosBias.emotional_load 增高
  → 判断层信号：prefer_narrow_scope = True
```

---

## 9. 设计原则

1. **情绪是认知调节信号**，不是角色扮演的装饰
2. **情绪不直接决定行动**——只影响判断层的姿态（posture: act / pause / narrow）
3. **情绪需要记忆**——连续低落比单次低落更重要，这就是 `EmotionReplaySummary` 存在的原因
4. **情绪可以触发自我调节任务**——真正的 metacognition
5. **情绪随 EMA 基线演化**——不是每次都从零计算，有历史连续性
