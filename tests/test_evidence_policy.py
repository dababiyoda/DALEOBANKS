"""Anti-cathedral policy and the lexicographic metric hierarchy: internal
expansion is denied while the evidence window is empty; a constitutional
breach hard-zeros the period; zero external evidence means zero
evidence-weighted progress, however busy the machine was."""

from db.models import OpportunityPacket, ValidationResult
from db.session import get_db_session, init_db
from services.evidence_policy import (
    constitutional_health,
    evaluate_work,
    evidence_quality_multiplier,
    evidence_weighted_j,
    evidence_window,
    institutional_metrics,
)
from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances


def _setup(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    return ledger


def _record_result(session, tier="conversation", quality=0.6, classification="success"):
    packet = OpportunityPacket(source="operator", core_thesis="t", evidence=["e"])
    session.add(packet)
    session.add(ValidationResult(
        opportunity_packet_id=packet.id,
        evidence_tier=tier, evidence_quality=quality,
        result_classification=classification,
    ))
    session.commit()


def test_empty_window_denies_internal_expansion_permits_repairs(tmp_path):
    ledger = _setup(tmp_path)
    try:
        with get_db_session() as session:
            assert evidence_window(session)["empty"] is True

            denied = evaluate_work(session, "internal_expansion",
                                   description="a seventh dashboard", ledger=ledger)
            assert denied["allowed"] is False

            for category in ("security_repair", "compliance_repair",
                             "critical_reliability_repair",
                             "external_evidence_producing",
                             "unblocks_external_evidence"):
                assert evaluate_work(session, category, ledger=ledger)["allowed"] is True

            unknown = evaluate_work(session, "vibes_expansion", ledger=ledger)
            assert unknown["allowed"] is False
        # Refusals are institutional memory.
        decisions = ledger.replay("anti_cathedral_decision")
        assert any(d["payload"]["allowed"] is False for d in decisions)
    finally:
        reset_shared_instances()


def test_nonempty_window_permits_internal_expansion(tmp_path):
    ledger = _setup(tmp_path)
    try:
        with get_db_session() as session:
            _record_result(session)
            decision = evaluate_work(session, "internal_expansion", ledger=ledger)
        assert decision["allowed"] is True
        assert decision["window"]["validation_results"] == 1
    finally:
        reset_shared_instances()


def test_constitutional_breach_hard_zeros_the_period(tmp_path):
    ledger = _setup(tmp_path)
    try:
        with get_db_session() as session:
            _record_result(session, tier="payment", quality=1.0)
            healthy = evidence_weighted_j(10.0, session, ledger)
            assert healthy["constitutional_gate"] == 1.0
            assert healthy["evidence_weighted_j"] > 0.0

            ledger.record("constitutional_violation", {"detail": "test breach"})
            breached = evidence_weighted_j(10.0, session, ledger)
        assert breached["constitutional_gate"] == 0.0
        assert breached["evidence_weighted_j"] == 0.0  # nothing buys it back
    finally:
        reset_shared_instances()


def test_broken_chain_zeroes_health(tmp_path):
    path = tmp_path / "l.jsonl"
    ledger = _setup(tmp_path)
    try:
        ledger.record("boot", {})
        lines = path.read_text().splitlines()
        lines[0] = lines[0].replace("boot", "tampered")
        path.write_text("\n".join(lines) + "\n")
        health = constitutional_health(DecisionLedger(path=str(path)))
        assert health["gate"] == 0.0
    finally:
        reset_shared_instances()


def test_zero_external_evidence_means_zero_progress(tmp_path):
    ledger = _setup(tmp_path)
    try:
        with get_db_session() as session:
            assert evidence_quality_multiplier(session) == 0.0
            weighted = evidence_weighted_j(100.0, session, ledger)
        # However large the internal J, no reality contact -> no progress.
        assert weighted["evidence_weighted_j"] == 0.0
    finally:
        reset_shared_instances()


def test_payment_tier_outweighs_observation(tmp_path):
    _setup(tmp_path)
    try:
        with get_db_session() as session:
            _record_result(session, tier="observation", quality=1.0)
            low = evidence_quality_multiplier(session)
        init_db()
        with get_db_session() as session:
            _record_result(session, tier="payment", quality=1.0)
            high = evidence_quality_multiplier(session)
        assert high > low
    finally:
        reset_shared_instances()


def test_institutional_metrics_report(tmp_path):
    ledger = _setup(tmp_path)
    try:
        with get_db_session() as session:
            _record_result(session, classification="negative")
            _record_result(session, tier="commitment", quality=0.8)
            metrics = institutional_metrics(session, ledger=ledger, base_j=5.0)

        assert metrics["validation_results_total"] == 2
        assert metrics["negative_results_retained"] == 1
        assert 0 < metrics["negative_retention_rate"] < 1
        assert metrics["episodes"] == 2 and metrics["closed"] == 2
        assert metrics["evidence_weighted"]["evidence_weighted_j"] > 0.0
    finally:
        reset_shared_instances()
