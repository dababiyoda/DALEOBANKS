"""HTTP-mode contract tests for the WealthMachine bridge: the client must
target the intake endpoint WealthMachineIntelligence exposes, present the
optional shared token, validate the returned wire payload, and never let an
assessment arrive without requires_human_approval."""

import io
import json

import pytest

from db.models import OpportunityPacket
from services.ledger import DecisionLedger
from services.wealthmachine_client import WealthMachineClient


class _FakeResponse:
    def __init__(self, payload):
        self._body = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self._body

    def __exit__(self, *exc):
        return False


def _packet():
    return OpportunityPacket(
        source="daleobanks", source_ref="idea-1", core_thesis="thesis",
        evidence=["e1"], possible_offer="educational checklist",
        monetization_paths=["paid checklist"],
    )


def _client(tmp_path):
    return WealthMachineClient(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def _assessment_wire(packet, **overrides):
    wire = {
        "opportunity_packet_id": packet.id,
        "go_no_go": "go",
        "opportunity_score": 0.7,
        "market_alignment": 0.6,
        "expected_roi": "modeled only; no revenue promises",
        "risk_level": "medium",
        "legal_readiness": "review_required",
        "product_hypothesis": "educational checklist",
        "pricing_hypothesis": "$29 modeled; test willingness to pay",
        "validation_plan": ["post one educational thread"],
        "monetization_paths": ["paid checklist"],
        "recommended_next_action": "post one educational thread",
        "requires_human_approval": True,
        "reasons": ["score above threshold"],
    }
    wire.update(overrides)
    return wire


def test_http_mode_posts_to_intake_with_token(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    monkeypatch.setenv("WEALTHMACHINE_INTAKE_TOKEN", "sekrit")
    packet = _packet()
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data.decode())
        return _FakeResponse(_assessment_wire(packet))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = _client(tmp_path)
    assert client.mode == "http"

    assessment = client.evaluate(packet)
    assert seen["url"] == "http://wealthmachine.local/api/opportunities/intake"
    assert seen["auth"] == "Bearer sekrit"
    assert seen["body"]["id"] == packet.id  # packet wire payload round-trips
    assert seen["body"]["schema_version"] == "1.0"
    assert assessment.go_no_go == "go"
    assert assessment.opportunity_packet_id == packet.id


def test_http_mode_omits_auth_header_without_token(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    monkeypatch.delenv("WEALTHMACHINE_INTAKE_TOKEN", raising=False)
    packet = _packet()
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["auth"] = request.get_header("Authorization")
        return _FakeResponse(_assessment_wire(packet))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    _client(tmp_path).evaluate(packet)
    assert seen["auth"] is None


def test_http_mode_forces_human_approval(tmp_path, monkeypatch):
    """Even if the remote engine claimed otherwise, approval stays required."""
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    packet = _packet()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(
            _assessment_wire(packet, requires_human_approval=False)
        ),
    )
    assessment = _client(tmp_path).evaluate(packet)
    assert assessment.requires_human_approval is True


def test_http_mode_rejects_contract_violations(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    packet = _packet()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(
            _assessment_wire(packet, go_no_go="full_send")
        ),
    )
    with pytest.raises(ValueError):
        _client(tmp_path).evaluate(packet)
