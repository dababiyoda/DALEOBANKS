"""The shadow loop: the complete governed cycle, end to end, with the
external act mocked out.

Signal → packet → adversarial assessment → human approval → scoped
capability grant → (shadow) execution → ValidationResult →
reconstructable DecisionEpisode. Nothing leaves the machine: no post, no
DM, no payment, no deployment. This is the evidence that the institution
can close a loop before it is ever allowed to touch the world.
"""

import asyncio

from db.models import ValidationResult
from db.session import get_db_session, init_db
from services.capability import CapabilityError, CapabilityService
from services.decision_episode import build_episode
from services.evidence_policy import evaluate_work
from services.idea_refinery import IdeaRefinery
from services.ledger import DecisionLedger, KillSwitch, set_shared_instances, reset_shared_instances
from services.operator_line import OperatorLine
from services.wealthmachine_client import WealthMachineClient

FIRE_THOUGHT = (
    "Financial independence is not selfish. It is protection from systems "
    "that profit from dependency. Maybe a starter kit could help."
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _shadow_loop(ledger, capability):
    """Drive the whole chain. Returns (packet, grant, approval, draft_id)."""
    init_db()
    refinery = IdeaRefinery(ledger=ledger)
    client = WealthMachineClient(ledger=ledger)
    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))

    with get_db_session() as session:
        idea = refinery.intake(session, FIRE_THOUGHT)
        packet = _run(refinery.refine(session, idea))["opportunity"]

        assessment = client.evaluate(packet)
        session.add(assessment)
        packet.status = "assessed"
        session.commit()

        actions = client.assessment_to_actions(session, assessment, packet, line)
        approval = actions["approval_request"]
        draft_id = actions["landing_page"].id

        line.handle_command(session, f"YES {approval.code}")

        grant = capability.mint_from_approval(
            session, approval.id, "publish_post",
            f"publish landing page draft {draft_id}", draft_id,
            named_targets=["lane-main"], maximum_uses=1,
            metadata={"opportunity_packet_id": packet.id},
        )

        capability.validate_and_consume(
            session, grant.id, "publish_post", draft_id, target="lane-main",
        )
        # Event name must start with "executed" so build_episode counts it.
        ledger.record("executed_shadow_action", {
            "opportunity_packet_id": packet.id, "capability_grant_id": grant.id,
            "mode": "shadow", "external_side_effect": False,
        })

        result = ValidationResult(
            opportunity_packet_id=packet.id,
            venture_assessment_id=assessment.id,
            capability_grant_id=grant.id,
            hypothesis="Diaspora savers engage with plain-language FIRE education",
            intervention="One educational post from the main lane",
            result_classification="mixed",
            evidence_tier="engagement",
            evidence_quality=0.4,
            causal_note="Shadow run: no external audience, so no causal claim",
            next_decision="Await human authorization before any real publication",
            recorded_by="shadow_loop",
            metadata={"mode": "shadow"},
        )
        session.add(result)
        session.commit()
        ledger.record("validation_result_recorded", {
            "id": result.id, "opportunity_packet_id": packet.id,
            "result_classification": "mixed",
        })
        return packet, grant, approval, draft_id


def test_shadow_loop_closes_without_any_external_action(tmp_path):
    from config import get_config

    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    capability = CapabilityService(ledger=ledger)
    try:
        live_before = get_config().LIVE
        packet, grant, _approval, draft_id = _shadow_loop(ledger, capability)

        with get_db_session() as session:
            episode = build_episode(session, packet.id, ledger=ledger)
            try:
                capability.validate_and_consume(
                    session, grant.id, "publish_post", draft_id, target="lane-main",
                )
                raise AssertionError("a one-use grant was consumed twice")
            except CapabilityError:
                pass

        for stage in ("signal", "thesis", "opportunity_packet", "venture_assessment",
                      "human_decision", "capability_grant", "executed_action",
                      "validation_result", "causal_note"):
            assert episode[stage], f"stage {stage} missing from the shadow loop"
        assert episode["loop_closed"] is True
        # Plumbing proven, market not: a shadow loop never counts as external.
        assert episode["externally_closed"] is False
        assert episode["shadow_only"] is True
        assert episode["capability_grant"][0]["id"] == grant.id

        chain_ok, _ = ledger.verify_chain()
        assert chain_ok is True
        assert get_config().LIVE == live_before  # a closed loop never arms
    finally:
        reset_shared_instances()


def test_shadow_loop_does_not_open_the_evidence_window(tmp_path):
    """Anti-cathedral: internal expansion stays blocked after a shadow
    rehearsal, and opens only when a real external result is recorded."""
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    capability = CapabilityService(ledger=ledger)
    try:
        init_db()
        with get_db_session() as session:
            before = evaluate_work(session, "internal_expansion",
                                   description="new dashboard", ledger=ledger)
            assert before["allowed"] is False
            assert before["window"]["empty"] is True
            assert evaluate_work(session, "unblocks_external_evidence",
                                 ledger=ledger)["allowed"] is True

        packet, _grant, _approval, _draft = _shadow_loop(ledger, capability)

        with get_db_session() as session:
            after_shadow = evaluate_work(session, "internal_expansion",
                                         description="new dashboard", ledger=ledger)
            assert after_shadow["allowed"] is False  # a rehearsal is not reality
            assert after_shadow["window"]["empty"] is True

            session.add(ValidationResult(
                opportunity_packet_id=packet.id,
                result_classification="negative",
                evidence_tier="observation",
                evidence_quality=0.2,
                causal_note="Real window closed with no response — retained, not erased",
            ))
            session.commit()
            after_real = evaluate_work(session, "internal_expansion",
                                       description="new dashboard", ledger=ledger)
        assert after_real["allowed"] is True
        assert after_real["window"]["validation_results"] == 1
    finally:
        reset_shared_instances()


def test_grant_in_the_loop_cannot_reach_past_the_approved_drafts(tmp_path):
    """The binding holds in the real chain, not only in isolation."""
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    capability = CapabilityService(ledger=ledger)
    try:
        init_db()
        refinery = IdeaRefinery(ledger=ledger)
        client = WealthMachineClient(ledger=ledger)
        line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))

        with get_db_session() as session:
            idea = refinery.intake(session, FIRE_THOUGHT)
            packet = _run(refinery.refine(session, idea))["opportunity"]
            assessment = client.evaluate(packet)
            session.add(assessment)
            actions = client.assessment_to_actions(session, assessment, packet, line)
            approval = actions["approval_request"]
            line.handle_command(session, f"YES {approval.code}")

            try:
                capability.mint_from_approval(
                    session, approval.id, "publish_post",
                    "publish some other draft", "draft-never-approved",
                )
                raise AssertionError("minted a grant outside the approved intent")
            except CapabilityError:
                pass

            grant = capability.mint_from_approval(
                session, approval.id, "publish_post", "publish interview script",
                actions["interview_script"].id,
            )
        assert grant.maximum_uses == 1
        assert any(e["payload"]["reason"] == "resource_outside_approved_intent"
                   for e in ledger.replay("capability_rejected"))
    finally:
        reset_shared_instances()
