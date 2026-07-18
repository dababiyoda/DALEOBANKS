"""DecisionEpisode projection: every packet is a reconstructable episode —
including killed ones and negative outcomes — with missing stages named
explicitly and source records never mutated."""

import asyncio

from db.models import OpportunityPacket, ValidationResult
from db.session import get_db_session, init_db
from services.decision_episode import STAGES, build_episode, list_episodes, loop_closure_rate
from services.idea_refinery import IdeaRefinery
from services.ledger import DecisionLedger, KillSwitch, set_shared_instances, reset_shared_instances
from services.operator_line import OperatorLine
from services.wealthmachine_client import WealthMachineClient

FIRE_THOUGHT = (
    "Financial independence is not selfish. It is protection from systems "
    "that profit from dependency. Maybe a budgeting checklist could help."
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _full_loop(ledger):
    """Refine → approve → assess → actions → validation: one closed loop."""
    init_db()
    refinery = IdeaRefinery(ledger=ledger)
    client = WealthMachineClient(ledger=ledger)
    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    with get_db_session() as session:
        idea = refinery.intake(session, FIRE_THOUGHT)
        refined = _run(refinery.refine(session, idea))
        packet = refined["opportunity"]
        packet.status = "approved"
        ledger.record("opportunity_decision", {"id": packet.id, "decision": "approved"})
        assessment = client.evaluate(packet)
        session.add(assessment)
        packet.status = "assessed"
        client.assessment_to_actions(session, assessment, packet, line)
        result = ValidationResult(
            opportunity_packet_id=packet.id,
            venture_assessment_id=assessment.id,
            hypothesis="Diaspora savers engage with FIRE education",
            result_classification="success",
            evidence_tier="conversation",
            evidence_quality=0.6,
            causal_note="Replies cited the specific mechanism",
        )
        session.add(result)
        session.commit()
        ledger.record("validation_result_recorded", {
            "id": result.id, "opportunity_packet_id": packet.id,
            "result_classification": "success",
        })
    return packet


def test_full_synthetic_episode_reconstructs_end_to_end(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        packet = _full_loop(ledger)
        with get_db_session() as session:
            episode = build_episode(session, packet.id, ledger=ledger)

        assert episode is not None
        for stage in ("signal", "provenance", "interpretation", "thesis",
                      "opportunity_packet", "venture_assessment",
                      "human_decision", "validation_result", "causal_note"):
            assert episode[stage], f"stage {stage} missing from closed loop"
        assert episode["loop_closed"] is True
        # Not-yet-implemented stages are named, never hidden.
        assert "capability_grant" in episode["missing_stages"]
        assert "executed_action" in episode["missing_stages"]
    finally:
        reset_shared_instances()


def test_killed_opportunity_is_still_an_episode(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        init_db()
        client = WealthMachineClient(ledger=ledger)
        with get_db_session() as session:
            packet = OpportunityPacket(
                source="operator", core_thesis="A regulated product idea",
                evidence=["one signal"], risk_flags=["legal_risk"],
            )
            session.add(packet)
            session.commit()
            assessment = client.evaluate(packet)
            session.add(assessment)
            session.commit()

            episode = build_episode(session, packet.id, ledger=ledger)

        assert episode is not None
        assert episode["venture_assessment"][0]["go_no_go"] == "kill"
        assert episode["loop_closed"] is False
        assert "validation_result" in episode["missing_stages"]
    finally:
        reset_shared_instances()


def test_negative_outcome_episode_and_closure_rate(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        init_db()
        with get_db_session() as session:
            packet = OpportunityPacket(source="operator", core_thesis="Quiet idea",
                                       evidence=["e1"])
            session.add(packet)
            session.add(ValidationResult(
                opportunity_packet_id=packet.id,
                result_classification="negative",
                causal_note="No response inside the window — recorded, not erased",
            ))
            session.commit()

            episode = build_episode(session, packet.id, ledger=ledger)
            closure = loop_closure_rate(session, ledger=ledger)

        assert episode["loop_closed"] is True  # a negative result closes the loop
        assert episode["validation_result"][0]["result_classification"] == "negative"
        assert closure["episodes"] >= 1 and closure["closed"] >= 1
    finally:
        reset_shared_instances()


def test_projection_never_mutates_sources(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        packet = _full_loop(ledger)
        before = len(ledger.entries())
        with get_db_session() as session:
            packets_before = len(session.query(OpportunityPacket).all())
            list_episodes(session, ledger=ledger)
            build_episode(session, packet.id, ledger=ledger)
            packets_after = len(session.query(OpportunityPacket).all())
        assert len(ledger.entries()) == before  # read-only projection
        assert packets_after == packets_before
        ok, _ = ledger.verify_chain()
        assert ok is True
    finally:
        reset_shared_instances()


def test_stage_names_are_canonical():
    assert STAGES[0] == "signal" and STAGES[-1] == "policy_impact"
    assert len(STAGES) == 12
