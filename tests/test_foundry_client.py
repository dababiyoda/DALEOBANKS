import json

import pytest

from services.foundry_client import (
    FoundryClientError,
    FoundryEnvelopeClient,
    validate_foundry_envelope,
)
from services.ledger import DecisionLedger


class FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()
        self.headers = {}

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


def envelope(packet_id="packet-1", **overrides):
    payload = {
        "schema_version": "0.1",
        "source_organ": "WealthMachineIntelligence",
        "opportunity_packet_id": packet_id,
        "packet_digest": "sha256:" + "a" * 64,
        "assessment_id": "assessment-1",
        "assessment_digest": "sha256:" + "b" * 64,
        "observed_pain": "proof is unreliable",
        "core_thesis": "verified proof may reduce disputes",
        "go_no_go": "go",
        "opportunity_score": 0.8,
        "market_alignment": 0.7,
        "risk_level": "medium",
        "legal_readiness": "standard",
        "product_hypothesis": "proof audit",
        "pricing_hypothesis": "$500 test",
        "validation_plan": ["sell one paid diagnostic"],
        "adversarial_cases": [],
        "reasons": [],
        "evidence_refs": ["sha256:" + "c" * 64],
        **foundation(),
        "legal_operator": "alfonso_lopez",
        "missing_fields": [],
        "blocking_reasons": [],
        "ready_for_foundry": True,
        "requires_human_approval": True,
        "execution_authority": "none",
    }
    payload.update(overrides)
    return payload


def client(tmp_path):
    return FoundryEnvelopeClient(
        ledger=DecisionLedger(path=str(tmp_path / "foundry-ledger.jsonl")),
    )


def test_client_posts_foundation_to_packet_bound_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    monkeypatch.setenv("WEALTHMACHINE_INTAKE_TOKEN", "secret")
    monkeypatch.delenv("WEALTHMACHINE_SIGNING_KEY", raising=False)
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data.decode())
        return FakeResponse(envelope())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = client(tmp_path).request("packet-1", foundation())
    assert seen["url"] == "http://wealthmachine.local/api/ventures/packet-1/foundry-envelope"
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["buyer"] == "Named Buyer LLC"
    assert result["ready_for_foundry"] is True
    assert result["execution_authority"] == "none"


def test_ready_envelope_cannot_hide_missing_or_blocking_state():
    with pytest.raises(FoundryClientError):
        validate_foundry_envelope(envelope(missing_fields=["buyer"]), "packet-1")
    with pytest.raises(FoundryClientError):
        validate_foundry_envelope(envelope(blocking_reasons=["fraud"]), "packet-1")


def test_authority_widening_and_packet_substitution_are_refused():
    with pytest.raises(FoundryClientError):
        validate_foundry_envelope(envelope(execution_authority="launch"), "packet-1")
    with pytest.raises(FoundryClientError):
        validate_foundry_envelope(envelope(packet_id="packet-2"), "packet-1")


def test_invalid_provenance_and_human_boundary_are_refused():
    with pytest.raises(FoundryClientError):
        validate_foundry_envelope(envelope(packet_digest="not-a-hash"), "packet-1")
    with pytest.raises(FoundryClientError):
        validate_foundry_envelope(envelope(requires_human_approval=False), "packet-1")


def test_missing_url_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("WEALTHMACHINE_URL", raising=False)
    with pytest.raises(FoundryClientError):
        client(tmp_path).request("packet-1", foundation())


def test_success_is_recorded_without_execution_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    monkeypatch.delenv("WEALTHMACHINE_SIGNING_KEY", raising=False)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: FakeResponse(envelope()),
    )
    instance = client(tmp_path)
    instance.request("packet-1", foundation())
    entries = instance.ledger.entries()
    event = next(entry for entry in entries if entry["event"] == "foundry_underwriting_envelope")
    assert event["payload"]["execution_authority"] == "none"
    assert event["payload"]["ready_for_foundry"] is True
    assert instance.ledger.verify_chain()[0] is True
