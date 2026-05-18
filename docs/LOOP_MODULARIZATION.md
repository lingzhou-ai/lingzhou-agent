# loop.py 模块化拆分建议

目标：先拆职责，再拆文件；保持 `core.loop` 作为稳定 façade，不在一次提交里重写主循环。

## 目录建议

```text
channels/
  __init__.py
  wechat.py

core/
  loop/
    __init__.py          # 薄 façade：稳定导出、兼容旧 import
    runtime.py           # 主循环编排：CognitionLoop、公开生命周期
    tick.py              # 单次 tick 编排：perceive -> judgment -> execute
    chat.py              # chat_messages 读写、reply flush、交互超时
    postprocess.py       # memory/facts/task progress/meta reflection/evolution tail
    logging.py           # 周期日志、reply clip、context scrub、观测指标
    progress.py          # 任务推进判定与重复动作识别
```

## 拆分顺序

1. 先抽纯函数和 helper。
2. 再抽状态较少的后处理模块。
3. 最后处理持有大量实例字段的主 tick 编排。

## 第一阶段

- `loop/logging.py`
  - `_strip_memory_context`
  - `_clip_reply_for_log`
  - tick/reply 相关日志格式化函数
- `loop/postprocess.py`
  - task progress 同步
  - meta reflection 写入
  - success stall / failure stall 后处理
- `loop/chat.py`
  - chat pending 拉取
  - assistant reply 先落库再做后续持久化
  - chat 绑定与 reply chat id 恢复

- `loop/driver.py`
  - 单轮 run 调度
  - 事件驱动 idle wait
  - act/wait 的下一轮唤醒策略

- `loop/startup.py`
  - 启动期 provider/routing 装配
  - soul bootstrap 与状态恢复
  - self model 恢复与启动期路由摘要

## 第二阶段

- `loop/runtime.py`
  - provider/plugin/tool/channel 初始化
  - routing provider 热切换
- `loop/tick.py`
  - `_tick`
  - `_tick_finalize`
  - tool rounds 内循环

## 当前落地状态

- 已落地：`loop/logging.py`、`loop/postprocess.py`、`loop/common.py`、`loop/chat.py`、`loop/driver.py`、`loop/startup.py`、`loop/tick.py`
- 当前 `loop/runtime.py` 主要保留：启动生命周期、provider/plugin 装配、状态恢复、对外 façade 代理方法
- 当前 `loop/chat.py` 负责 chat id 绑定、pending chat 消费、交互入口
- 当前 `loop/driver.py` 负责单轮调度和事件驱动等待
- 当前 `loop/startup.py` 负责启动期 routing/provider/soul/self-model/state 恢复
- 已完成收口：`runtime.py` 的热重载逻辑已抽到 `core/loop/reload.py`；`TaskStore` 的 task/run/reflection 等持久化边界已沉到 `store/memory/`
- 下一步优先：继续压缩 `core/judgment/runtime.py`，并收掉文档中的历史迁移描述，避免 README / CHANGELOG / 设计文档口径漂移

## 与多模态扩展的关系

- `channels/` 只负责接入和消息归一化，不负责理解。
- 图片/语音/视频理解统一走工具层和 provider 能力路由。
- 当前图片能力已经可以按 `vision` 自动选模型；后续新增 `audio` / `video` 时，沿用同一条“先判能力，再选模型”的路线。

## 命名原则

- `channels/` 放外部入口协议。
- `core/loop/` 放认知内环编排。
- `tools/` 保持用户可调用动作。
- `provider/` 只负责模型目录、payload 组装、能力路由。