---
name: negative-feedback
description: "用户否定性反馈内化技能。Use when 收到用户消息时先语义判断是否否定之前的行为/答案/结论/探针；若是，必须触发自我反思任务，不能继续推进原任务。防止因忽视否定而重复犯错。"
compatibility: Designed for Lingzhou user message handling.
tags: reflection, user, correction, self-correction
triggers: 否定反馈, 纠正, 搞错了, 不对, 撤回
match_terms: 用户否定, 反思, 纠正, probe.disable, memory.set_fact 覆盖
match_rules: |
  any: 搞错了 | 不对 | 纠正 | 撤回 | 不满意 => 1.0
  any: 否定反馈 | 反思 | 纠正 => 0.8
state_rules: |
  has_user_message => 0.6
---

## 触发判断：语义识别否定性反馈

每当有用户消息时，先做一次语义判断：

> 这条消息是否在否定或纠正我**之前的行为、答案、结论或探针**？

**不依赖关键词**，靠语义理解。以下均属否定性反馈：
- 表达不满意（"不对"、"错了"、"这不是我要的"）
- 指出我搞错了某件事
- 要求我收回/修改某个判断
- 对我的探针/结论提出质疑

## 若判断为否定性反馈：触发反思流程

1. 在 `rationale` 中明确写出：**"用户否定了 [具体内容摘要]"**

2. 本轮**首要行动**是创建反思任务：
   ```
   task.add(
     title="自我反思：[被否定内容摘要]",
     goal="识别错误根因，写入长期记忆，避免重复",
     priority=high
   )
   ```
   > 该反思任务**优先级高于**当前 active task；不要继续推进原有任务

3. 反思任务的完成标准（全部满足才 `task.complete`）：
   - `memory.add_semantic`：写入一条"教训"节点（`kind=lesson`）
   - 判断相关探针是否需要撤回：`probe.disable` / `probe.remove`
   - 判断相关结论是否需要修正：`memory.set_fact` 覆盖旧结论

## 若判断为普通消息：正常流程

普通追问、新指令、或对当前状态的确认 → 按正常决策流程处理，无需触发反思。

## 反例黑名单

| 反模式 | 正确做法 |
|---|---|
| 用户说"不对"后继续推进原任务 | 先停下来，触发反思任务，再讨论是否续推 |
| 依赖关键词判断否定（只认"错误"字样） | 语义理解，表达方式多样 |
| 反思任务只写 `memory.add_semantic` 但不处理探针 | 相关探针和旧结论都要明确判断是否撤回/覆盖 |
| 把否定性反馈当成普通追问处理 | 否定是最高优先级信号，先反思再行动 |
