"""Tests for the operator approval line: command semantics and safety rules."""

import base64
import hashlib
import hmac

from config import get_config, update_config
from db.models import ApprovalRequest, SelfSignal
from db.session import get_db_session, init_db
from services.ledger import DecisionLedger, KillSwitch
from services.operator_line import OperatorLine, validate_twilio_signature


def _line(tmp_path) -> OperatorLine:
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    return OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))


def test_request_approval_creates_pending_and_ledgers(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        request = line.request_approval(
            session, kind="publish", summary="Post the grid thread?",
            payload={"content": "draft"}, rationale="strong claims",
        )
        stored = session.query(ApprovalRequest).all()

    assert stored and stored[0].id == request.id
    assert stored[0].status == "pending"
    prompts = line.ledger.replay("operator_prompted")
    assert prompts and prompts[-1]["payload"]["id"] == request.id
    assert prompts[-1]["payload"]["sms_sent"] is False  # no Twilio configured


def test_yes_approves_the_single_pending_request(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        request = line.request_approval(session, kind="publish", summary="Ship it?")
        result = line.handle_command(session, "YES", via="sms")
        assert result["ok"] is True
        assert result["request_id"] == request.id
        assert session.query(ApprovalRequest).first().status == "approved"
        # YES covers only that request — nothing remains approved-in-advance.
        again = line.handle_command(session, "YES", via="sms")
        assert again["ok"] is False


def test_bare_yes_refuses_when_ambiguous(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        line.request_approval(session, kind="publish", summary="First?")
        line.request_approval(session, kind="publish", summary="Second?")
        result = line.handle_command(session, "YES")
        assert result["ok"] is False
        statuses = {r.status for r in session.query(ApprovalRequest).all()}
        assert statuses == {"pending"}  # ambiguity approves nothing


def test_yes_with_id_prefix_targets_exactly_one(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        first = line.request_approval(session, kind="publish", summary="First?")
        second = line.request_approval(session, kind="publish", summary="Second?")
        result = line.handle_command(session, f"YES {first.id[:8]}")
        assert result["ok"] is True

        by_id = {r.id: r.status for r in session.query(ApprovalRequest).all()}
        assert by_id[first.id] == "approved"
        assert by_id[second.id] == "pending"


def test_no_and_hold_and_edit(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        request = line.request_approval(session, kind="publish", summary="Ship?")
        line.handle_command(session, f"HOLD {request.id[:8]}")
        assert session.query(ApprovalRequest).first().status == "held"

        # Held requests can still be decided by id.
        line.handle_command(session, f"NO {request.id[:8]}")
        assert session.query(ApprovalRequest).first().status == "rejected"

        second = line.request_approval(session, kind="publish", summary="Other?")
        result = line.handle_command(session, "EDIT Use this wording instead")
        assert result["ok"] is True
        stored = [r for r in session.query(ApprovalRequest).all() if r.id == second.id][0]
        assert stored.status == "edited"
        assert stored.payload["operator_edit"] == "Use this wording instead"


def test_freeze_disarms_outbound_immediately(tmp_path):
    init_db()
    line = _line(tmp_path)
    update_config(LIVE=True)
    try:
        with get_db_session() as session:
            result = line.handle_command(session, "FREEZE", via="sms")
        assert result["ok"] is True
        assert get_config().LIVE is False
        commands = line.ledger.replay("operator_command")
        assert commands[-1]["payload"]["command"] == "FREEZE"
    finally:
        update_config(LIVE=False)


def test_opinion_becomes_self_signal_not_doctrine(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        result = line.handle_command(
            session, "OPINION: lean harder into transmission reform", via="sms"
        )
        signals = session.query(SelfSignal).all()

    assert result["ok"] is True
    assert len(signals) == 1
    assert signals[0].text == "lean harder into transmission reform"
    assert signals[0].source == "operator_opinion"
    assert "weigh" in result["reply"]  # a signal to weigh, never to obey


def test_why_explains_the_request(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        line.request_approval(
            session, kind="publish", summary="Post the claim?",
            payload={"content": "Grid queues doubled since 2020."},
            rationale="unsourced statistic",
        )
        result = line.handle_command(session, "WHY")

    assert result["ok"] is True
    assert "unsourced statistic" in result["reply"]
    assert "Grid queues doubled" in result["reply"]


def test_unknown_command_returns_help(tmp_path):
    init_db()
    line = _line(tmp_path)
    with get_db_session() as session:
        result = line.handle_command(session, "LAUNCH THE NUKES")
    assert result["ok"] is False
    assert "YES" in result["reply"] and "FREEZE" in result["reply"]


def test_twilio_signature_validation(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret-token")
    url = "https://example.com/api/operator/sms"
    params = {"Body": "YES", "From": "+15550001111"}
    payload = url + "Body" + "YES" + "From" + "+15550001111"
    good = base64.b64encode(
        hmac.new(b"secret-token", payload.encode(), hashlib.sha1).digest()
    ).decode()

    assert validate_twilio_signature(url, params, good) is True
    assert validate_twilio_signature(url, params, "forged") is False
    assert validate_twilio_signature(url, params, "") is False
