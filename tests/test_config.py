"""Configuration defaults and safety checks."""

from __future__ import annotations

import importlib

import pytest

import config as config_module


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove configuration-related environment variables for a clean test."""
    for key in [
        "LIVE",
        "GOAL_MODE",
        "WEIGHTS_IMPACT",
        "WEIGHTS_REVENUE",
        "WEIGHTS_AUTHORITY",
        "WEIGHTS_FAME",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_live_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the agent ships with LIVE mode disabled by default."""
    _clear_env(monkeypatch)
    importlib.reload(config_module)
    cfg = config_module.get_config()

    assert cfg.LIVE is False
    assert cfg.GOAL_MODE == "IMPACT"


def test_goal_weights_have_impact_bias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Weights in IMPACT mode should match the documented defaults."""
    _clear_env(monkeypatch)
    importlib.reload(config_module)
    cfg = config_module.get_config()

    impact_weights = cfg.GOAL_WEIGHTS["IMPACT"]
    assert abs(impact_weights["alpha"] - 0.40) < 1e-6
    assert abs(impact_weights["beta"] - 0.30) < 1e-6
    assert abs(impact_weights["gamma"] - 0.20) < 1e-6
    assert abs(impact_weights["lambda"] - 0.10) < 1e-6

    # Ensure other modes exist for operator toggles.
    for key in ("FAME", "REVENUE", "AUTHORITY", "MONETIZE"):
        assert key in cfg.GOAL_WEIGHTS
