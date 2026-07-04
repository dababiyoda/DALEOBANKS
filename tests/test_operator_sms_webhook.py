"""Security tests for the inbound operator SMS webhook: it is an operator
command surface and must not be spoofable."""

import base64
import hashlib
import hmac
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from db.models import ApprovalRequest
from db.session import get_db_session, init_db
from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances

URL = "https://example.com/api/operator/sms"


class FakeRequest:
    def __init__(self, params: dict, signature: str):
        self._body = urlencode(params).encode()
        self.headers = {"X-Twilio-Signature": signature}
        self.url = URL

    async def body(self):
        return self._body


def _sign(params: dict, token: str) -> str:
    payload = URL + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()


async def test_invalid_signature_is_rejected_and_ledgered(tmp_path, monkeypatch):
    init_db()
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "real-token")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", URL)
    monkeypatch.setenv("OPERATOR_PHONE", "+15550001111")

    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module
        from services.operator_line import OperatorLine
        from services.ledger import KillSwitch

        line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
        with get_db_session() as session:
            pending = line.request_approval(session, kind="publish", summary="Ship?")

        params = {"Body": f"YES {pending.code}", "From": "+15550001111"}
        forged = FakeRequest(params, signature=_sign(params, "attacker-token"))

        with pytest.raises(HTTPException) as exc_info:
            await app_module.operator_sms_webhook(forged)
        assert exc_info.value.status_code == 403

        # No decision was made and the rejection is in the security ledger.
        with get_db_session() as session:
            assert session.query(ApprovalRequest).first().status == "pending"
        rejections = ledger.replay("operator_sms_rejected")
        assert rejections and rejections[-1]["payload"]["reason"] == "bad_signature"
    finally:
        reset_shared_instances()


async def test_valid_signature_but_unknown_sender_is_rejected(tmp_path, monkeypatch):
    init_db()
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "real-token")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", URL)
    monkeypatch.setenv("OPERATOR_PHONE", "+15550001111")

    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        params = {"Body": "FREEZE", "From": "+19998887777"}  # not the operator
        request = FakeRequest(params, signature=_sign(params, "real-token"))

        with pytest.raises(HTTPException) as exc_info:
            await app_module.operator_sms_webhook(request)
        assert exc_info.value.status_code == 403
        rejections = ledger.replay("operator_sms_rejected")
        assert rejections and rejections[-1]["payload"]["reason"] == "unknown_sender"
    finally:
        reset_shared_instances()


async def test_signed_operator_command_executes(tmp_path, monkeypatch):
    init_db()
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "real-token")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", URL)
    monkeypatch.setenv("OPERATOR_PHONE", "+15550001111")

    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module
        from services.operator_line import OperatorLine, set_operator_line
        from services.ledger import KillSwitch

        line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
        set_operator_line(line)
        with get_db_session() as session:
            pending = line.request_approval(session, kind="publish", summary="Ship?")

        params = {"Body": f"YES {pending.code}", "From": "+15550001111"}
        request = FakeRequest(params, signature=_sign(params, "real-token"))

        response = await app_module.operator_sms_webhook(request)
        assert response.media_type == "application/xml"
        assert b"Approved" in response.body

        with get_db_session() as session:
            assert session.query(ApprovalRequest).first().status == "approved"
    finally:
        set_operator_line(None)
        reset_shared_instances()
