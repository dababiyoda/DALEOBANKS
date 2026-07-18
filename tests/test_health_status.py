"""Health endpoints: the public probe stays minimal (no oracle for arming,
crisis, or tamper state); the authenticated safety endpoint answers the
operator's real question — is this thing safe right now?"""

from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances

_SAFETY_FIELDS = {"live", "crisis_paused", "crisis_reason", "ledger_ok", "ledger_broken_at"}


async def test_public_health_is_minimal_no_oracle(tmp_path):
    set_shared_instances(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))
    try:
        import app as app_module

        response = await app_module.health_check()
        assert response["ok"] is True
        assert "timestamp" in response
        # No arming, crisis, or ledger-tamper state on the public surface.
        assert _SAFETY_FIELDS.isdisjoint(response.keys())
    finally:
        reset_shared_instances()


async def test_safety_endpoint_reports_safe_runtime_status(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    ledger.record("boot", {})
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        response = await app_module.health_safety()
        assert response["ok"] is True
        assert response["live"] is False  # the safe default, reported honestly
        assert response["crisis_paused"] in (True, False, None)
        assert response["ledger_ok"] is True
        assert response["ledger_broken_at"] is None
    finally:
        reset_shared_instances()


async def test_safety_endpoint_reports_broken_ledger_chain(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = DecisionLedger(path=str(path))
    ledger.record("boot", {})
    ledger.record("second", {})
    # Corrupt the chain: tamper with the first entry on disk.
    lines = path.read_text().splitlines()
    lines[0] = lines[0].replace("boot", "tampered")
    path.write_text("\n".join(lines) + "\n")
    set_shared_instances(ledger=DecisionLedger(path=str(path)))
    try:
        import app as app_module

        response = await app_module.health_safety()
        assert response["ledger_ok"] is False  # tampering visible to the admin
    finally:
        reset_shared_instances()


def test_safety_endpoint_requires_admin_role():
    """The safety route must be behind the admin gate, not public."""
    import app as app_module

    routes = {r.path: r for r in app_module.app.routes if hasattr(r, "path")}
    assert "/api/health/safety" in routes
    # The public probe carries no dependencies; the safety route must.
    assert routes["/api/health/safety"].dependant.dependencies
    assert not routes["/api/health"].dependant.dependencies
