"""Truthful system-status projection for the dashboard.

Every field is derived from an observation taken now, or reported as
``unknown``/``unavailable``. Nothing here may default to a healthy value: a
dependency we cannot observe is not a dependency we know to be working.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Dict, Optional


def _memory_usage() -> str:
    """Peak resident memory of this process, or ``unknown``."""
    try:
        import resource
        import sys

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB, macOS reports bytes.
        mib = peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024
        return f"{mib:.1f} MB (peak RSS)"
    except Exception:
        return "unknown"


def _api_health(x_client: Any) -> str:
    if x_client is None:
        return "unavailable"
    try:
        return "healthy" if x_client.is_healthy() else "unavailable"
    except Exception:
        return "unknown"


def _rate_limits(x_client: Any) -> str:
    """``degraded`` when any X endpoint circuit breaker is open."""
    if x_client is None or not getattr(x_client, "client", None):
        return "unknown"
    breakers = getattr(x_client, "circuit_breakers", None)
    if not isinstance(breakers, dict):
        return "unknown"
    try:
        if any(breaker.is_open() for breaker in breakers.values()):
            return "degraded"
    except Exception:
        return "unknown"
    return "good"


def build_system_status(
    *,
    x_client: Any,
    config: Any,
    crisis_service: Any,
    uptime: Optional[Callable[[], str]] = None,
    scheduler_status: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    try:
        crisis_state = "PAUSED" if crisis_service.is_paused() else "NORMAL"
        crisis_reason = crisis_service.reason
    except Exception:
        crisis_state, crisis_reason = "UNKNOWN", "unavailable"

    try:
        scheduler = scheduler_status() if scheduler_status else {"running": None}
    except Exception:
        scheduler = {"running": None}

    try:
        uptime_value = uptime() if uptime else "unknown"
    except Exception:
        uptime_value = "unknown"

    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "api_health": _api_health(x_client),
        "rate_limits": _rate_limits(x_client),
        "ethics_guard": "active" if getattr(config, "RAGEBAIT_GUARD", False) else "disabled",
        "memory_usage": _memory_usage(),
        "uptime": uptime_value,
        "live_mode": bool(getattr(config, "LIVE", False)),
        "crisis_state": crisis_state,
        "crisis_reason": crisis_reason,
        "scheduler": scheduler,
    }


__all__ = ["build_system_status"]
