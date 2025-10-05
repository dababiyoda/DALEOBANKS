"""Analytics calculations for J-score and impact weighting."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.analytics import AnalyticsService
from db.session import get_db_session, init_db


def setup_function() -> None:
    """Reset the in-memory store before each test."""

    init_db()


@pytest.mark.asyncio
async def test_pull_metrics_no_client_returns_zero() -> None:
    service = AnalyticsService()
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []

    result = await service.pull_and_update_metrics(session, x_client=None)

    assert result == {"updated_count": 0}


def test_calculate_impact_score_aggregates_structured_signals() -> None:
    service = AnalyticsService()

    with get_db_session() as session:
        service.record_pilot_acceptance(session, pilot_name="Solar pilot", accepted_by="City A")
        service.record_artifact_fork(session, artifact_name="Playbook", platform="github")
        service.record_artifact_fork(session, artifact_name="Playbook", platform="gitlab")
        service.record_coalition_partner(session, partner_name="Climate Org")
        service.record_citation(session, source_title="Energy Report", url="https://example.com/report")
        service.record_helpfulness_feedback(session, channel="x", rating=4.0, comment="Great help")
        session.commit()

        impact = service.calculate_impact_score(session, days=7)

    assert impact["components"]["pilots"]["count"] == 1
    assert impact["components"]["artifacts"]["count"] == 2
    assert impact["components"]["citations"]["count"] == 1
    assert impact["components"]["helpfulness"]["average_rating"] == 4.0
    assert impact["impact_score"] > 0
