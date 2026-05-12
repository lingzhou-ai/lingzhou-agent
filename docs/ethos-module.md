# Ethos 模块

> Ethos 是 lingzhou 的价值观层，介于 Soul 的不变公理和情绪的瞬时波动之间。

---

## 1. 三层价值体系

```
hard_axioms（公理层）
    ↓ 永不改变，代码级锁定

ethos_baseline（基线层）← EMA 缓慢演化
    ↓ 稳定的价值观，随经历漂移

ethos_state（瞬态层）← 每 tick 计算
    ↓ 当前上下文的价值激活
    → EthosBias（偏差度量）
    → JudgmentSignals（判断建议）
```

---

## 2. EthosValues

```python
@dataclass
class EthosValues:
    truth: float      = 0.65  # [0,1] 追求证据、不妄下结论
    caution: float    = 0.60  # [0,1] 偏好保守、可撤销的操作
    continuity: float = 0.60  # [0,1] 维护任务连续性
    curiosity: float  = 0.45  # [0,1] 主动探索和学习
    care: float       = 0.55  # [0,1] 对用户数据和状态负责
```

这 5 个维度来自 Hermes 的 ethosValues 设计，但 lingzhou 将其与 EMA 演化机制结合。

---

## 3. 瞬态 EthosState 推导

```python
derive_ethos_state(
    failure_count: int,
    high_error_streak: int,
    has_active_task: bool,
    has_next_step: bool,
    perception_trend: str,         # "stable" | "worsening" | "recovering"
    emotion_down_regulate_streak: int,
    baseline: dict[str, float] | None = None,
    ema_alpha: float = 0.9,
    floor_truth: float = 0.50,
    floor_caution: float = 0.45,
) -> EthosState
```

### 推导规则

**基础**：瞬态值从 `EthosValues` 默认值出发，信号叠加调整后与 EMA 基线混合。

**调整因子**：

| 条件 | 调整 |
|---|---|
| `failure_count > 0` | `truth` += 0.10, `caution` += 0.10, `curiosity` -= 0.08 |
| `high_error_streak >= 2` | `truth` += 0.10, `caution` += 0.12, `care` -= 0.08 |
| `has_active_task` | `continuity` += 0.12 |
| `has_next_step` | `continuity` += 0.08, `care` += 0.06 |
| `perception_trend == "recovering"` | `curiosity` += 0.08, `care` += 0.04 |

**上下界**：所有维度 clamp 到 [0, 1]，EMA 混合后再施加运行时下限：`truth` ≥ `floor_truth`（0.50），`caution` ≥ `floor_caution`（0.45）。

---

## 4. EthosBias

```python
@dataclass
class EthosBias:
    prefer_verification: bool = False  # 优先验证类动作（caution > 0.70 或失败 >= 2 时置 True）
    prefer_narrow_scope: bool = False  # 优先收窄操作范围（失败 >= 2 或高误差连续 >= 2）
    preserve_continuity: bool = False  # 优先维持任务连续（continuity > 0.70 且有活跃任务）
    avoid_overclaiming: bool  = False  # 避免过度承诺（情绪持续下调 streak >= 2）
    reasons: list[str]                 # 每个置 True 的 bias 对应的中文理由
```

EthosBias 是从价值观推导的**行为倾向**，供候选动作预排名使用：
- 每 tick 由 `derive_ethos_state()` 确定性推导，不由 LLM 生成
- 注入 `ethos_section` 后以自然语言形式出现在判断 prompt 里

---

## 5. JudgmentSignals（判断建议）

```python
@dataclass
class JudgmentSignals:
    require_more_evidence: bool   # 在行动前需要更多信息
    prefer_narrow_scope: bool     # 优先选择范围更小的操作
    posture: Literal["act", "pause", "narrow"]  # 整体姿态
```

### 计算规则

```python
require_more_evidence = (
    high_error_streak >= 2 or
    (perception_trend == "worsening" and failure_count > 0)
)
prefer_narrow_scope = (
    failure_count >= 2 or high_error_streak >= 2
)
posture = (
    "narrow" if (
        failure_count >= 3 or
        (failure_count >= 1 and emotion.regulation.strategy == "down-regulate")
    ) else
    "pause"  if (
        high_error_streak >= 2 or
        (perception_trend == "worsening" and failure_count >= 2)
    ) else
    "act"
)
```

---

## 6. 注入判断层

```python
# core/judgment.py _fmt_ethos()
ethos_section = f"""
价値图式  truth={ethos.values.truth:.2f}  caution={ethos.values.caution:.2f}
          continuity={ethos.values.continuity:.2f}  curiosity={ethos.values.curiosity:.2f}  care={ethos.values.care:.2f}
行为倾向  {', '.join(active_biases)}   # prefer_verification / prefer_narrow_scope / ...
理由      {'; '.join(ethos.bias.reasons)}
"""

signals_section = f"""
需要更多证据：{"是" if signals.require_more_evidence else "否"}
优先缩小范围：{"是" if signals.prefer_narrow_scope else "否"}
当前姿态：{signals.posture}
"""
```

在 `prompts/judgment.md` 中：
```
## 价值观状态（Ethos）
{ethos_section}

## 判断建议信号
{signals_section}
```

---

## 7. Ethos 的 EMA 演化

每 tick 结束时（或每 N tick），瞬态 ethos_state 混合进基线：

```python
α = cfg.soul.ethos_ema_alpha  # 默认 0.9
new_baseline = {
    k: α * old_val + (1 - α) * new_val
    for k, (old_val, new_val) in zip(baseline, state.values)
}
await task_store.set_fact("soul:ethos_baseline", json.dumps(new_baseline))
```

**α=0.9 的含义**：
- 单次异常不会颠覆价值观
- 持续 10 个 tick 的偏移，才会造成约 1-e^{-1} ≈ 63% 的基线偏移
- 这模拟了人类价值观的惰性和稳定性

---

## 8. 与情绪的区分

| 维度 | 情绪（Emotion） | Ethos |
|---|---|---|
| 时间尺度 | 瞬时（单 tick） | 缓慢演化（EMA） |
| 描述对象 | 当前感受（valence/arousal） | 价值观倾向（truth/care/...） |
| 影响对象 | 调节策略（approach/avoid/inhibit） | 判断姿态（act/pause/narrow） |
| 可变性 | 高（每 tick 重新计算） | 低（α=0.9 EMA 惰性） |

情绪影响 Ethos（瞬态调整），Ethos 影响判断姿态，判断姿态影响 LLM 决策。  
三层级联，形成有韧性的认知调节链。

---

## 9. 设计原则

1. **Ethos 不是角色设定**——它是动态计算的，受经历影响
2. **Ethos 基线可以进化**——EMA 渐变 + evolution 机制主动重写，lingzhou 可以重塑自己的价值倾向
3. **hard_axioms 是唯一例外**——禁忌层在 Ethos 之上，是自编程的唯一禁区，只有人类可以变更
4. **JudgmentSignals 是建议，不是命令**——LLM 可以覆盖，但必须说明理由（rationale）
5. **EthosBias 是自我意识**——系统知道自己现在距离"正常的自己"有多远
