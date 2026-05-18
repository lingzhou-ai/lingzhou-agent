"""core/probe — 灵舟探针系统。

探针（Probe）是灵舟可自由部署的感知单元，类似传感器或监控脚本。
LLM 可以通过 probe.install / probe.remove / probe.run / probe.list 工具
在运行时自由放置和收回探针。

## 设计思路（参考文献）

- Minsky (1986) "The Society of Mind"：多个专化感知器组成的感知织物
- Brooks (1986) Subsumption Architecture：独立感知层直接影响行为
- Weiser (1991) "The Computer for the 21st Century"：环境传感器提供上下文感知
- Prometheus 监控模型：具名导出器 + 可配置抓取间隔 + 告警规则

## 数据回传路径

- none / log：只记录日志
- wm：结果注入工作记忆（WorkingMemory），供下一个 tick 感知
- chat：以用户消息形式发回活跃会话，LLM 会直接看到
"""
from core.probe.manager import ProbeManager

__all__ = ["ProbeManager"]
