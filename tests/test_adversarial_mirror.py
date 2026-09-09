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
        observed_pain="Teams need a repeatable workshop process",
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
        observed_pain="Teams need practical course material",
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
    from tests.bridge_fixtures import KEY, Response, assessment_wire, intercept

    # Explicit bounded synthetic configuration, with real request/response HMAC.
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://localhost")
    monkeypatch.setenv("WEALTHMACHINE_MODE", "http")
    monkeypatch.setenv("WEALTHMACHINE_SIGNING_KEY", KEY)
    monkeypatch.setenv("WEALTHMACHINE_INTAKE_TOKEN", "synthetic-unit-fixture-only")
    monkeypatch.setenv("UNIIMENTE_BRIDGE_MODE", "synthetic-localhost")
    monkeypatch.setenv("UNIIMENTE_BRIDGE_STATE_PATH", str(tmp_path / "bridge.jsonl"))
    monkeypatch.setenv("UNIIMENTE_CONSTITUTION_HASH", "sha256:" + "a" * 64)
    monkeypatch.setenv("UNIIMENTE_LEGAL_PRINCIPAL", "alfonso_lopez")
    client = _client(tmp_path)
    packet = OpportunityPacket(
        observed_pain="A synthetic customer needs a guide",
        evidence=["e1"], possible_offer="guide",
    )
    wire = assessment_wire(packet)
    bear = next(case for case in wire["cases"] if case["case"] == "bear")
    bear.update(argument="willingness to pay untested", resolved=False)
    intercept(monkeypatch, lambda request, timeout: Response(packet, wire))
    assessment = client.evaluate(packet)
    assert assessment.cases == wire["cases"]
    assert bear in assessment.cases and bear["resolved"] is False
