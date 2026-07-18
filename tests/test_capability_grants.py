"""CapabilityGrant: authority as narrow, expiring, revocable capabilities.
Grants mint only from human approvals; validation happens at execution
time; expired, revoked, mismatched, exhausted, replayed, or over-budget
grants fail closed; a broken ledger disarms consumption entirely."""

from datetime import datetime, timedelta, UTC

import pytest

from db.models import ApprovalRequest, CapabilityGrant
from db.session import get_db_session, init_db
from services.capability import CapabilityError, CapabilityService
from services.ledger import DecisionLedger, KillSwitch, set_shared_instances, reset_shared_instances
from services.operator_line import OperatorLine


def _setup(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    service = CapabilityService(ledger=ledger)
    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    return ledger, service, line


def _approved_request(session, line):
    request = line.request_approval(
        session, kind="publish", summary="Publish one educational post",
        payload={"draft_id": "draft-1"},
        strongest_objection="Audience may read it as advice; disclosure required",
    )
    line.handle_command(session, f"YES {request.code}")
    return request


def test_grant_mints_only_from_approved_requests(tmp_path):
    ledger, service, line = _setup(tmp_path)
    try:
        with get_db_session() as session:
            pending = line.request_approval(
                session, kind="publish", summary="Not yet approved",
                payload={"draft_id": "draft-x"},
            )
            with pytest.raises(CapabilityError):
                service.mint_from_approval(
                    session, pending.id, "publish_post", "publish draft-x", "draft-x",
                )
            approved = _approved_request(session, line)
            grant = service.mint_from_approval(
                session, approved.id, "publish_post", "publish draft-1", "draft-1",
            )
        assert grant.maximum_uses == 1
        assert grant.expires_at is not None
        assert ledger.replay("capability_granted")
    finally:
        reset_shared_instances()


def test_valid_one_time_grant_succeeds_then_replay_fails(tmp_path):
    ledger, service, line = _setup(tmp_path)
    try:
        with get_db_session() as session:
            approved = _approved_request(session, line)
            grant = service.mint_from_approval(
                session, approved.id, "publish_post", "publish draft-1", "draft-1",
            )
            # Mocked execution: validate-and-consume, no external action.
            consumed = service.validate_and_consume(
                session, grant.id, "publish_post", "draft-1",
            )
            assert consumed.uses_consumed == 1
            # Replay: the same grant a second time fails closed.
            with pytest.raises(CapabilityError):
                service.validate_and_consume(session, grant.id, "publish_post", "draft-1")
        assert ledger.replay("capability_consumed")
        assert any(e["payload"]["reason"] == "exhausted"
                   for e in ledger.replay("capability_rejected"))
    finally:
        reset_shared_instances()


def test_expired_revoked_and_mismatched_grants_fail_closed(tmp_path):
    ledger, service, line = _setup(tmp_path)
    try:
        with get_db_session() as session:
            approved = _approved_request(session, line)

            expired = service.mint_from_approval(
                session, approved.id, "publish_post", "publish draft-1", "draft-1",
            )
            expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            with pytest.raises(CapabilityError):
                service.validate_and_consume(session, expired.id, "publish_post", "draft-1")

            revoked = service.mint_from_approval(
                session, approved.id, "publish_post", "publish draft-1", "draft-1",
            )
            service.revoke(session, revoked.id, reason="operator changed mind")
            with pytest.raises(CapabilityError):
                service.validate_and_consume(session, revoked.id, "publish_post", "draft-1")

            wrong = service.mint_from_approval(
                session, approved.id, "publish_post", "publish draft-1", "draft-1",
            )
            with pytest.raises(CapabilityError):  # wrong action
                service.validate_and_consume(session, wrong.id, "send_dm", "draft-1")
            with pytest.raises(CapabilityError):  # wrong resource
                service.validate_and_consume(session, wrong.id, "publish_post", "draft-999")

            budget = service.mint_from_approval(
                session, approved.id, "spend", "spend on one experiment", "exp-1",
                max_cost=25.0,
            )
            with pytest.raises(CapabilityError):  # over budget
                service.validate_and_consume(session, budget.id, "spend", "exp-1", cost=26.0)
        assert ledger.replay("capability_revoked")
    finally:
        reset_shared_instances()


def test_broken_ledger_disarms_consumption(tmp_path):
    path = tmp_path / "l.jsonl"
    ledger, service, line = _setup(tmp_path)
    try:
        with get_db_session() as session:
            approved = _approved_request(session, line)
            grant = service.mint_from_approval(
                session, approved.id, "publish_post", "publish draft-1", "draft-1",
            )
        # Tamper with the chain on disk; consumption must fail closed.
        lines = path.read_text().splitlines()
        lines[0] = lines[0].replace("operator_prompted", "tampered_event")
        path.write_text("\n".join(lines) + "\n")
        broken = CapabilityService(ledger=DecisionLedger(path=str(path)))
        with get_db_session() as session:
            with pytest.raises(CapabilityError):
                broken.validate_and_consume(session, grant.id, "publish_post", "draft-1")
    finally:
        reset_shared_instances()


def test_grants_never_widen_standing_autonomy(tmp_path):
    """A grant covers exactly one scope; approval elsewhere grants nothing
    here, and consuming a grant leaves LIVE untouched."""
    from config import get_config
    ledger, service, line = _setup(tmp_path)
    try:
        live_before = get_config().LIVE
        with get_db_session() as session:
            approved = _approved_request(session, line)
            grant = service.mint_from_approval(
                session, approved.id, "publish_post", "publish draft-1", "draft-1",
                named_targets=["lane-main"],
            )
            with pytest.raises(CapabilityError):  # unnamed target refused
                service.validate_and_consume(
                    session, grant.id, "publish_post", "draft-1", target="lane-other",
                )
            service.validate_and_consume(
                session, grant.id, "publish_post", "draft-1", target="lane-main",
            )
        assert get_config().LIVE == live_before  # consuming never arms
    finally:
        reset_shared_instances()
