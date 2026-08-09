"""Degrading is easy to state. The return trip is what gets lost.

A freeze with no record is either permanent by neglect or evaporates because
nobody remembered it was on, and both are worse than the incident. So every
posture change is an event with a reason, recovery is gated on conditions
declared while the incident is still open, and closing unresolved keeps the
restriction rather than quietly dropping it.
"""

import pytest

from db.session import get_db_session, init_db
from services.incident_posture import (
    ESCALATION_FLOOR,
    POSTURES,
    IncidentError,
    IncidentPosture,
    is_tightening,
    minimum_posture_for,
    posture_index,
)
from services.ledger import DecisionLedger


@pytest.fixture
def posture(tmp_path):
    init_db()
    return IncidentPosture(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def _incident(svc, session, **over):
    """`svc` rather than `posture`, since callers pass posture= as a field."""
    payload = dict(kind="platform", severity="medium",
                   summary="adapter returning 500s", detected_by="watchdog")
    payload.update(over)
    return svc.open_incident(session, **payload)


# ------------------------------------------------------------------ #
# The ladder
# ------------------------------------------------------------------ #

def test_postures_run_from_permissive_to_silent():
    assert POSTURES[0] == "RUN" and POSTURES[-1] == "SILENT"
    assert posture_index("PAUSE") < posture_index("READ_ONLY")
    assert is_tightening("PAUSE", "SILENT")
    assert not is_tightening("SILENT", "PAUSE")


def test_severity_sets_a_floor():
    assert minimum_posture_for("critical") == "SILENT"
    assert minimum_posture_for("low") == "RUN"


def test_optimism_cannot_hold_a_critical_incident_open(posture):
    """A critical incident does not sit at PAUSE because someone hoped."""
    with get_db_session() as session:
        with pytest.raises(IncidentError, match="Optimism is not a containment"):
            _incident(posture, session, severity="critical", posture="PAUSE",
                      escalated_to="Alfonso Lopez")


def test_high_severity_must_name_a_human(posture):
    with get_db_session() as session:
        with pytest.raises(IncidentError, match="name the human"):
            _incident(posture, session, severity="high", escalated_to="")


def test_incident_opens_at_its_floor_by_default(posture):
    with get_db_session() as session:
        record = _incident(posture, session, severity="high",
                           escalated_to="Alfonso Lopez")
    assert record.posture == "DRAFT_ONLY"
    assert record.posture_history[0]["from"] == "RUN"


# ------------------------------------------------------------------ #
# Tightening is free, loosening is not
# ------------------------------------------------------------------ #

def test_tightening_is_always_allowed(posture):
    with get_db_session() as session:
        record = _incident(posture, session)
        tightened = posture.tighten(session, incident_id=record.id,
                                    posture="SILENT", reason="spreading",
                                    actor="operator")
    assert tightened.posture == "SILENT"


def test_loosening_through_a_posture_change_is_refused(posture):
    """The only way back is a recovery. This is the guard that stops a freeze
    from being shrugged off."""
    with get_db_session() as session:
        record = _incident(posture, session, severity="high",
                           escalated_to="Alfonso Lopez")
        with pytest.raises(IncidentError, match="loosening happens through recovery"):
            posture.tighten(session, incident_id=record.id, posture="PAUSE",
                            reason="feels better now", actor="operator")


def test_tightening_requires_a_reason_and_an_actor(posture):
    with get_db_session() as session:
        record = _incident(posture, session)
        with pytest.raises(IncidentError, match="reason and an actor"):
            posture.tighten(session, incident_id=record.id, posture="SILENT",
                            reason="", actor="operator")


# ------------------------------------------------------------------ #
# Recovery
# ------------------------------------------------------------------ #

def test_recovery_without_predeclared_conditions_is_refused(posture):
    """Conditions written after the pressure lifts are written to be met."""
    with get_db_session() as session:
        record = _incident(posture, session)
        with pytest.raises(IncidentError, match="written to be met"):
            posture.recover(session, incident_id=record.id,
                            evidence_refs=["looks fine"], learning="ok",
                            actor="operator")


def test_recovery_needs_evidence_for_every_condition(posture):
    with get_db_session() as session:
        record = _incident(posture, session)
        posture.declare_recovery_conditions(
            session, incident_id=record.id,
            conditions=["adapter green for 24h", "root cause identified"],
        )
        with pytest.raises(IncidentError, match="2 recovery conditions"):
            posture.recover(session, incident_id=record.id,
                            evidence_refs=["uptime-1"], learning="l",
                            actor="operator")


def test_full_recovery_returns_to_run(posture):
    with get_db_session() as session:
        record = _incident(posture, session)
        posture.declare_recovery_conditions(session, incident_id=record.id,
                                            conditions=["adapter green for 24h"])
        recovered = posture.recover(
            session, incident_id=record.id, evidence_refs=["uptime-report-1"],
            learning="rate limit was undeclared on the adapter", actor="operator",
        )
    assert recovered.posture == "RUN"
    assert recovered.status == "RECOVERED"
    assert recovered.posture_history[-1]["posture"] == "RUN"


def test_recovery_requires_a_learning_statement(posture):
    with get_db_session() as session:
        record = _incident(posture, session)
        posture.declare_recovery_conditions(session, incident_id=record.id,
                                            conditions=["green"])
        with pytest.raises(IncidentError, match="learning statement"):
            posture.recover(session, incident_id=record.id,
                            evidence_refs=["e1"], learning="", actor="operator")


def test_closing_unresolved_keeps_the_restriction(posture):
    """Honest and deliberately uncomfortable: the freeze stays until someone
    recovers it properly."""
    with get_db_session() as session:
        record = _incident(posture, session, severity="high",
                           escalated_to="Alfonso Lopez")
        closed = posture.close_unresolved(
            session, incident_id=record.id,
            reason="vendor never responded", actor="Alfonso Lopez",
        )
        effective = posture.effective_posture(session)
    assert closed.status == "CLOSED_UNRESOLVED"
    assert closed.posture == "DRAFT_ONLY"
    assert effective["posture"] == "DRAFT_ONLY"


# ------------------------------------------------------------------ #
# Composition
# ------------------------------------------------------------------ #

def test_no_incidents_means_run(posture):
    with get_db_session() as session:
        effective = posture.effective_posture(session)
    assert effective["posture"] == "RUN"
    assert effective["open_incidents"] == 0


def test_postures_compose_by_taking_the_tightest(posture):
    """Two medium incidents do not cancel into a mild one."""
    with get_db_session() as session:
        _incident(posture, session, severity="medium")
        _incident(posture, session, severity="critical",
                  escalated_to="Alfonso Lopez")
        effective = posture.effective_posture(session)
    assert effective["posture"] == "SILENT"
    assert effective["open_incidents"] == 2
    assert effective["publishing_permitted"] is False
    assert effective["spending_permitted"] is False


def test_recovered_incident_stops_constraining(posture):
    with get_db_session() as session:
        record = _incident(posture, session)
        posture.declare_recovery_conditions(session, incident_id=record.id,
                                            conditions=["green"])
        posture.recover(session, incident_id=record.id, evidence_refs=["e1"],
                        learning="fixed", actor="operator")
        effective = posture.effective_posture(session)
    assert effective["posture"] == "RUN"


def test_escalation_floor_is_named():
    assert ESCALATION_FLOOR == "high"
