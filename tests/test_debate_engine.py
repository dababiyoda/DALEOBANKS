"""A debate that produced only outrage is a weak outcome, enforced.

That is easy to agree with and hard to hold, because outrage is what success
looks like in every media dashboard. So productivity is defined by artifacts,
and a debate that left none closes as unproductive with that recorded.
"""

import pytest

from db.session import get_db_session, init_db
from services.debate_engine import (
    PRODUCTIVE_OUTCOMES,
    DebateEngine,
    DebateEngineError,
    touches_speculative_domain,
)
from services.ledger import DecisionLedger


@pytest.fixture
def engine(tmp_path):
    init_db()
    return DebateEngine(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def _debate(engine, session, **over):
    payload = dict(
        question="Do junk fees survive because disclosure rules are toothless?",
        daleobanks_position="Disclosure without a comparison duty changes nothing.",
        strongest_counterargument="Comparison duties raise compliance costs that "
                                  "small lenders pass back to borrowers.",
        evidence_class="PROPOSAL",
    )
    payload.update(over)
    return engine.open_debate(session, **payload)


# ------------------------------------------------------------------ #
# Opening
# ------------------------------------------------------------------ #

def test_debate_requires_the_case_against_itself(engine):
    with get_db_session() as session:
        with pytest.raises(DebateEngineError, match="agenda-setting, not debate"):
            _debate(engine, session, strongest_counterargument="")


def test_frontier_topic_cannot_open_as_fact(engine):
    """Wanting a future badly is not evidence it arrived."""
    with get_db_session() as session:
        with pytest.raises(DebateEngineError, match="frontier work is labeled"):
            _debate(engine, session,
                    question="Does longevity escape velocity arrive this decade?",
                    evidence_class="FACT")


def test_frontier_topic_opens_as_proposal(engine):
    with get_db_session() as session:
        record = _debate(engine, session,
                         question="What blocks cheap robotics?",
                         evidence_class="PROPOSAL")
    assert record.evidence_class == "PROPOSAL"


def test_settled_topic_may_open_as_fact(engine):
    """Negative control: the evidence-class gate applies to frontier claims,
    not to everything."""
    with get_db_session() as session:
        record = _debate(engine, session, evidence_class="FACT")
    assert record.evidence_class == "FACT"


def test_speculative_domain_detection():
    assert touches_speculative_domain("a robotics supply chain") == ["robotics"]
    assert touches_speculative_domain("compound interest") == []


# ------------------------------------------------------------------ #
# Closing on what it produced
# ------------------------------------------------------------------ #

def test_engagement_only_closes_as_unproductive(engine):
    with get_db_session() as session:
        record = _debate(engine, session)
        closed = engine.close_debate(session, debate_id=record.id,
                                     outcomes=["engagement_only"])
    assert closed.productive is False


def test_outrage_only_closes_as_unproductive(engine):
    with get_db_session() as session:
        record = _debate(engine, session)
        closed = engine.close_debate(session, debate_id=record.id,
                                     outcomes=["outrage_only"])
    assert closed.productive is False


def test_an_artifact_makes_it_productive(engine):
    with get_db_session() as session:
        record = _debate(engine, session)
        closed = engine.close_debate(
            session, debate_id=record.id,
            outcomes=["falsified_assumption", "expert_identified"],
            outcome_refs={"expert_identified": "thread-42"},
        )
    assert closed.productive is True


def test_closing_requires_stating_what_happened(engine):
    """Even when the honest answer is nothing."""
    with get_db_session() as session:
        record = _debate(engine, session)
        with pytest.raises(DebateEngineError, match="requires stating"):
            engine.close_debate(session, debate_id=record.id, outcomes=[])


def test_unknown_outcome_is_refused(engine):
    with get_db_session() as session:
        record = _debate(engine, session)
        with pytest.raises(DebateEngineError, match="unrecognized"):
            engine.close_debate(session, debate_id=record.id,
                                outcomes=["went_viral"])


def test_a_debate_closes_once(engine):
    with get_db_session() as session:
        record = _debate(engine, session)
        engine.close_debate(session, debate_id=record.id, outcomes=["prototype"])
        with pytest.raises(DebateEngineError, match="already closed"):
            engine.close_debate(session, debate_id=record.id,
                                outcomes=["better_question"])


# ------------------------------------------------------------------ #
# Research leads
# ------------------------------------------------------------------ #

def test_resolution_requires_independent_verification(engine):
    """A lively public thread is not scientific closure."""
    with get_db_session() as session:
        lead = engine.open_research_lead(session, question="Does the mechanism hold?")
        with pytest.raises(DebateEngineError, match="not scientific closure"):
            engine.resolve_research_lead(session, lead_id=lead.id, status="RESOLVED",
                                         result="it holds")


def test_falsification_needs_no_verification(engine):
    """Negative control: demanding verification for a negative result would
    suppress the cheapest useful outcome research produces."""
    with get_db_session() as session:
        lead = engine.open_research_lead(session, question="Does it hold?")
        resolved = engine.resolve_research_lead(
            session, lead_id=lead.id, status="FALSIFIED",
            result="the mechanism does not hold under load",
        )
    assert resolved.status == "FALSIFIED"
    assert resolved.independently_verified is False


def test_verified_resolution_is_recorded(engine):
    with get_db_session() as session:
        lead = engine.open_research_lead(session, question="Does it hold?")
        resolved = engine.resolve_research_lead(
            session, lead_id=lead.id, status="RESOLVED", result="replicated",
            verification_ref="doi:10.1234/independent",
        )
    assert resolved.independently_verified is True


def test_unverified_result_cannot_be_absorbed(engine):
    with get_db_session() as session:
        lead = engine.open_research_lead(session, question="Does it hold?")
        engine.resolve_research_lead(session, lead_id=lead.id, status="FALSIFIED",
                                     result="no")
        with pytest.raises(DebateEngineError, match="independently verified"):
            engine.absorb_external_capability(session, lead_id=lead.id,
                                              capability_ref="lib-1")


def test_external_solution_absorbed_is_the_loop_working(engine):
    """Someone else solving it is the point of seeding, not a loss."""
    with get_db_session() as session:
        lead = engine.open_research_lead(session, question="Does it hold?",
                                         disposition="OPEN_SOURCE")
        engine.resolve_research_lead(session, lead_id=lead.id, status="RESOLVED",
                                     result="replicated", verification_ref="doi:1")
        absorbed = engine.absorb_external_capability(
            session, lead_id=lead.id, capability_ref="github.com/someone/thing",
        )
    assert absorbed.absorbed_capability_ref


def test_unknown_disposition_is_refused(engine):
    with get_db_session() as session:
        with pytest.raises(DebateEngineError, match="disposition must be"):
            engine.open_research_lead(session, question="q", disposition="ACQUIHIRE")


# ------------------------------------------------------------------ #
# Scorecard
# ------------------------------------------------------------------ #

def test_scorecard_separates_produced_from_merely_loud(engine):
    with get_db_session() as session:
        loud = _debate(engine, session)
        engine.close_debate(session, debate_id=loud.id, outcomes=["outrage_only"])
        useful = _debate(engine, session, question="A second question?")
        engine.close_debate(session, debate_id=useful.id,
                            outcomes=["research_lead"])
        engine.open_research_lead(session, question="follow-up", debate_id=useful.id)
        scorecard = engine.seeding_scorecard(session)
    assert scorecard["productive_debates"] == 1
    assert scorecard["unproductive_debates"] == 1
    assert scorecard["research_leads"] == 1
    assert scorecard["leads_verified"] == 0
