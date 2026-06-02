"""core/judgment/decision/health_mixin.py — 模型健康与冷却。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from core.judgment.output import ModelHealth

if TYPE_CHECKING:
    from provider.base import Provider

_log = logging.getLogger("lingzhou.judgment")

# LLM 兜底分类仅识别以下标签（避免 LLM 自由发挥）
_VALID_LLM_CODES = frozenset({"config", "quota", "429", "402", "401", "403", "400", "timeout", "other"})

_LLM_CLASSIFY_PROMPT = """\
你是一个错误分类器。根据下面的错误信息，判断它属于哪种错误类型。
只能返回以下标签之一，不得输出任何其他内容：
config  — API key / credential 缺失或未配置
quota   — 配额耗尽
429     — 请求频率过高
402     — 余额不足或需要付款
401     — 鉴权失败
403     — 权限不足
400     — 请求格式错误
timeout — 超时
other   — 其他

错误信息：
{err_text}

标签："""


class ExecutorHealthMixin:
    _model_health: dict[str, ModelHealth]
    _provider_errors: dict[str, str]

    def _get_health(self, model_ref: str) -> ModelHealth:
        health = self._model_health.get(model_ref)
        if health is None:
            health = ModelHealth()
            self._model_health[model_ref] = health
        return health

    def _classify_error_code(self, err_text: str) -> str:
        """仅识别有明确结构信号的错误（HTTP 状态码、协议关键词）。
        语义性错误（如配置缺失）留给 LLM 兜底感知，不在此做关键词枚举。
        """
        text = (err_text or "").lower()
        # quota 超限：先于 429 独立识别，部分 provider 通过 403/400 返回
        if "quota" in text and any(
            m in text for m in ("exceeded", "exhausted", "limit", "超限", "超额", "insufficient")
        ):
            return "quota"
        if " 429 " in f" {text} " or "too many requests" in text:
            return "429"
        if " 402 " in f" {text} " or "payment required" in text or "insufficient balance" in text:
            return "402"
        if " 401 " in f" {text} " or "unauthorized" in text:
            return "401"
        if " 403 " in f" {text} " or "forbidden" in text:
            return "403"
        if " 400 " in f" {text} " or "bad request" in text:
            return "400"
        if "readtimeout" in text or "timeout" in text:
            return "timeout"
        return "other"

    def _cooldown_seconds(self, code: str, failure_streak: int) -> float:
        streak = max(1, failure_streak)
        # 配置/quota 类错误与 streak 无关，等人修配置或等配额重置
        if code == "config":
            return 3600.0
        if code == "quota":
            return 3600.0
        if code == "429":
            return min(180.0, 30.0 * streak)
        if code == "402":
            return 86400.0
        if code in {"401", "403"}:
            return min(300.0, 120.0 + 30.0 * (streak - 1))
        if code == "400":
            return min(180.0, 45.0 * streak)
        if code == "timeout":
            # 首次 30s，之后线性增长，上限 120s
            return min(120.0, 30.0 * streak)
        return min(90.0, 15.0 * streak)

    def _mark_model_failure(self, model_ref: str, err_text: str) -> None:
        code = self._classify_error_code(err_text)
        health = self._get_health(model_ref)
        health.failure_streak += 1
        health.last_error = err_text
        health.last_code = code
        health.cooldown_until = time.time() + self._cooldown_seconds(code, health.failure_streak)
        self._provider_errors[model_ref] = health.last_error
        # 规则无法识别时，fire-and-forget 用 LLM 补充感知，回写更精确的 code
        if code == "other":
            self._schedule_llm_classify(model_ref, err_text)

    def _pick_classify_provider(self, failed_model_ref: str) -> Provider | None:
        """挑一个与 failed_model_ref 不同、且当前可用的 provider 做分类调用。主 provider 最优先。"""
        primary: Provider | None = getattr(self, "_provider", None)
        primary_ref: str = getattr(getattr(self, "_cfg", None), "model", "")
        if primary is not None and primary_ref != failed_model_ref:
            return primary
        for model_ref, health in self._model_health.items():
            if model_ref == failed_model_ref:
                continue
            if health.cooldown_until > time.time():
                continue
            try:
                return self._find_or_create_provider(model_ref)  # type: ignore[attr-defined]
            except Exception:
                continue
        return primary  # 最后兑底（分类失败也无副作用）

    def _schedule_llm_classify(self, model_ref: str, err_text: str) -> None:
        """异步 fire-and-forget：用 LLM 对 other 类错误重新分类并回写。同一 model_ref 同一时刻只跑一个分类任务。"""
        pending: set[str] = getattr(self, "_pending_llm_classify", None)  # type: ignore[assignment]
        if pending is None:
            pending = set()
            self._pending_llm_classify = pending  # type: ignore[attr-defined]
        if model_ref in pending:
            return  # 已有进行中的分类任务，跳过
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # 非 async 上下文，跳过
        pending.add(model_ref)
        loop.create_task(self._llm_classify_and_rewrite(model_ref, err_text))

    async def _llm_classify_and_rewrite(self, model_ref: str, err_text: str) -> None:
        try:
            provider = self._pick_classify_provider(model_ref)
            if provider is None:
                return
            from provider.base import Message

            prompt = _LLM_CLASSIFY_PROMPT.format(err_text=err_text[:800])
            reply = await provider.chat(
                [Message(role="user", content=prompt)],
                temperature=0.0,
            )
            code = reply.strip().lower().split()[0] if reply.strip() else "other"
            if code not in _VALID_LLM_CODES:
                code = "other"
            if code == "other":
                return  # 没有改善，不回写
            health = self._get_health(model_ref)
            # 只有仍处于冷却状态时才回写（避免覆盖已恢复的健康状态）
            if health.cooldown_until > time.time():
                health.last_code = code
                health.cooldown_until = time.time() + self._cooldown_seconds(code, health.failure_streak)
                _log.info("[health] LLM 重分类 model=%s other→%s", model_ref, code)
        except Exception as e:
            _log.debug("[health] LLM 分类失败，忽略: %s", e)
        finally:
            getattr(self, "_pending_llm_classify", set()).discard(model_ref)

    def _mark_model_success(self, model_ref: str) -> None:
        health = self._get_health(model_ref)
        health.failure_streak = 0
        health.last_error = ""
        health.last_code = ""
        health.cooldown_until = 0.0
        self._provider_errors.pop(model_ref, None)

    def _is_model_available(self, model_ref: str) -> bool:
        return self._get_health(model_ref).cooldown_until <= time.time()
