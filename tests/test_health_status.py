"""The health endpoint must answer the operator's first question — is this
thing safe right now? — not just "is the process up"."""

from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances


async def test_health_reports_safe_runtime_status(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    ledger.record("boot", {})
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        response = await app_module.health_check()
        assert response["ok"] is True
        assert response["live"] is False  # the safe default, reported honestly
        assert response["crisis_paused"] in (True, False, None)
        assert response["ledger_ok"] is True
        assert response["ledger_broken_at"] is None
    finally:
        reset_shared_instances()


async def test_health_reports_broken_ledger_chain(tmp_path):
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

        response = await app_module.health_check()
        assert response["ledger_ok"] is False  # tampering is visible, not hidden
    finally:
        reset_shared_instances()
