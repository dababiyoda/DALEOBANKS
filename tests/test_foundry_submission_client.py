import json

import pytest

from services.bridge_security import BridgeSecurityError, build_headers
from services.foundry_client import (
    FoundryClientError,
    FoundryEnvelopeClient,
    validate_foundry_submission_receipt,
)
from services.ledger import DecisionLedger
from services.venture_protocol import SCHEMA_VERSION

APPROVAL_HASH = "sha256:" + "f" * 64


class FakeResponse:
    def __init__(self, payload, headers=None):
        self._raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.headers = headers or {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def foundation():
    return {
        "buyer": "Named Buyer LLC",
        "beneficiary": "operations team",
        "pain_owner": "VP Operations",
        "budget_owner": "CFO",
        "recurring_transaction": "approve and settle verified service",
        "trapped_value_usd": 50000,
        "accepted_artifact": "signed verification receipt",
        "external_consequence": "buyer changes settlement decision",
        "lawful_path": "paid diagnostic under reviewed agreement",
    }


def receipt(**overrides):
    payload = {
        "kernel_receipt": {
            "status": "accepted_for_foundry_analysis",
            "opportunity_id": "packet-1:assessment-1",
            "opportunity_digest": "sha256:" + "e" * 64,
            "duplicate": False,
            "requires_human_approval": True,
            "execution_authority": "none",
        },
        "human_approval_record_hash": APPROVAL_HASH,
        "requires_human_approval": True,
        "execution_authority": "none",
    }
    payload.update(overrides)
    return payload


def client(tmp_path):
    return FoundryEnvelopeClient(
        ledger=DecisionLedger(path=str(tmp_path / "submission-ledger.jsonl")),
    )


def test_submit_posts_foundation_and_approval_to_packet_bound_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    monkeypatch.delenv("WEALTHMACHINE_SIGNING_KEY", raising=False)
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode())
        seen["headers"] = {name.lower(): value for name, value in request.header_items()}
        return FakeResponse(receipt())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = client(tmp_path).submit("packet-1", foundation(), APPROVAL_HASH)
    assert seen["url"] == "http://wealthmachine.local/api/ventures/packet-1/submit-foundry"
    assert seen["body"]["foundation"]["buyer"] == "Named Buyer LLC"
    assert seen["body"]["human_approval_record_hash"] == APPROVAL_HASH
    assert seen["headers"]["x-service-identity"] == "daleobanks"
    assert result["kernel_receipt"]["execution_authority"] == "none"


def test_submission_receipt_cannot_widen_authority_or_swap_approval():
    bad_outer = receipt(execution_authority="launch")
    with pytest.raises(FoundryClientError):
        validate_foundry_submission_receipt(bad_outer, APPROVAL_HASH)

    bad_kernel = receipt()
    bad_kernel["kernel_receipt"] = dict(bad_kernel["kernel_receipt"], execution_authority="launch")
    with pytest.raises(FoundryClientError):
        validate_foundry_submission_receipt(bad_kernel, APPROVAL_HASH)

    with pytest.raises(FoundryClientError):
        validate_foundry_submission_receipt(
            receipt(human_approval_record_hash="sha256:" + "0" * 64),
            APPROVAL_HASH,
        )


def test_invalid_approval_hash_is_refused_before_network(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    called = False

    def fake_urlopen(request, timeout=None):
        nonlocal called
        called = True
        return FakeResponse(receipt())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(FoundryClientError):
        client(tmp_path).submit("packet-1", foundation(), "approval:unverified")
    assert called is False


def test_signed_response_is_verified_and_replay_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    monkeypatch.setenv("WEALTHMACHINE_SIGNING_KEY", "transport-test-key")
    payload = receipt()
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    response_headers = build_headers(
        raw,
        identity="wealthmachine",
        schema_version=SCHEMA_VERSION,
        idempotency_key="response-1",
        trace_id="packet-1",
    )

    class SignedResponse(FakeResponse):
        def __init__(self):
            self._raw = raw
            self.headers = response_headers

    response = SignedResponse()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: response,
    )
    instance = client(tmp_path)
    assert instance.submit("packet-1", foundation(), APPROVAL_HASH)["execution_authority"] == "none"
    with pytest.raises(BridgeSecurityError):
        instance.submit("packet-1", foundation(), APPROVAL_HASH)


def test_submission_is_recorded_in_tamper_evident_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    monkeypatch.delenv("WEALTHMACHINE_SIGNING_KEY", raising=False)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: FakeResponse(receipt()),
    )
    instance = client(tmp_path)
    instance.submit("packet-1", foundation(), APPROVAL_HASH)
    event = next(
        entry for entry in instance.ledger.entries()
        if entry["event"] == "foundry_kernel_submission"
    )
    assert event["payload"]["human_approval_record_hash"] == APPROVAL_HASH
    assert event["payload"]["execution_authority"] == "none"
    assert instance.ledger.verify_chain()[0] is True
