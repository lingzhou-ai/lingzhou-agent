"""Judgment context formatters focused on skills, cognition and probe panels."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.probe.types import PROBE_COVERAGE_HINTS, normalize_probe_coverage_tags

if TYPE_CHECKING:
    from core.perception import CognitiveSignals
    from core.skill import Skill


def _short_skill_desc(desc: str, limit: int = 200) -> str:
    text = desc.strip()
    return text


def _fmt_skill_catalog(skills: list[Skill], *, pinned_names: set[str] | None = None) -> str:
    if not skills:
        return "（暂无 skills）"
    lines = [
        "**AGENT SKILLS CATALOG** — 阅读每条 description（Use when）后自主判断是否激活，不要仅凭名称猜测。",
        "用 skill.activate(name=\"...\") 加载完整 SKILL.md，再决定是否遵循。",
        "",
        "| 技能 | 说明（Use when）及激活上下文 |",
        "|------|--------------------------|",
    ]
    for skill in skills:
        desc = _short_skill_desc(skill.description)
        compat = str(getattr(skill, "compatibility", "") or "").strip()
        cell = f"{desc}<br>*{compat}*" if compat else desc
        pin_mark = " `[↑]`" if pinned_names and skill.name in pinned_names else ""
        lines.append(f"| `{skill.name}`{pin_mark} | {cell} |")
    lines.append("")
    lines.append("可调用 skill.list / skill.search 浏览；激活前务必 skill.activate 读取完整规则。")
    return "\n".join(lines)


def _fmt_primary_skill(skill: Skill | None) -> str:
    if skill is None:
        return "（本轮无明显 skill 候选；按一般 judgment 规则执行。若遇到专业流程或项目特有规则，再查 catalog 并按需 skill.activate。）"
    origin = str(getattr(skill, "origin", "dynamic") or "dynamic")
    if origin == "workspace" and getattr(skill, "source_path", ""):
        origin = skill.source_path
    return (
        f"**{skill.name}** — {skill.description}\n"
        f"> 候选 skill，不代表已激活。source: {origin}\n"
        f"> 若你判断它与当前任务相关，先调用 skill.activate(name=\"{skill.name}\") 读取完整 SKILL.md，再决定是否遵循。"
    )


def _fmt_skills(skills: list[Skill]) -> str:
    if not skills:
        return "（当前没有候选 skill 被高亮；可按需查阅 catalog）"
    parts: list[str] = [
        "以下是当前上下文下较相关的候选 skills。它们目前仍只是 metadata 线索，不是已注入的完整 instructions。",
    ]
    for skill in skills:
        origin = str(getattr(skill, "origin", "dynamic") or "dynamic")
        if origin == "workspace" and getattr(skill, "source_path", ""):
            origin = skill.source_path
        parts.append(f"**{skill.name}** [{origin}] — {skill.description}")
        parts.append(f"> activation: skill.activate(name=\"{skill.name}\")")
    return "\n".join(parts)


def _fmt_cognitive_signals(signals: CognitiveSignals | None) -> str:
    if signals is None:
        return "（认知信号暂不可用）"
    return signals.to_text()


def _fmt_blind_spots(probes: list[Any]) -> str:
    """计算当前可能存在的感知盲点——LLM 意识不到的缺失。

    不是命令，是让 LLM 自己决定是否需要关注这些潜在盲区。
    """
    coverage_tags = {
        tag
        for p in probes
        for tag in normalize_probe_coverage_tags(getattr(p, "coverage_tags", []))
    }
    has_channel_health = "ops:channel_health" in coverage_tags
    has_api_quota = "ops:api_quota" in coverage_tags
    has_git = "workspace:git_state" in coverage_tags

    gaps = []
    if not has_channel_health:
        gaps.append("- 关键外部通道健康未监控 → 依赖链路中断时你可能无法及时感知（例如消息网关/API 代理不可用）")
    if not has_api_quota:
        gaps.append("- API 调用量/额度未追踪 → 你可能在悄悄耗尽配额而不自知")
    if not has_git:
        gaps.append("- git 变更未追踪 → evolution 改了代码你不知道改了什么")

    if not gaps:
        return "当前感知覆盖良好，暂无明显盲点。"

    coverage_legend = "；".join(f"{tag}={desc}" for tag, desc in PROBE_COVERAGE_HINTS.items())
    return (
        "以下是你当前**没有在监控**的东西——不是要求你立即行动，只是提醒你可能忽略了：\n"
        + "\n".join(gaps)
        + f"\n\n可用 coverage_tags: {coverage_legend}"
    )


def _fmt_probe_sensors(probes: list[Any]) -> str:
    """将当前已部署的探针传感器网络格式化为 LLM 可读的感知面板。

    每个探针显示：状态 / 名称 / 部署目的 / 执行规格 / 最近读数。
    让 LLM 随时知道自己的感知网络状态及每个探针的意义。
    """
    if not probes:
        return (
            "⚠️ 你目前没有部署任何探针。探针是你的『感知触手』——采集外部信息，结果自动注入工作记忆。\n"
            "建议安装以下自我监控探针（用 probe.install）：\n"
            "  1. 磁盘使用率 → kind=shell spec='df -h / | tail -1' trigger=interval:600 purpose='磁盘超85%需清理' coverage_tags=[]\n"
            "  2. 内存 → kind=shell spec='free -m | grep Mem' trigger=interval:300 purpose='内存压力预警' coverage_tags=[]\n"
            "  3. 自身进程 → kind=shell spec='ps aux | grep lingzhou | grep -v grep | wc -l' trigger=interval:120 purpose='确认自身存活' coverage_tags=[]\n"
            "  4. 外部通道健康 → kind=shell spec='curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8080/health' trigger=interval:300 purpose='关键通道健康，非200说明链路异常' coverage_tags=['ops:channel_health']\n"
        )
    lines: list[str] = [
        "探针结果不是绝对真相：confidence<0.60 或标记为布放可疑时，先校验探针布放（spec/target/trigger），再据此决策。",
        "盲点推断只读取显式 coverage_tags，不再从 purpose/spec 猜测；未声明 coverage_tags 的探针不会计入覆盖。",
    ]
    for p in probes:
        mark = "✓" if p.enabled else "⊘"
        trigger_desc = p.trigger or "manual"
        alert_mark = " 🔔" if p.alert_expr else ""
        confidence = getattr(p, "last_confidence", None)
        confidence_mark = ""
        if isinstance(confidence, (int, float)):
            confidence_mark = f" confidence={float(confidence):.2f}"
        suspect_mark = " ⚠️布放可疑" if getattr(p, "last_suspect", False) else ""
        # 目的说明
        purpose_line = f"  └ 目的: {p.purpose}" if getattr(p, "purpose", "") else ""
        # 最近读数
        reading_line = ""
        if p.last_run_at:
            t = p.last_run_at
            if p.last_error:
                reading_line = f"  └ @{t} ❌ {p.last_error}"
            elif p.last_result:
                result_text = p.last_result.strip().replace("\n", " ")
                reading_line = f"  └ @{t} → {result_text}"
            else:
                reading_line = f"  └ @{t} (无输出)"
        else:
            reading_line = "  └ 尚未执行"
        conf_reason = str(getattr(p, "last_confidence_reason", "") or "").strip()
        conf_line = ""
        if conf_reason:
            conf_line = f"  └ 可信度依据: {conf_reason}"
        alert_line = ""
        if getattr(p, "last_alerted", False):
            detail = str(getattr(p, "last_alert_detail", "") or "").strip()
            alert_line = f"  └ 🔔 上次告警: {detail}" if detail else "  └ 🔔 上次告警已触发"
        coverage_tags = normalize_probe_coverage_tags(getattr(p, "coverage_tags", []))
        coverage_line = (
            f"  └ coverage: {', '.join(coverage_tags)}"
            if coverage_tags else
            "  └ coverage: （未声明，不计入盲点覆盖）"
        )
        header = (
            f"  {mark} [{p.name}] {p.kind}/{trigger_desc} →{p.data_back}{alert_mark}"
            f"{confidence_mark}{suspect_mark}"
        )
        entry = header
        if purpose_line:
            entry += "\n" + purpose_line
        entry += "\n" + coverage_line
        entry += "\n" + reading_line
        if alert_line:
            entry += "\n" + alert_line
        if conf_line:
            entry += "\n" + conf_line
        lines.append(entry)
    return "\n".join(lines)


__all__ = [
    "_short_skill_desc",
    "_fmt_skill_catalog",
    "_fmt_primary_skill",
    "_fmt_skills",
    "_fmt_cognitive_signals",
    "_fmt_blind_spots",
    "_fmt_probe_sensors",
]
