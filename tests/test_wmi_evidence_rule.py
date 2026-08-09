"""One question — "did WealthMachineIntelligence actually produce this?" —
gets one answer, from one place.

Phase 0 gave assessments provenance labels but left the rule that reads them
written twice: the client required ``external_execution`` *and*
``evidence_class == EXTERNAL_ASSESSMENT``; the API route required only the
second. Two copies, two policies, and the looser copy decided what a packet's
status became.

Every guard here carries a negative control — a case proving the guard
refuses, not merely that it permits when nothing is wrong. A guard only ever
observed passing has not been tested.
"""

import pytest

from db.models import Idea, OpportunityPacket, VentureAssessment
from services.decision_episode import build_episode
from services.ledger import DecisionLedger, KillSwitch
from services.venture_protocol import (
    EVIDENCE_CLASS_EXTERNAL_ASSESSMENT,
    EVIDENCE_CLASS_EXTERNAL_UNVERIFIED,
    EVIDENCE_CLASS_MOCK,
    EXECUTION_CLASS_INBOUND_CONTRACT,
    EXECUTION_CLASS_SIMULATION,
    EXECUTION_CLASS_WMI_HTTP_AUTHENTICATED,
    MOCK_ASSESSMENT_LABEL,
    SIMULATION_LABELS,
    SimulatedEvidenceError,
    assessment_provenance,
    is_authoritative_wmi_assessment,
    is_simulated_assessment,
    packet_status_for_assessment,
    require_authoritative_wmi,
)


def _simulated():
    return VentureAssessment(
        go_no_go="go", opportunity_score=0.9,
        execution_class=EXECUTION_CLASS_SIMULATION,
        evidence_class=EVIDENCE_CLASS_MOCK,
        external_execution=False,
    )


def _authoritative():
    return VentureAssessment(
        go_no_go="go", opportunity_score=0.9,
        execution_class=EXECUTION_CLASS_WMI_HTTP_AUTHENTICATED,
        evidence_class=EVIDENCE_CLASS_EXTERNAL_ASSESSMENT,
        external_execution=True,
    )


def _half_labeled():
    """The case the two rule copies disagreed about: an assessment claiming
    the strong evidence_class without an external execution behind it."""
    return VentureAssessment(
        go_no_go="go", opportunity_score=0.9,
        execution_class=EXECUTION_CLASS_INBOUND_CONTRACT,
        evidence_class=EVIDENCE_CLASS_EXTERNAL_ASSESSMENT,
        external_execution=False,
    )


# ------------------------------------------------------------------ #
# The rule
# ------------------------------------------------------------------ #

def test_authoritative_assessment_is_recognized():
    assert is_authoritative_wmi_assessment(_authoritative())
    assert not is_simulated_assessment(_authoritative())


def test_simulated_assessment_is_not_authoritative():
    """Negative control: a maximally confident local verdict still fails."""
    simulated = _simulated()
    assert simulated.go_no_go == "go"
    assert simulated.opportunity_score == 0.9
    assert not is_authoritative_wmi_assessment(simulated)


def test_evidence_class_alone_is_not_enough():
    """The drift case. Both conjuncts are required; the looser rule is gone."""
    assert not is_authoritative_wmi_assessment(_half_labeled())


def test_external_execution_alone_is_not_enough():
    """Negative control on the other conjunct."""
    unverified = VentureAssessment(
        execution_class="EXTERNAL_HTTP_UNVERIFIED",
        evidence_class=EVIDENCE_CLASS_EXTERNAL_UNVERIFIED,
        external_execution=True,
    )
    assert not is_authoritative_wmi_assessment(unverified)


def test_unlabeled_assessment_fails_closed():
    """Silence is not evidence: a bare assessment proves nothing."""
    assert not is_authoritative_wmi_assessment(VentureAssessment())


def test_foreign_object_without_provenance_fails_closed():
    """Negative control: an object that never heard of provenance is not
    promoted to evidence by omission."""

    class Foreign:
        go_no_go = "go"
        opportunity_score = 1.0

    assert not is_authoritative_wmi_assessment(Foreign())
    assert packet_status_for_assessment(Foreign()) == "assessment_received_unverified"


# ------------------------------------------------------------------ #
# The gate refuses
# ------------------------------------------------------------------ #

