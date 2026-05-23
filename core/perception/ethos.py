"""core/perception/ethos.py — 价值层：EthosValues / EthosState + derive_ethos_state。

参考：Kohlberg (1969) 道德发展内化原则；McCloskey & Glucksberg (1978) 概念渐变
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.perception.emotion import clamp01


_ETHOS_DIMENSIONS = ("truth", "caution", "continuity", "curiosity", "care")


@dataclass
class EthosValues:
    truth: float = 0.65         # 诚实优先
    caution: float = 0.60       # 行动前先确认
    continuity: float = 0.60    # 维持任务连续性
    curiosity: float = 0.45     # 主动感知，不被动等待
    care: float = 0.55          # 对用户数据和状态负责


@dataclass
class EthosBias:
    """当前 tick 的行为倾向，用于候选动作预排名。"""
    prefer_verification: bool = False   # 优先验证类动作
    prefer_narrow_scope: bool = False   # 优先收窄范围
    preserve_continuity: bool = False   # 优先维持任务连续
    avoid_overclaiming: bool = False    # 避免过度承诺
    reasons: list[str] = field(default_factory=list[str])


@dataclass
class EthosState:
    values: EthosValues = field(default_factory=EthosValues)
    bias: EthosBias = field(default_factory=EthosBias)

    def __hash__(self) -> int:
        v = self.values
        b = self.bias
        return hash((
            v.truth, v.caution, v.continuity, v.curiosity, v.care,
            b.prefer_verification, b.prefer_narrow_scope,
            b.preserve_continuity, b.avoid_overclaiming,
        ))


def _resolve_ethos_seed_values(
    baseline: dict[str, float] | None,
    seed_values: dict[str, float] | None,
) -> tuple[dict[str, float], dict[str, float]]:
    base = baseline or seed_values or {}
    fallback = seed_values or baseline or {}
    missing = [key for key in _ETHOS_DIMENSIONS if key not in base and key not in fallback]
    if missing:
        raise ValueError(
            "derive_ethos_state requires explicit baseline or seed_values for ethos dimensions: "
            + ", ".join(missing)
        )
    return base, fallback


def derive_ethos_state(
    failure_count: int,
    high_error_streak: int,
    has_active_task: bool,
    has_next_step: bool,
    perception_trend: str,
    emotion_down_regulate_streak: int,
    baseline: dict[str, float] | None = None,
    seed_values: dict[str, float] | None = None,
    ema_alpha: float = 0.9,
    floor_truth: float = 0.50,
    floor_caution: float = 0.45,
    prefer_verification_caution_min: float = 0.70,
    prefer_verification_failure_count: int = 2,
    prefer_narrow_failure_count: int = 2,
    prefer_narrow_error_streak: int = 2,
    preserve_continuity_min: float = 0.70,
    avoid_overclaiming_down_regulate_streak: int = 2,
    failure_adjust_count: int = 1,
    failure_truth_delta: float = 0.10,
    failure_caution_delta: float = 0.10,
    failure_curiosity_delta: float = -0.08,
    high_error_adjust_streak: int = 2,
    high_error_truth_delta: float = 0.10,
    high_error_caution_delta: float = 0.12,
    high_error_care_delta: float = -0.08,
    active_task_continuity_delta: float = 0.12,
    next_step_continuity_delta: float = 0.08,
    next_step_care_delta: float = 0.06,
    recovering_curiosity_delta: float = 0.08,
    recovering_care_delta: float = 0.04,
) -> EthosState:
    """每 tick 从信号确定性推导 EthosState（含 EMA 基线混合）。

    注：以下信号→价值映射系数是初始默认值，可通过 evolution 机制进化。
    EMA 基线（soul:ethos_baseline）随每次经历缓慢漂移，是真正的"性格记忆"。

    ema_alpha / floor_truth / floor_caution 均从 cfg.soul.* 传入，不再硬编码。
    """
    base, fallback = _resolve_ethos_seed_values(baseline, seed_values)
    v = EthosValues(
        truth=float(base.get("truth", fallback["truth"])),
        caution=float(base.get("caution", fallback["caution"])),
        continuity=float(base.get("continuity", fallback["continuity"])),
        curiosity=float(base.get("curiosity", fallback["curiosity"])),
        care=float(base.get("care", fallback["care"])),
    )
    if failure_count >= failure_adjust_count:
        v.truth   = clamp01(v.truth   + failure_truth_delta)
        v.caution = clamp01(v.caution + failure_caution_delta)
        v.curiosity = clamp01(v.curiosity + failure_curiosity_delta)
    if high_error_streak >= high_error_adjust_streak:
        v.truth   = clamp01(v.truth   + high_error_truth_delta)
        v.caution = clamp01(v.caution + high_error_caution_delta)
        v.care    = clamp01(v.care    + high_error_care_delta)
    if has_active_task:
        v.continuity = clamp01(v.continuity + active_task_continuity_delta)
    if has_next_step:
        v.continuity = clamp01(v.continuity + next_step_continuity_delta)
        v.care       = clamp01(v.care       + next_step_care_delta)
    if perception_trend == "recovering":
        v.curiosity = clamp01(v.curiosity + recovering_curiosity_delta)
        v.care      = clamp01(v.care      + recovering_care_delta)
    # EMA 混合历史基线（演化速率由 ema_alpha 控制，从 cfg.soul.ethos_ema_alpha 传入）
    if baseline:
        a = ema_alpha
        v.truth      = clamp01(a * baseline.get("truth",      v.truth)      + (1-a) * v.truth)
        v.caution    = clamp01(a * baseline.get("caution",    v.caution)    + (1-a) * v.caution)
        v.continuity = clamp01(a * baseline.get("continuity", v.continuity) + (1-a) * v.continuity)
        v.curiosity  = clamp01(a * baseline.get("curiosity",  v.curiosity)  + (1-a) * v.curiosity)
        v.care       = clamp01(a * baseline.get("care",       v.care)       + (1-a) * v.care)
    # 运行时下限（防止极端场景下完全崩溃）
    v.truth   = max(v.truth,   floor_truth)
    v.caution = max(v.caution, floor_caution)

    bias = EthosBias()
    reasons: list[str] = []
    if v.caution > prefer_verification_caution_min or failure_count >= prefer_verification_failure_count:
        bias.prefer_verification = True
        reasons.append("谨慎度高，优先验证")
    if failure_count >= prefer_narrow_failure_count or high_error_streak >= prefer_narrow_error_streak:
        bias.prefer_narrow_scope = True
        reasons.append("多次失败，收窄操作范围")
    if v.continuity > preserve_continuity_min and has_active_task:
        bias.preserve_continuity = True
        reasons.append("任务连续性优先")
    if emotion_down_regulate_streak >= avoid_overclaiming_down_regulate_streak:
        bias.avoid_overclaiming = True
        reasons.append("情绪持续下调，避免过度承诺")
    bias.reasons = reasons
    return EthosState(values=v, bias=bias)
