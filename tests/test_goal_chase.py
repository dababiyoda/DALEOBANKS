"""The loop's most common correct output is a refusal.

"Infinite" here excludes blind persistence, unlimited budget, ignoring
falsification, and attacking every aspiration at once. Each exclusion is a
way a loop like this eats an institution, so each gets a test that makes the
scheduler decline rather than manufacture motion.
"""

import pytest

from db.session import get_db_session, init_db
from services.aspiration_registry import AspirationRegistry
from services.goal_chase import GoalChaseScheduler
from services.ledger import DecisionLedger


@pytest.fixture
def rig(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    registry = AspirationRegistry(ledger=ledger)
    return registry, GoalChaseScheduler(registry=registry, ledger=ledger)


def _aspiration(registry, session, importance="medium", **kw):
    payload = {
        "founder_statement": "reduce the distance between aspiration and reality",
        "success_state": "one retained external observation",
        "owner": "Alfonso Lopez", "status": "ACTIVE", "importance": importance,
    }
    payload.update(kw)
    return registry.register(session, **payload)


def _backcast(registry, session, record, gate="declared surface"):
    registry.set_backcast(
        session, aspiration_id=record.id, success_state=record.success_state,
        stages=[{"gate": "distant"}, {"gate": gate}],
        repeatable_system="one cheapest reversible pilot",
    )
    return record


def _campaign(registry, session, record):
    return registry.predeclare_campaign(
        session, aspiration_id=record.id, gate=record.current_gate,
        sbm="VERIFIED_ASPIRATION_GATES_CLEARED",
        evidence_threshold="one retained observation",
        resource_ceiling="USD 0", stop_condition="no response in 14 days",
    )


# ------------------------------------------------------------------ #
# Refusals
# ------------------------------------------------------------------ #

def test_empty_registry_produces_a_refusal_not_a_task(rig):
    """A scheduler that always finds something to do is manufacturing motion."""
    _, scheduler = rig
    with get_db_session() as session:
        move = scheduler.next_move(session, budget_ceiling=100.0)
    assert move["action"] == "BLOCKED"
    assert move["code"] == "NO_LIVE_ASPIRATION"


def test_all_blocked_does_not_route_around_the_wall(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        record = _aspiration(registry, session)
        registry.set_status(session, aspiration_id=record.id,
                            status="BLOCKED_PERMISSION",
                            reason="no declared surface", actor="Alfonso Lopez")
        move = scheduler.next_move(session, budget_ceiling=100.0)
    assert move["action"] == "BLOCKED"
    assert move["code"] == "ALL_ASPIRATIONS_BLOCKED"


def test_no_declared_budget_ceiling_stops_the_loop(rig):
    """An unbounded loop is the failure mode, not the feature."""
    registry, scheduler = rig
    with get_db_session() as session:
        _backcast(registry, session, _aspiration(registry, session))
        move = scheduler.next_move(session, budget_ceiling=None)
    assert move["action"] == "BLOCKED"
    assert move["code"] == "NO_BUDGET_CEILING"


def test_one_campaign_at_a_time(rig):
    """Attacking several gates at once is how a portfolio becomes a rout."""
    registry, scheduler = rig
    with get_db_session() as session:
        first = _backcast(registry, session, _aspiration(registry, session))
        _campaign(registry, session, first)
        _backcast(registry, session, _aspiration(registry, session))
        move = scheduler.next_move(session, budget_ceiling=100.0)
    assert move["action"] == "AWAIT_OUTCOME"
    assert "one gate at a time" in move["reason"]


# ------------------------------------------------------------------ #
# Legitimate moves
# ------------------------------------------------------------------ #

def test_missing_backcast_is_the_next_move(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        record = _aspiration(registry, session)
        move = scheduler.next_move(session, budget_ceiling=100.0)
    assert move["action"] == "SET_BACKCAST"
    assert move["aspiration_id"] == record.id


def test_ready_aspiration_yields_a_predeclaration_with_all_six(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        record = _backcast(registry, session, _aspiration(registry, session))
        move = scheduler.next_move(session, budget_ceiling=100.0)
    assert move["action"] == "PREDECLARE_CAMPAIGN"
    assert move["aspiration_id"] == record.id
    assert len(move["required_predeclarations"]) == 6


def test_importance_orders_the_choice(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        _backcast(registry, session, _aspiration(registry, session, importance="low"))
        critical = _backcast(
            registry, session,
            _aspiration(registry, session, importance="critical"), gate="critical gate",
        )
        move = scheduler.next_move(session, budget_ceiling=100.0)
    assert move["aspiration_id"] == critical.id


# ------------------------------------------------------------------ #
# Route tournament
# ------------------------------------------------------------------ #

def test_tournament_ranks_by_live_leverage(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        a = _backcast(registry, session, _aspiration(registry, session))
        b = _aspiration(registry, session)
        registry.register_primitive(session, name="narrow", description="d",
                                    unlocks=[a.id])
        registry.register_primitive(session, name="broad", description="d",
                                    unlocks=[a.id, b.id])
        ranked = scheduler.route_tournament(session)
    assert ranked[0]["name"] == "broad"
    assert ranked[0]["live_unlocks"] == 2


def test_a_falsified_gate_leaves_the_tournament(rig):
    """Reality closed the route. Retrying it is blind persistence."""
    registry, scheduler = rig
    with get_db_session() as session:
        record = _backcast(registry, session, _aspiration(registry, session))
        registry.register_primitive(session, name="dead end", description="d",
                                    unlocks=[record.id])
        campaign = _campaign(registry, session, record)
        registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="FALSIFIED",
            evidence_tier="working_prototype",
            narrative="the technical route does not hold", recorded_by="operator",
        )
        ranked = scheduler.route_tournament(session)
    assert all(row["name"] != "dead end" for row in ranked)


# ------------------------------------------------------------------ #
# Absorbing outcomes
# ------------------------------------------------------------------ #

def test_cleared_gate_raises_ambition(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        record = _backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        event = registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="CLEARED",
            evidence_tier="authorized_pilot", external_evidence_refs=["obs-1"],
            narrative="one retained observation", recorded_by="Alfonso Lopez",
        )
        absorbed = scheduler.absorb_outcome(session, event_id=event.id)
    assert absorbed["next"] == "RAISE_AMBITION"
    assert absorbed["external_evidence"] is True


def test_falsified_route_is_retired_not_retried(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        record = _backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        event = registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="FALSIFIED",
            evidence_tier="reproduced_test", narrative="closed",
            recorded_by="operator",
        )
        absorbed = scheduler.absorb_outcome(session, event_id=event.id)
    assert absorbed["next"] == "RETIRE_ROUTE"


def test_deferral_names_what_it_waits_on(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        record = _backcast(registry, session, _aspiration(registry, session))
        campaign = _campaign(registry, session, record)
        event = registry.record_gate_outcome(
            session, campaign_id=campaign.id, outcome="DEFERRED",
            evidence_tier="document", narrative="awaiting authority",
            recorded_by="operator",
        )
        absorbed = scheduler.absorb_outcome(session, event_id=event.id)
    assert absorbed["next"] == "AWAIT_INPUT"


# ------------------------------------------------------------------ #
# Gap map
# ------------------------------------------------------------------ #

def test_gap_map_reports_blockers_and_gates_cleared(rig):
    registry, scheduler = rig
    with get_db_session() as session:
        live = _backcast(registry, session, _aspiration(registry, session))
        blocked = _aspiration(registry, session)
        registry.set_status(session, aspiration_id=blocked.id,
                            status="BLOCKED_CAPITAL", reason="no capital",
                            actor="Alfonso Lopez")
        gaps = scheduler.gap_map(session)
    assert gaps["live"] == 2
    assert gaps["blocked"] == 1
    assert gaps["blocked_by_reason"]["BLOCKED_CAPITAL"] == 1
    assert gaps["gates_cleared"] == 0
    assert live.id not in gaps["without_backcast"]