def test_gate_refuses_a_simulation():
    with pytest.raises(SimulatedEvidenceError) as excinfo:
        require_authoritative_wmi(_simulated(), action="route to a Venture Cell")
    message = str(excinfo.value)
    assert "route to a Venture Cell" in message
    assert EXECUTION_CLASS_SIMULATION in message


def test_gate_refuses_the_drift_case():
    with pytest.raises(SimulatedEvidenceError):
        require_authoritative_wmi(_half_labeled(), action="record external evidence")


def test_gate_admits_a_real_verdict():
    require_authoritative_wmi(_authoritative(), action="route to a Venture Cell")


# ------------------------------------------------------------------ #
# Packet status is derived, never restated
# ------------------------------------------------------------------ #

def test_packet_status_per_provenance():
    assert packet_status_for_assessment(_simulated()) == "simulated"
    assert packet_status_for_assessment(_authoritative()) == "assessed"
    assert packet_status_for_assessment(_half_labeled()) == (
        "assessment_received_unverified"
    )


def test_call_sites_agree_with_the_canonical_rule():
    """Regression guard for the drift itself: the API route's status and the
    client's draft labeling must come from the same predicate."""
    from services.wealthmachine_client import WealthMachineClient
    import inspect

    source = inspect.getsource(WealthMachineClient.assessment_to_actions)
    # The rule is consumed, not restated.
    assert "is_authoritative_wmi_assessment(assessment)" in source
    assert 'evidence_class == "EXTERNAL_ASSESSMENT"' not in source

    app_source = inspect.getsource(__import__("app"))
    assert "packet_status_for_assessment(assessment)" in app_source
    assert 'elif assessment.evidence_class == "EXTERNAL_ASSESSMENT":' not in app_source


# ------------------------------------------------------------------ #
# Simulated verdicts stay labeled where a human reads them
# ------------------------------------------------------------------ #

def test_simulated_assessment_labels_reach_the_operator(tmp_path):
    from db.session import get_db_session, init_db
    from services.operator_line import OperatorLine
    from services.wealthmachine_client import WealthMachineClient

    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    client = WealthMachineClient(ledger=ledger)
    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    packet = OpportunityPacket(
        core_thesis="thesis", audience="builders", evidence=["e1"],
        possible_offer="educational checklist",
    )
    with get_db_session() as session:
        session.add(packet)
        actions = client.assessment_to_actions(session, _simulated(), packet, line)
        approval = actions["approval_request"]
        landing = actions["landing_page"]

    assert MOCK_ASSESSMENT_LABEL in approval.summary
    assert approval.payload["authoritative_wmi_assessment"] is False
    assert MOCK_ASSESSMENT_LABEL in landing.draft_text
    assert list(SIMULATION_LABELS) == MOCK_ASSESSMENT_LABEL.split(" | ")


# ------------------------------------------------------------------ #
# Institutional memory reads the distinction
# ------------------------------------------------------------------ #

def _episode_for(assessment, tmp_path):
    from db.session import get_db_session, init_db

    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    with get_db_session() as session:
        idea = Idea(raw_text="raw", thesis="thesis")
        session.add(idea)
        packet = OpportunityPacket(source_ref=idea.id, core_thesis="thesis",
                                   evidence=["e1"])
        session.add(packet)
        assessment.opportunity_packet_id = packet.id
        session.add(assessment)
        session.commit()
        return build_episode(session, packet.id, ledger=ledger)


def test_episode_marks_a_simulated_assessment_unverified(tmp_path):
    episode = _episode_for(_simulated(), tmp_path)
    assert episode["externally_assessed"] is False
    assert episode["simulated_assessment_count"] == 1
    assert episode["assessment_provenance"][0]["authoritative_wmi"] is False


def test_episode_marks_a_real_assessment_verified(tmp_path):
    episode = _episode_for(_authoritative(), tmp_path)
    assert episode["externally_assessed"] is True
    assert episode["simulated_assessment_count"] == 0
    assert episode["assessment_provenance"][0]["authoritative_wmi"] is True


def test_episode_does_not_count_the_drift_case_as_external(tmp_path):
    """Negative control at the memory layer: the case that used to read as
    'assessed' must not enter institutional memory as external evidence."""
    episode = _episode_for(_half_labeled(), tmp_path)
    assert episode["externally_assessed"] is False


def test_provenance_summary_shape():
    summary = assessment_provenance(_authoritative())
    assert set(summary) == {
        "execution_class", "evidence_class", "external_execution",
        "authoritative_wmi", "simulated",
    }
