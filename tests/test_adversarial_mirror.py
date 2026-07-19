"""The mock evaluator argues with itself exactly like the real engine:
mirrored adversarial cases, preserved disagreement, and the rule that a
high score may not erase a severe unresolved risk."""

from db.models import OpportunityPacket
from db.session import init_db
from services.ledger import DecisionLedger
from services.wealthmachine_client import WealthMachineClient


def _client(tmp_path):
    init_db()
    return WealthMachineClient(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def test_strong_packet_gets_bear_and_do_nothing_cases(tmp_path):
    client = _client(tmp_path)
    strong = OpportunityPacket(
        evidence=["five replies", "two DMs", "a collaboration ask"],
        urgency="high", possible_offer="workshop",
        monetization_paths=["paid workshop"],
    )
    assessment = client.evaluate(strong)
    cases = {c["case"]: c for c in assessment.cases}

    assert assessment.go_no_go == "go"
    assert cases["bear"]["stance"] == "against"
    assert cases["bull"]["stance"] == "for"  # disagreement preserved
    assert "do_nothing" in cases and "opportunity_cost" in cases


def test_sybil_evidence_caps_the_mock_verdict(tmp_path):
    client = _client(tmp_path)
    suspicious = OpportunityPacket(
        evidence=["I'd pay for this!", "i'd pay for this!", "I'd pay for this! "],
        urgency="high", possible_offer="course",
        monetization_paths=["paid course"],
    )
    assessment = client.evaluate(suspicious)
    cases = {c["case"]: c for c in assessment.cases}

    assert cases["fraud_manipulation"]["severity"] == "high"
    assert assessment.go_no_go != "go"
    assert any("adversarial case" in r for r in assessment.reasons)
    assert assessment.requires_human_approval is True


def test_http_mode_passes_cases_through(tmp_path, monkeypatch):
    import io
    import json

    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wealthmachine.local")
    client = _client(tmp_path)
    packet = OpportunityPacket(evidence=["e1"], possible_offer="guide")

    class _FakeResponse:
        def __init__(self, payload):
            self._body = io.BytesIO(json.dumps(payload).encode())

        def __enter__(self):
            return self._body

        def __exit__(self, *exc):
            return False

    wire = {
        "opportunity_packet_id": packet.id, "go_no_go": "defer",
        "opportunity_score": 0.5, "requires_human_approval": True,
        "cases": [{"case": "bear", "stance": "against", "severity": "medium",
                   "argument": "willingness to pay untested", "resolved": False}],
    }
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda request, timeout=None: _FakeResponse(wire))
    assessment = client.evaluate(packet)
    assert assessment.cases and assessment.cases[0]["case"] == "bear"
