"""The registry's job is refusing, so every guard here is tested by making
it refuse.

A registry that only stores aspirations is a wishlist. What makes this one
load-bearing is the set of things it will not record: a gate cleared by a
simulation, a campaign that picked its threshold afterwards, a second
bottleneck metric running beside the first, a blocked aspiration quietly
deleted.
"""

import pytest

from db.models import AspirationCampaign, AspirationRecord, BackcastPath
from db.session import get_db_session, init_db
from services.aspiration_registry import (
    ASPIRATION_STATUSES,
    BLOCKED_STATUSES,
    EVIDENCE_HIERARCHY,
    MINIMUM_GATE_CLEARANCE_TIER,
    AspirationRegistry,
    AspirationRegistryError,
    evidence_rank,
    is_external_evidence,
)
from services.ledger import DecisionLedger


@pytest.fixture
def registry(tmp_path):
    init_db()
    return AspirationRegistry(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def _aspiration(registry, session, **overrides):
    payload = {
        "founder_statement": "Reduce the distance between aspiration and reality",
        "success_state": "One retained external observation from a declared surface",
        "owner": "Alfonso Lopez",
        "status": "ACTIVE",
    }
    payload.update(overrides)
    return registry.register(session, **payload)


def _with_backcast(registry, session, record, gate="declared external surface"):
    registry.set_backcast(
        session,
        aspiration_id=record.id,
        success_state=record.success_state,
        stages=[{"gate": "sustained owned distribution"}, {"gate": gate}],
        repeatable_system="one cheapest reversible pilot per period",
    )
    return record


def _campaign(registry, session, record, **overrides):
    payload = {
        "aspiration_id": record.id,
        "gate": record.current_gate,
        "sbm": "VERIFIED_ASPIRATION_GATES_CLEARED",
        "evidence_threshold": "one retained observation, positive or negative",
        "resource_ceiling": "USD 0; no spend authorized",
        "stop_condition": "no response within 14 days",
    }
    payload.update(overrides)
    return registry.predeclare_campaign(session, **payload)


# ------------------------------------------------------------------ #
# The evidence hierarchy
# ------------------------------------------------------------------ #

def test_hierarchy_is_ordered_weakest_first():
    assert evidence_rank("aspiration") < evidence_rank("simulation")
    assert evidence_rank("simulation") < evidence_rank("reproduced_test")
    assert evidence_rank("reproduced_test") < evidence_rank("working_prototype")
    assert evidence_rank("working_prototype") < evidence_rank("authorized_pilot")
    assert evidence_rank("authorized_pilot") < evidence_rank("reconciled_real_outcome")
    assert EVIDENCE_HIERARCHY[-1] == "reconciled_real_outcome"


def test_internal_tiers_are_not_external_evidence():
    """Negative control: everything at or below a reproduced test happened
    inside the building."""
    for tier in ("aspiration", "document", "model_reasoning", "simulation",
                 "reproduced_test", "working_prototype"):
        assert not is_external_evidence(tier), tier


def test_external_tiers_are_external_evidence():
    for tier in ("authorized_pilot", "real_payment", "real_user_behavior",
                 "external_acceptance", "reconciled_real_outcome"):
        assert is_external_evidence(tier), tier


def test_unknown_tier_ranks_lowest_not_highest():
    """Negative control: an invented tier must not sneak past the gate."""
    assert evidence_rank("independently_verified_super_real") == -1
    assert not is_external_evidence("independently_verified_super_real")


# ------------------------------------------------------------------ #
# Registration
# ------------------------------------------------------------------ #

def test_register_requires_an_observable_success_state(registry):
    with get_db_session() as session:
        with pytest.raises(AspirationRegistryError, match="success_state"):
            registry.register(
                session, founder_statement="Become influential",
                success_state="   ", owner="Alfonso Lopez",
            )


def test_register_requires_statement_and_owner(registry):
    with get_db_session() as session:
        with pytest.raises(AspirationRegistryError, match="founder_statement"):
            registry.register(session, founder_statement="",
                              success_state="observable", owner="Alfonso Lopez")
        with pytest.raises(AspirationRegistryError, match="owner"):
            registry.register(session, founder_statement="statement",
                              success_state="observable", owner="  ")


def test_unknown_status_is_rejected(registry):
    with get_db_session() as session:
        with pytest.raises(AspirationRegistryError, match="status must be"):
            _aspiration(registry, session, status="GOING_GREAT")


def test_all_thirteen_statuses_are_accepted(registry):
    with get_db_session() as session:
        for status in ASPIRATION_STATUSES:
            record = _aspiration(registry, session, status=status)
            assert record.status == status


# ------------------------------------------------------------------ #
# Blocked aspirations survive
# ------------------------------------------------------------------ #

def test_blocked_aspiration_keeps_its_history(registry):
    with get_db_session() as session:
        record = _aspiration(registry, session)
        registry.set_status(
            session, aspiration_id=record.id, status="BLOCKED_PERMISSION",
            reason="no founder-declared surface or authority exists",
            actor="Alfonso Lopez",
        )
        registry.set_status(
            session, aspiration_id=record.id, status="ACTIVE",
            reason="surface declared", actor="Alfonso Lopez",
        )
        stored = registry.public_aspiration(session, record.id)

    assert stored["status"] == "ACTIVE"
    blocked = [entry for entry in stored["status_history"]
               if entry["status"] == "BLOCKED_PERMISSION"]
    assert len(blocked) == 1
    assert blocked[0]["reason"] == "no founder-declared surface or authority exists"


def test_registry_exposes_no_delete(registry):
    """Negative control on the API surface itself: there is no way to drop an
    aspiration, only to change its status with a reason."""
    for forbidden in ("delete", "remove", "drop", "purge", "delete_aspiration"):
        assert not hasattr(registry, forbidden)


def test_status_change_requires_reason_and_actor(registry):
    with get_db_session() as session:
        record = _aspiration(registry, session)
        with pytest.raises(AspirationRegistryError, match="reason"):
            registry.set_status(session, aspiration_id=record.id,
                                status="RETIRED", reason="  ", actor="Alfonso Lopez")
        with pytest.raises(AspirationRegistryError, match="actor"):
            registry.set_status(session, aspiration_id=record.id,
                                status="RETIRED", reason="superseded", actor="")


def test_blocked_statuses_are_named(registry):
    assert "BLOCKED_PERMISSION" in BLOCKED_STATUSES
    assert "BLOCKED_CAPITAL" in BLOCKED_STATUSES
    assert "ACHIEVED" not in BLOCKED_STATUSES


# ------------------------------------------------------------------ #
# Backcast GPS
# ------------------------------------------------------------------ #

def test_backcast_requires_g_p_and_s(registry):
    with get_db_session() as session:
        record = _aspiration(registry, session)
        with pytest.raises(AspirationRegistryError, match="success state"):
            registry.set_backcast(session, aspiration_id=record.id, success_state="",
                                  stages=[{"gate": "g"}], repeatable_system="s")
        with pytest.raises(AspirationRegistryError, match="at least one stage"):
            registry.set_backcast(session, aspiration_id=record.id, success_state="G",
                                  stages=[], repeatable_system="s")
        with pytest.raises(AspirationRegistryError, match="repeatable system"):
            registry.set_backcast(session, aspiration_id=record.id, success_state="G",
                                  stages=[{"gate": "g"}], repeatable_system="  ")


def test_backcast_stage_without_a_gate_is_rejected(registry):
    with get_db_session() as session:
        record = _aspiration(registry, session)
        with pytest.raises(AspirationRegistryError, match="missing a gate"):
            registry.set_backcast(session, aspiration_id=record.id, success_state="G",
                                  stages=[{"gate": "ok"}, {"note": "no gate here"}],
                                  repeatable_system="s")


def test_nearest_stage_becomes_the_current_gate(registry):
    with get_db_session() as session:
        record = _aspiration(registry, session)
        path = registry.set_backcast(
            session, aspiration_id=record.id, success_state="G",
            stages=[{"gate": "far"}, {"gate": "middle"}, {"gate": "nearest"}],
            repeatable_system="s",
        )
        stored = registry.public_aspiration(session, record.id)
    assert path.current_gate == "nearest"
    assert stored["current_gate"] == "nearest"


def test_revising_a_backcast_supersedes_rather_than_overwrites(registry):
    with get_db_session() as session:
        record = _aspiration(registry, session)
        first = registry.set_backcast(session, aspiration_id=record.id, success_state="G",
                                      stages=[{"gate": "old"}], repeatable_system="s")
        second = registry.set_backcast(session, aspiration_id=record.id, success_state="G",
                                       stages=[{"gate": "new"}], repeatable_system="s")
        paths = session.query(BackcastPath).all()
        prior = [p for p in paths if p.id == first.id][0]

    assert len(paths) == 2
    assert prior.superseded_by == second.id


# ------------------------------------------------------------------ #
# Campaign predeclaration
# ------------------------------------------------------------------ #

def test_campaign_requires_all_six_answers(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        for omitted in ("gate", "sbm", "evidence_threshold",
                        "resource_ceiling", "stop_condition"):
            with pytest.raises(AspirationRegistryError, match="all six answers"):
                _campaign(registry, session, record, **{omitted: "   "})


def test_campaign_must_attack_the_current_gate(registry):
    """Negative control: a campaign cannot pick a distant, easier gate."""
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        with pytest.raises(AspirationRegistryError, match="current gate"):
            _campaign(registry, session, record, gate="something more convenient")


def test_terminal_aspiration_cannot_run_a_campaign(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        registry.set_status(session, aspiration_id=record.id, status="RETIRED",
                            reason="folded into another aspiration", actor="Alfonso Lopez")
        with pytest.raises(AspirationRegistryError, match="terminal aspiration"):
            _campaign(registry, session, record)


def test_only_one_bottleneck_metric_runs_at_a_time(registry):
    """Negative control for the single-bottleneck rule: if two SBMs are live,
    neither is the bottleneck."""
    with get_db_session() as session:
        first = _with_backcast(registry, session, _aspiration(registry, session))
        _campaign(registry, session, first)

        second = _with_backcast(registry, session, _aspiration(registry, session))
        with pytest.raises(AspirationRegistryError, match="one dominant SBM"):
            _campaign(registry, session, second, sbm="QUALIFIED_OWNED_AUDIENCE_GROWTH")


def test_a_second_campaign_under_the_same_sbm_is_allowed(registry):
    with get_db_session() as session:
        first = _with_backcast(registry, session, _aspiration(registry, session))
        _campaign(registry, session, first)
        second = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, second)
    assert campaign.status == "PREDECLARED"


# ------------------------------------------------------------------ #
# Gate outcomes: the load-bearing refusal
# ------------------------------------------------------------------ #

def test_gate_cannot_be_cleared_by_a_simulation(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        with pytest.raises(AspirationRegistryError, match="cannot be cleared"):
            registry.record_gate_outcome(
                session, campaign_id=campaign.id, outcome="CLEARED",
                evidence_tier="simulation",
                external_evidence_refs=["shadow-receipt-1"],
                narrative="the shadow loop closed", recorded_by="operator",
            )


def test_gate_cannot_be_cleared_by_a_passing_test(registry):
    """Negative control aimed squarely at this repository's own habit."""
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        with pytest.raises(AspirationRegistryError, match="cannot be cleared"):
            registry.record_gate_outcome(
                session, campaign_id=campaign.id, outcome="CLEARED",
                evidence_tier="reproduced_test",
                external_evidence_refs=["tests/test_media_operating_system.py"],
                narrative="338 tests pass", recorded_by="operator",
            )


def test_clearing_requires_an_external_evidence_reference(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        with pytest.raises(AspirationRegistryError, match="external evidence reference"):
            registry.record_gate_outcome(
                session, campaign_id=campaign.id, outcome="CLEARED",
                evidence_tier="authorized_pilot", external_evidence_refs=[],
                narrative="it went well", recorded_by="operator",
            )


def test_gate_clears_on_an_authorized_pilot_with_references(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        event = registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="CLEARED",
            evidence_tier="authorized_pilot",
            external_evidence_refs=["pilot-observation-1"],
            narrative="one retained observation from the declared surface",
            recorded_by="Alfonso Lopez",
        )
        cleared = registry.verified_gates_cleared(session)
        stored = registry.public_aspiration(session, record.id)

    assert event.outcome == "CLEARED"
    assert cleared == 1
    assert "pilot-observation-1" in stored["current_evidence"]
    assert stored["active_sbm"] == ""  # the period closes with the campaign


def test_a_falsified_route_is_a_real_outcome(registry):
    """Negative results are recorded, and they do not need external evidence
    to count as learning — only CLEARED makes a claim about the world."""
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        event = registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="FALSIFIED",
            evidence_tier="reproduced_test",
            narrative="the technical route does not hold",
            recorded_by="operator",
        )
        assert registry.verified_gates_cleared(session) == 0
    assert event.outcome == "FALSIFIED"


def test_verified_gates_counts_only_external_clearances(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="DEFERRED",
            evidence_tier="simulation", narrative="waiting on authority",
            recorded_by="operator",
        )
        assert registry.verified_gates_cleared(session) == 0


def test_campaign_concludes_once(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="DEFERRED",
            evidence_tier="document", narrative="paused", recorded_by="operator",
        )
        with pytest.raises(AspirationRegistryError, match="already concluded"):
            registry.record_gate_outcome(
                session, campaign_id=campaign.id, outcome="CLEARED",
                evidence_tier="reconciled_real_outcome",
                external_evidence_refs=["invoice-1"],
                narrative="second bite", recorded_by="operator",
            )


def test_invalid_outcome_and_tier_are_rejected(registry):
    with get_db_session() as session:
        record = _with_backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        with pytest.raises(AspirationRegistryError, match="outcome must be"):
            registry.record_gate_outcome(
                session, campaign_id=campaign.id, outcome="WENT_GREAT",
                evidence_tier="authorized_pilot", narrative="n", recorded_by="o",
            )
        with pytest.raises(AspirationRegistryError, match="evidence_tier must be"):
            registry.record_gate_outcome(
                session, campaign_id=campaign.id, outcome="DEFERRED",
                evidence_tier="vibes", narrative="n", recorded_by="o",
            )


# ------------------------------------------------------------------ #
# Shared primitives
# ------------------------------------------------------------------ #

def test_primitives_rank_by_live_aspirations_unlocked(registry):
    with get_db_session() as session:
        a = _aspiration(registry, session)
        b = _aspiration(registry, session)
        c = _aspiration(registry, session)
        registry.register_primitive(session, name="narrow", description="d",
                                    unlocks=[a.id])
        registry.register_primitive(session, name="broad", description="d",
                                    unlocks=[a.id, b.id, c.id])
        ranked = registry.ranked_primitives(session)

    assert ranked[0]["name"] == "broad"
    assert ranked[0]["unlocks_live"] == 3
    assert ranked[1]["name"] == "narrow"


def test_retired_aspirations_stop_counting_toward_leverage(registry):
    """A primitive whose only dependents are retired is not a bottleneck."""
    with get_db_session() as session:
        a = _aspiration(registry, session)
        b = _aspiration(registry, session)
        registry.register_primitive(session, name="p", description="d",
                                    unlocks=[a.id, b.id])
        registry.set_status(session, aspiration_id=b.id, status="RETIRED",
                            reason="folded in", actor="Alfonso Lopez")
        ranked = registry.ranked_primitives(session)

    assert ranked[0]["unlocks_total"] == 2
    assert ranked[0]["unlocks_live"] == 1


def test_choosing_a_disposition_requires_a_rationale(registry):
    with get_db_session() as session:
        a = _aspiration(registry, session)
        with pytest.raises(AspirationRegistryError, match="rationale"):
            registry.register_primitive(session, name="p", description="d",
                                        unlocks=[a.id], disposition="BUILD")


def test_build_is_not_the_default_disposition(registry):
    with get_db_session() as session:
        a = _aspiration(registry, session)
        primitive = registry.register_primitive(session, name="p", description="d",
                                                unlocks=[a.id])
    assert primitive.disposition == "UNDECIDED"


def test_unknown_disposition_is_rejected(registry):
    with get_db_session() as session:
        a = _aspiration(registry, session)
        with pytest.raises(AspirationRegistryError, match="disposition must be"):
            registry.register_primitive(session, name="p", description="d",
                                        unlocks=[a.id], disposition="ACQUIHIRE")


def test_primitive_cannot_unlock_an_unregistered_aspiration(registry):
    with get_db_session() as session:
        with pytest.raises(AspirationRegistryError, match="not registered"):
            registry.register_primitive(session, name="p", description="d",
                                        unlocks=["no-such-aspiration"])
