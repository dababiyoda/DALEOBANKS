"""Tests for measured revenue: conversions beat estimates."""

from datetime import datetime, timedelta, UTC

from db.models import Conversion, Redirect
from db.session import get_db_session, init_db
from services.analytics import AnalyticsService
from services.kpi import KPIService
from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances


def test_revenue_prefers_recorded_conversions():
    init_db()
    analytics = AnalyticsService()

    with get_db_session() as session:
        # Clicks that would estimate 100 * 0.05 = $5.00 under the old math.
        session.add(Redirect(label="pilot", target_url="https://x.test", clicks=100))
        session.add(Conversion(value=29.0))
        session.add(Conversion(value=13.5))
        # An old conversion outside the 24h window.
        session.add(Conversion(value=99.0, occurred_at=datetime.now(UTC) - timedelta(days=3)))
        session.commit()

        assert analytics.calculate_revenue_per_day(session) == 42.5


def test_revenue_falls_back_to_estimate_when_no_conversions_exist():
    init_db()
    analytics = AnalyticsService()

    with get_db_session() as session:
        session.add(Redirect(label="pilot", target_url="https://x.test", clicks=100))
        session.commit()
        assert analytics.calculate_revenue_per_day(session) == 5.0


def test_kpi_daily_revenue_uses_period_conversions():
    init_db()
    kpi = KPIService()
    now = datetime.now(UTC)

    with get_db_session() as session:
        session.add(Conversion(value=10.0, occurred_at=now - timedelta(hours=2)))
        session.add(Conversion(value=7.0, occurred_at=now - timedelta(days=5)))
        session.commit()

        value = kpi._calculate_daily_revenue(
            session, now - timedelta(days=1), now
        )
    assert value == 10.0


async def test_conversion_endpoint_records_and_ledgers(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        response = await app_module.record_conversion(
            app_module.ConversionRequest(
                value=49.0, redirect_id="r1", source="stripe",
            ),
            None,
        )
        assert response["success"] is True

        with get_db_session() as session:
            conversions = session.query(Conversion).all()
        assert len(conversions) == 1
        assert conversions[0].value == 49.0
        assert conversions[0].source == "stripe"

        events = ledger.replay("revenue_event")
        assert len(events) == 1
        assert events[0]["payload"]["value"] == 49.0

        listing = await app_module.list_conversions(limit=10, _=None)
        assert listing["count"] == 1
    finally:
        reset_shared_instances()


async def test_redirect_click_is_ledgered(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        with get_db_session() as session:
            redirect = Redirect(id="r42", label="pilot", target_url="https://example.com")
            session.add(redirect)
            session.commit()

        await app_module.handle_redirect("r42")

        clicks = ledger.replay("link_click")
        assert len(clicks) == 1
        assert clicks[0]["payload"] == {"redirect_id": "r42", "clicks": 1}
    finally:
        reset_shared_instances()
