"""Analytics calculations for J-score and impact weighting."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.analytics import AnalyticsService


@pytest.mark.asyncio
async def test_pull_metrics_no_client_returns_zero() -> None:
    service = AnalyticsService()
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []

    result = await service.pull_and_update_metrics(session, x_client=None)

    assert result == {"updated_count": 0}


def test_calculate_impact_score_uses_config_weights() -> None:
    service = AnalyticsService()
    service.config.GOAL_WEIGHTS["IMPACT"] = {
        "alpha": 1.0,
        "beta": 2.0,
        "gamma": 3.0,
        "lambda": 0.0,
    }

    service.calculate_fame_score = MagicMock(
        return_value={
            "fame_score": 2.0,
            "engagement_proxy": 0.0,
            "follower_delta": 0.0,
            "engagement_z": 0.0,
            "follower_z": 0.0,
        }
    )
    service.calculate_revenue_per_day = MagicMock(return_value=20.0)
    service.calculate_authority_signals = MagicMock(return_value=15.0)

    result = service.calculate_impact_score(MagicMock(), days=1)

    expected = round(1.0 * 2.0 + 2.0 * (20.0 / 10.0) + 3.0 * (15.0 / 10.0), 2)
    assert result["impact_score"] == expected
