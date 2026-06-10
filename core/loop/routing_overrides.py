"""Helpers for runtime routing override persistence and validation."""

from __future__ import annotations

from typing import Any

_ROUTING_TIERS = frozenset({"reader", "reasoner", "repair"})


def _valid_model_ref(model_ref: str) -> bool:
    provider, sep, model_id = str(model_ref or "").partition("/")
    if not provider or not sep or not model_id:
        return False
    if model_id.strip().isdigit():
        return False
    try:
        from provider.catalog import lookup_model_ref

        return lookup_model_ref(model_ref) is not None
    except Exception:
        return True


def normalize_routing_overrides(payload: Any) -> dict[str, str] | None:
    """Return validated tier -> model overrides, accepting the legacy flat JSON shape."""
    if not isinstance(payload, dict):
        return None
    raw_overrides = payload.get("overrides") if isinstance(payload.get("overrides"), dict) else payload
    overrides = {
        str(tier): str(model_ref).strip()
        for tier, model_ref in raw_overrides.items()
        if tier in _ROUTING_TIERS
        and isinstance(model_ref, str)
        and _valid_model_ref(model_ref)
    }
    return overrides or None


def routing_overrides_meta(*, source: str, decision_basis: str = "") -> dict[str, str]:
    meta = {"source": str(source or "unknown")}
    basis = " ".join(str(decision_basis or "").split())
    if basis:
        meta["decision_basis"] = basis[:240]
    return meta
