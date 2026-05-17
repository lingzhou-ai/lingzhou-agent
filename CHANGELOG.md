# 更新日志

## [0.2.0] — 2026-05-17

### 新增
- **46 个工具** — 全面对齐 OpenClaw：web.fetch、web.search、browser.*、image.generate、tts.speak
- **task.plan** — 结构化执行计划（对齐 update_plan）
- **config.get/set** — LLM 可自主调参，自动热重载
- **插件系统** — discover→load→register→start 生命周期
- **gateway logs** — tail/errors/crash/wechat/stats 快速看日志
- **file.read offset+limit** — 行号读取，不再碎片化
- **workspace 沙箱** — 路径穿越检测 + 大小限制
- **原子写入** — .lingzhou-tmp → rename
- **systemd 服务** — `/etc/systemd/system/lingzhou.service`

### 修复
- `perception_replay` NameError → `_tick_finalize` 传参
- `_MUTATION_TOOLS` 死循环 → 移除 shell.run
- `IsADirectoryError` → file.write/edit 目录保护
- 自驱力从不触发 → explore-stuck 检测 + co-activation
- file.edit OldTextNotFound → 显示实际文件内容
- 僵尸任务 → 重启时 in_progress → pending
- 静默崩溃 → crash.log 捕获 stderr
- 微信通道 → 默认 wechat，restart 保持通道

## [0.1.0] — 2026-05-12

### 初始版本
- 认知循环 (Perception → Judgment → Execution → Reflection)
- 自驱力引擎 (Active Inference + Intrinsic Motivation)
- 进化引擎 (LLM 生成 + 语法验证 + 热重载)
- 微信 bot 通道 (iLink long-poll via hermesclaw proxy)
- 30+ 工具：文件、Shell、记忆、任务、定时
- CLI chat、gateway logs、plugin 管理
