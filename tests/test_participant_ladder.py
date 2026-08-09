"""What the ladder refuses to say about people.

Owned distribution, advancement, community progression, commerce,
collaboration, and venture handoffs are one ladder, so the guards live in one
place. Each is tested by making it refuse, and each refusal is paired with a
case proving the legitimate version still passes — a guard that blocks real
participation would be worse than none.
"""

import pytest

from db.models import AdvancementAction, CommerceRecord, OwnedRelationship
from db.session import get_db_session, init_db
from services.ledger import DecisionLedger
from services.participant_ladder import (
    MIN_SEGMENT_POPULATION,
    RUNGS,
    ConsentError,
    ParticipantLadder,
    ParticipantLadderError,
    PrivacyError,
    UnreconciledRevenueError,
    consent_required,
    register_segment,
    register_territory_node,
    rung_index,
)


@pytest.fixture
def ladder(tmp_path):
    init_db()
    return ParticipantLadder(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def _person(ladder, session, **kw):
    payload = {"handle_ref": "pseudo-1", "purposes": ["deliver the newsletter"],
               "retention_until": "2027-01-01"}
    payload.update(kw)
    return ladder.register(session, **payload)


def _consented(ladder, session):
    person = _person(ladder, session)
    ladder.record_consent(session, participant_id=person.id,
                          consent_state="CONTACT", evidence_ref="signup-1")
    return person


def _verified_action(ladder, session, person):
    return ladder.record_advancement(
        session, participant_id=person.id,
        action_type="emergency_fund_started", description="opened a reserve",
        voluntary=True, verification_method="self-report plus screenshot",
        verification_evidence_ref="evidence-1", recorded_by="operator",
    )


# ------------------------------------------------------------------ #
# Privacy at creation
# ------------------------------------------------------------------ #

def test_participant_requires_a_stated_purpose():
    init_db()
    ladder = ParticipantLadder()
    with get_db_session() as session:
        with pytest.raises(PrivacyError, match="stated purpose"):
            ladder.register(session, handle_ref="p", purposes=[],
                            retention_until="2027-01-01")


def test_participant_requires_a_retention_limit(ladder):
    with get_db_session() as session:
        with pytest.raises(PrivacyError, match="retention limit"):
            ladder.register(session, handle_ref="p", purposes=["x"],
                            retention_until="  ")


def test_a_properly_scoped_record_is_accepted(ladder):
    with get_db_session() as session:
        person = _person(ladder, session)
    assert person.rung == "viewer"
    assert person.consent_state == "NONE"


# ------------------------------------------------------------------ #
# Nobody climbs by being counted
# ------------------------------------------------------------------ #

def test_cannot_advance_without_a_verified_action(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(ParticipantLadderError, match="enthusiasm is not advancement"):
            ladder.advance_rung(session, participant_id=person.id,
                                rung="learner", reason="seems keen")


def test_unverified_action_does_not_unlock_a_rung(ladder):
    """Negative control: an action recorded without evidence stays a claim."""
    with get_db_session() as session:
        person = _consented(ladder, session)
        action = ladder.record_advancement(
            session, participant_id=person.id, action_type="fire_plan_completed",
            description="says they finished", voluntary=True, recorded_by="operator",
        )
        assert action.verified is False
        with pytest.raises(ParticipantLadderError):
            ladder.advance_rung(session, participant_id=person.id,
                                rung="learner", reason="claimed completion")


def test_verified_action_unlocks_a_rung(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        _verified_action(ladder, session, person)
        advanced = ladder.advance_rung(session, participant_id=person.id,
                                       rung="member", reason="verified reserve")
    assert advanced.rung == "member"
    assert advanced.rung_history[-1]["from"] == "viewer"


def test_real_relationship_rungs_require_consent(ladder):
    with get_db_session() as session:
        person = _person(ladder, session)
        ladder.record_advancement(
            session, participant_id=person.id, action_type="cohort_joined",
            description="joined", voluntary=True,
            verification_method="roster", verification_evidence_ref="roster-1",
        )
        with pytest.raises(ConsentError, match="requires consent"):
            ladder.advance_rung(session, participant_id=person.id,
                                rung="member", reason="verified")


def test_involuntary_action_is_never_advancement(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(ParticipantLadderError, match="voluntarily"):
            ladder.record_advancement(
                session, participant_id=person.id,
                action_type="opportunity_entered", description="auto-enrolled",
                voluntary=False, verification_method="log",
                verification_evidence_ref="e1",
            )


def test_harm_report_blocks_verification(ladder):
    """An action that hurt someone is recorded and does not count."""
    with get_db_session() as session:
        person = _consented(ladder, session)
        action = ladder.record_advancement(
            session, participant_id=person.id, action_type="ownership_step_taken",
            description="bought in", voluntary=True, verification_method="receipt",
            verification_evidence_ref="r1", harm_reported=True,
        )
    assert action.verified is False
    assert action.harm_reported is True


def test_rung_order_and_consent_boundary():
    assert rung_index("viewer") < rung_index("member") < rung_index("expert")
    assert consent_required("member") is True
    assert consent_required("viewer") is False
    assert RUNGS[-1] == "infrastructure_creator"


# ------------------------------------------------------------------ #
# Advancement rate
# ------------------------------------------------------------------ #

def test_empty_population_is_not_a_rate_of_zero(ladder):
    with get_db_session() as session:
        result = ladder.verified_advancement_rate_30d(session)
    assert result["rate"] is None
    assert result["active"] == 0


def test_rate_counts_verified_actions_only(ladder):
    with get_db_session() as session:
        advanced = _consented(ladder, session)
        _verified_action(ladder, session, advanced)
        idle = _person(ladder, session, handle_ref="pseudo-2")
        ladder.record_advancement(
            session, participant_id=idle.id, action_type="practice_completed",
            description="claims so", voluntary=True,
        )
        result = ladder.verified_advancement_rate_30d(session)
    assert result["active"] == 2
    assert result["advanced"] == 1
    assert result["rate"] == 0.5


# ------------------------------------------------------------------ #
# Owned distribution is offered, never taken
# ------------------------------------------------------------------ #

def test_forced_migration_is_refused(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(ConsentError, match="never forced"):
            ladder.record_owned_relationship(
                session, participant_id=person.id, channel="email",
                destination_ref="list-1", consent_evidence_ref="c1",
                source_surface="x", migrated_voluntarily=False,
            )


def test_migration_without_consent_evidence_is_refused(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(ConsentError, match="consent evidence"):
            ladder.record_owned_relationship(
                session, participant_id=person.id, channel="email",
                destination_ref="list-1", consent_evidence_ref="",
                source_surface="x", migrated_voluntarily=True,
            )


def test_voluntary_consented_migration_is_recorded(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        rel = ladder.record_owned_relationship(
            session, participant_id=person.id, channel="email",
            destination_ref="list-1", consent_evidence_ref="double-optin-1",
            source_surface="x", migrated_voluntarily=True,
        )
        assert ladder.owned_audience_size(session) == 1
    assert rel.withdrawn is False


def test_withdrawal_ends_every_owned_relationship(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        ladder.record_owned_relationship(
            session, participant_id=person.id, channel="email",
            destination_ref="list-1", consent_evidence_ref="c1",
            source_surface="x", migrated_voluntarily=True,
        )
        ladder.record_consent(session, participant_id=person.id,
                              consent_state="WITHDRAWN", evidence_ref="")
        assert ladder.owned_audience_size(session) == 0


# ------------------------------------------------------------------ #
# Revenue means money moved
# ------------------------------------------------------------------ #

def test_revenue_without_reconciliation_is_refused(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(UnreconciledRevenueError, match="reconciliation reference"):
            ladder.record_commerce(
                session, participant_id=person.id, offer="guide", amount=29.0,
                reconciliation_ref="", delivered=True, accepted=True,
            )


def test_revenue_at_checkout_is_refused(ladder):
    """Negative control: paid is not delivered, and delivered is not accepted."""
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(UnreconciledRevenueError, match="after delivery"):
            ladder.record_commerce(
                session, participant_id=person.id, offer="guide", amount=29.0,
                reconciliation_ref="stripe-1", delivered=False, accepted=False,
            )


def test_reconciled_sale_produces_a_contribution_margin(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        ladder.record_commerce(
            session, participant_id=person.id, offer="guide", amount=29.0,
            reconciliation_ref="stripe-1", delivered=True, accepted=True,
            direct_cost=4.0,
        )
        scorecard = ladder.commercial_scorecard(session)
    assert scorecard["reconciled_revenue"] == 29.0
    assert scorecard["contribution_margin"] == 25.0
    assert scorecard["paying_participants"] == 1


def test_empty_scorecard_reads_zero_not_unknown(ladder):
    with get_db_session() as session:
        scorecard = ladder.commercial_scorecard(session)
    assert scorecard["reconciled_revenue"] == 0
    assert scorecard["contribution_margin_ratio"] is None


# ------------------------------------------------------------------ #
# Handoffs
# ------------------------------------------------------------------ #

def test_handoff_requires_all_prerequisites(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(ParticipantLadderError, match="missing"):
            ladder.prepare_handoff(
                session, participant_id=person.id, destination="pumpstation",
                need_detected="wants capital", eligibility_checked=False,
                eligibility_note="", disclosure_text="", consent_evidence_ref="",
            )


def test_handoff_without_disclosure_is_refused(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(ParticipantLadderError, match="disclosure"):
            ladder.prepare_handoff(
                session, participant_id=person.id, destination="pumpstation",
                need_detected="wants capital", eligibility_checked=True,
                eligibility_note="qualified", disclosure_text="",
                consent_evidence_ref="c1",
            )


def test_complete_handoff_is_prepared_but_not_sent(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        handoff = ladder.prepare_handoff(
            session, participant_id=person.id, destination="pumpstation",
            need_detected="building a lawful business, needs settlement rails",
            eligibility_checked=True, eligibility_note="meets stated criteria",
            disclosure_text="PumpStation is a UNIIMENTE venture cell we own.",
            consent_evidence_ref="consent-1", evidence_refs=["biz-plan-1"],
        )
    assert handoff.status == "PREPARED"


def test_declined_handoff_is_a_recorded_outcome(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        handoff = ladder.prepare_handoff(
            session, participant_id=person.id, destination="pumpstation",
            need_detected="need", eligibility_checked=True, eligibility_note="ok",
            disclosure_text="we own it", consent_evidence_ref="c1",
        )
        updated = ladder.record_handoff_outcome(
            session, handoff_id=handoff.id, status="DECLINED",
            outcome="participant chose not to proceed",
        )
    assert updated.status == "DECLINED"


# ------------------------------------------------------------------ #
# Collaboration
# ------------------------------------------------------------------ #

def test_collaboration_needs_two_people(ladder):
    with get_db_session() as session:
        person = _consented(ladder, session)
        with pytest.raises(ParticipantLadderError, match="at least two"):
            ladder.record_collaboration(
                session, participant_ids=[person.id], kind="build", description="solo",
            )


def test_verified_collaboration_is_recorded(ladder):
    with get_db_session() as session:
        a = _consented(ladder, session)
        b = _person(ladder, session, handle_ref="pseudo-2")
        link = ladder.record_collaboration(
            session, participant_ids=[a.id, b.id], kind="research",
            description="joint replication", outcome="preprint",
            verification_evidence_ref="doi-1",
        )
    assert link.verified is True


# ------------------------------------------------------------------ #
# Aggregate-only audience intelligence
# ------------------------------------------------------------------ #

def test_small_segment_is_refused_as_a_dossier(ladder):
    with get_db_session() as session:
        with pytest.raises(PrivacyError, match="identifies people"):
            register_segment(session, name="tiny", population=3,
                             purpose="targeting")


def test_segment_requires_a_purpose(ladder):
    with get_db_session() as session:
        with pytest.raises(PrivacyError, match="stated purpose"):
            register_segment(session, name="s", population=500, purpose="")


def test_aggregate_segment_is_accepted(ladder):
    with get_db_session() as session:
        segment = register_segment(
            session, name="ES cross-border earners", population=800,
            purpose="decide which localization lane to test next",
            language="es",
        )
    assert segment.population >= MIN_SEGMENT_POPULATION


# ------------------------------------------------------------------ #
# The rabbit hole has to let people leave
# ------------------------------------------------------------------ #

def test_node_without_a_counterargument_is_refused(ladder):
    with get_db_session() as session:
        with pytest.raises(ParticipantLadderError, match="opposing case"):
            register_territory_node(
                session, title="t", surface="tiktok", depth=0, thesis="a claim",
                counterargument="", off_ramp="unsubscribe",
                capability_payload="do this",
            )


def test_node_without_an_off_ramp_is_refused(ladder):
    with get_db_session() as session:
        with pytest.raises(ParticipantLadderError, match="off-ramp"):
            register_territory_node(
                session, title="t", surface="tiktok", depth=0, thesis="a claim",
                counterargument="the other side", off_ramp="",
                capability_payload="do this",
            )


def test_node_without_a_capability_payload_is_refused(ladder):
    with get_db_session() as session:
        with pytest.raises(ParticipantLadderError, match="reader can do"):
            register_territory_node(
                session, title="t", surface="tiktok", depth=0, thesis="a claim",
                counterargument="the other side", off_ramp="leave anytime",
                capability_payload="",
            )


def test_complete_node_is_accepted(ladder):
    with get_db_session() as session:
        node = register_territory_node(
            session, title="Why hard work may not compound", surface="tiktok",
            depth=0,
            thesis="Cross-border family obligations change the FIRE math.",
            counterargument="Remittances also buy option value that a "
                            "spreadsheet does not price.",
            off_ramp="If this does not describe you, here is the general version.",
            capability_payload="Work out your true savings rate including "
                               "transfers before choosing a target.",
        )
    assert node.depth == 0
    assert node.counterargument and node.off_ramp
