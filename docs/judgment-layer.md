# 判断层

> 判断层（Judgment）是 lingzhou 的决策核心，将所有认知信号整合为一个行动。

---

## 1. 职责

```
感知层  →  情绪层  →  Ethos层  →  【判断层】  →  执行层
```

判断层做三件事：
1. **组装判断束（bundle）**：从所有内存层收集上下文
2. **调用 LLM**：填充 `prompts/judgment.md` 模板，发送请求
3. **解析输出**：将 LLM 回复解析为 `JudgmentOutput`，驱动执行层

---

## 2. 判断束（Context Bundle）

`_assemble_context()` 收集以下字段：

### 全部已实现（注入模板）
| 字段 | 来源 | 含义 |
|---|---|---|
| `task_section` | `task_store.get_active()` | 当前任务状态 |
| `emotion_valence` | `emotion.valence` | 效价（[0,1]）|
| `emotion_arousal` | `emotion.arousal` | 唤醒度（[0,1]）|
| `emotion_dominant` | `emotion.dominant` | 主导情绪标签 |
| `emotion_regulation` | `emotion.regulation.strategy` | 调节策略（down-regulate / up-regulate / maintain）|
| `perception_section` | `percept` 感知结果 | 原始感知 |
| `perception_replay_section` | `build_perception_replay()` | 感知趋势摘要 |
| `wm_section` | `wm.snapshot()` | 工作记忆快照 |
| `failures_section` | `task_store.list_failures_for_task()` | 失败记录 |
| `episodic_section` | `episodic.load_for_context(task_id)` | 情节记忆叙事 |
| `memories_section` | `semantic.retrieve_multi_anchor(anchors)` | 语义记忆节点 |
| `soul_section` | `facts["soul:*"]` | 价值基线 |
| `hard_boundaries_section` | `facts["soul:hard_axioms"]` | 不可违反的公理 |
| `ethos_section` | `derive_ethos_state()` + `_fmt_ethos()` | 当前价值观状态与行为倾向 |
| `signals_section` | `compute_judgment_signals()` | 确定性判断预信号 |
| `skills_section` | `skill_registry.match_for_context()` | 激活的认知护栏 |
| `cognitive_signals_section` | `CognitiveSignals.to_text()` | 循环探针 + WM/情绪警报 |
| `entity_section` | `semantic.retrieve_multi_anchor()` | 实体记忆 |
| `current_time_section` | `datetime.now()` | 当前时间 |
| `tools_section` | `tool_registry.list_manifest()` | 可用工具清单 |
| `user_message` | 用户输入（或 None） | 用户指令 |

---

## 3. JudgmentOutput 结构

```python
@dataclass
class JudgmentOutput:
    decision: str           # 决策摘要
    chosen_action_id: str   # 工具 ID，如 "file.read"
    params: dict            # 工具参数
    rationale: str          # 推理过程
    reply_to_user: str      # 对用户的回复（可为空）
    next_step: str          # 下一步计划
    reflection: str          # 本轮洞察 → 由 loop.py 写入 semantic memory
```

`reflection` 字段：当 LLM 输出包含 reflection 时，loop.py 将其写入 `semantic.store_reflection()`。

---

## 4. prompts/judgment.md 模板结构

```markdown
# 判断束

## 当前任务
{task_section}

## 感知状态
{perception_section}

### 感知趋势
{perception_replay_section}

## 情绪状态
- 效价：{emotion_valence}
- 唤醒：{emotion_arousal}
- 主导情绪：{emotion_dominant}
- 调节策略：{emotion_regulation}

## 价值观状态（Ethos）
{ethos_section}

## 判断建议信号
{signals_section}

## 绝对边界（不可违反）
{hard_boundaries_section}

## 认知信号
{cognitive_signals_section}

## 工作记忆
{wm_section}

## 最近失败
{failures_section}

## 情节记忆
{episodic_section}

## 语义记忆
{memories_section}

## Soul（价值基线）
{soul_section}

## 当前激活的认知防线
{skills_section}

## 可用工具
{tools_section}

## 用户消息
{user_message}
```

---

## 5. 安全兜底（_simulate_safe_output）

当 LLM 调用失败或输出无法解析时，降级到确定性兜底：

```python
def _simulate_safe_output(
    posture: str,       # "act" | "pause" | "narrow"
    hard_boundaries: list,
    failures: list,
) -> JudgmentOutput:

    # 优先级：hard_boundary 触发 → posture == "pause" → 默认 wait
    if _boundary_violated(hard_boundaries):
        return JudgmentOutput(chosen_action_id="system.refuse", ...)
    if posture == "pause":
        return JudgmentOutput(chosen_action_id="system.wait", ...)
    if posture == "narrow":
        return JudgmentOutput(chosen_action_id="memory.get_fact", ...)  # 最安全的读操作
    return JudgmentOutput(chosen_action_id="system.wait", ...)
```

**设计原则**：宁可停下，不可错误行动。

---

## 6. 判断层调用流程

```python
# core/loop.py — 每 tick
action = await judgment.decide(
    percept=percept,
    wm=wm,
    task_store=task_store,
    episodic=episodic,
    semantic=semantic,
    emotion=emotion,
    ethos_state=ethos_state,
    judgment_signals=signals,
    hard_boundaries=hard_axioms,
    perception_replay=perception_replay_summary,
    cognitive_signals=cognitive_signals,
)
```

内部流程：
1. `_assemble_context()` → `ctx` 字典
2. `prompt = judgment_md.format(**ctx)` → 填充模板
3. `provider.chat([{"role": "user", "content": prompt}])` → LLM 调用
4. `_parse_output(response)` → `JudgmentOutput`
5. 若解析失败 → `_simulate_safe_output()`

---

## 7. 已知问题与修复路线

| 问题 | 状态 | 修复 |
|---|---|---|
| 6 个字段未注入模板 | ✅ 已修复 | 已在 `_assemble_context()` 中全部注入 |
| `reflection` 字段缺失 | ✅ 已实现 | `JudgmentOutput` 已有此字段，loop 写回 semantic |
| `skills_section` 未注入 | ✅ 已实现 | `skill_registry.match_for_context()` 接入 `_assemble_context` |
| BOOTSTRAP.md/IDENTITY.md 未注入 | ✅ 已实现 | `soul.bootstrap()` 读取文件 → WM `kind="bootstrap_identity"` + `judgment.set_identity_prefix()` |

---

## 8. 设计原则

1. **判断层是整合器，不是执行者**——它只产生 `JudgmentOutput`，不直接调用工具
2. **所有认知信号必须进入 bundle**——任何计算但未注入的字段都是信息损失
3. **兜底必须保守**——LLM 不可达时，选择最小影响操作（wait / 只读）
4. **reflection 是学习闭环**——每次判断结束应有机会写入新的语义记忆节点
5. **hard_axioms 必须在 bundle 里明确出现**——不能靠 LLM 自觉，要写进模板
