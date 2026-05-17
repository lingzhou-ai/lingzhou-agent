# 灵舟 (lingzhou) — 自编程自进化认知 Agent

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

灵舟是一个**自编程、自进化的认知 Agent**。它在 Linux 服务器上自主运行，通过微信与用户交互，具备自我感知、自主探索、自我改进的能力。

## 核心理念

> 数字生命应该有自驱力。

灵舟不是被动等待指令的聊天机器人。它拥有**好奇心引擎**（基于 Active Inference + Intrinsic Motivation），在空闲时自主探索知识、改进自身代码、整理记忆。

## 快速开始

```bash
# 安装
git clone https://cnb.cool/xiaolanplan/lingzhou.git
cd lingzhou && pip install -e .

# 配置
cp lingzhou.json.example ~/.lingzhou/lingzhou.json
# 编辑 ~/.lingzhou/lingzhou.json 设置 API keys
# 创建 ~/.lingzhou/.env 写入 DASHSCOPE_API_KEY / DEEPSEEK_API_KEY

# 启动
lingzhou gateway start -d          # 后台运行（默认微信通道）
lingzhou gateway start --channel local  # 仅终端

# 管理
lingzhou gateway logs tail -f      # 实时日志
lingzhou gateway logs stats        # 统计概览
lingzhou gateway restart           # 重启
lingzhou stop                      # 停止
```

### 系统服务（推荐）

```bash
sudo cp scripts/lingzhou.service /etc/systemd/system/
sudo systemctl enable --now lingzhou
```

## 架构

```
感知层 (Perception)  →  好奇心引擎 (Self-Drive)
         ↓                        ↓
    判断层 (Judgment)  ←  LLM 多模型路由
         ↓
    执行层 (Execution) → 46 个工具
         ↓
    反思层 (Reflection) → 进化引擎 (Evolution)
```

- [架构详解](docs/ARCHITECTURE.md)
- [自驱力理论](docs/SELF_DRIVE.md)

## 工具 (46 个)

### 文件 · Shell · 进程
`file.read` `file.write` `file.edit` `file.list` · `shell.run` · `process.*` (5)

### 记忆 · 任务 · 计划
`memory.*` (6) · `task.*` (9 含 `task.plan`) · `schedule.*` (4)

### Web · 浏览器
`web.fetch` `web.search` · `browser.*` (5: navigate/snapshot/click/type/scroll)

### 媒体
`image.analyze` `image.generate` `tts.speak`

### 元能力
`config.get` `config.set` · `skill.*` · `reflect.structural` · `plugin`

[完整工具目录](docs/TOOLS.md)

## 特性

- **🧠 自驱力引擎** — Active Inference + Intrinsic Motivation，空闲时自主探索
- **🔧 自进化** — 检测失败模式，LLM 生成修复代码，语法验证后用热加载生效
- **📋 任务管理** — 完整的 add→advance→complete→fail 生命周期
- **💬 微信 Bot** — 通过 hermesclaw 代理接入，支持 slash 命令路由
- **🌐 Web 能力** — 网页搜索、网页抓取、headless 浏览器
- **🔌 插件系统** — discover→load→register→start 生命周期
- **♻️ 配置热加载** — 修改 lingzhou.json 无需重启
- **🛡️ 安全** — workspace 沙箱、路径穿越检测、原子写入

## 配置

```jsonc
// ~/.lingzhou/lingzhou.json
{
  "model": "deepseek/deepseek-v4-flash",
  "loop": { "max_idle_gap": 45, "act": true },
  "evolution": { "enabled": true },
  "gateway": { "default_channel": "wechat" }
}
```

LLM 可通过 `config.get` / `config.set` 工具在运行时自主调参。

[完整配置参考](docs/CONFIG.md)

## 插件开发

```python
# plugins/my-plugin/plugin.json
{"id": "my-plugin", "name": "My Plugin", "version": "0.1.0"}

# plugins/my-plugin/__init__.py
def register(ctx):
    # 注册工具或通道
    pass
```

[插件开发指南](docs/PLUGIN.md)

## 项目结构

```
lingzhou/
├── core/           # 认知核心 (loop/judgment/perception/evolution/self_drive)
├── cli/            # 命令行入口 (gateway/chat/config/logs/plugin)
├── tools/          # 46 个工具
├── memory/         # 记忆系统 (WM/episodic/semantic/task_store)
├── provider/       # LLM 接入层
├── plugins/        # 插件目录
├── docs/           # 文档
└── scripts/        # systemd wrapper / watchdog
```

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)

## 致谢

灵舟的理论基础：
- **Active Inference** — Karl Friston (2013)
- **Intrinsic Motivation** — Oudeyer & Kaplan (2007)
- **Self-Regulated Learning** — Zimmerman (2000)
- **Open-Ended Learning** — Wang et al. (2019, POET)

灵舟在架构上参考了 [OpenClaw](https://github.com/openclaw/openclaw) 和 [Hermes](https://github.com/AaronWong1999/hermesclaw)。

## 许可证

MIT
