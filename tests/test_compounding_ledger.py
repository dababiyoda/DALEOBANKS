"""This ledger exists to say no to its own author, so that is what is tested.

Every guard here gets two tests: one showing it refuses, and one showing it
still lets the legitimate case through. A guard that only ever refuses is a
disabled feature with good manners, and a guard that only ever permits is
decoration.

The last test in this file is the one that matters. It builds a plausible
system entirely out of internally-consistent parts, and checks that the
report calls it ARCHITECTURE_ONLY rather than progress.
"""

from datetime import datetime, timedelta, timezone

import pytest

from db.models import ComponentRecord, ProofRecord
from db.session import get_db_session, init_db
from services.compounding_ledger import (
    ARCHITECTURE_DEBT_CEILING,
    COMPOUNDING_DIMENSIONS,
    FORCED_VERDICTS,
    MINIMUM_PROOF_TIER,
    TIERS,
    ArchitectureDebtError,
    CompoundingLedger,
    InsufficientProofError,
    SelfReferentialProofError,
    UndeclaredCompoundingError,
    UnharvestedKillError,
    is_internal_reference,
    tier_rank,
)


@pytest.fixture
def ledger():
    init_db()
    return CompoundingLedger()


@pytest.fixture
def session():
    with get_db_session() as s:
        yield s


def _register(ledger, session, **overrides):
    payload = {
        "name": "daily edition",
        "tier": "system",
        "dimensions": ["distribution", "proof"],
        "expected_external_consequence": "one reader outside the org returns unprompted",
        "proof_deadline_days": 30,
    }
    payload.update(overrides)
    return ledger.register(session, **payload)


# ------------------------------------------------------------------ #
# The hierarchy is a hierarchy
# ------------------------------------------------------------------ #


def test_tiers_ascend_from_action_to_infrastructure():
    assert TIERS[0] == "action"
    assert TIERS[-1] == "infrastructure"
    assert tier_rank("action") < tier_rank("business") < tier_rank("infrastructure")


def test_opus_maximus_is_not_a_tier(ledger, session):
    """The whole is not a component of itself."""
    assert "opus_maximus" not in TIERS
    with pytest.raises(UndeclaredCompoundingError):
        _register(ledger, session, tier="opus_maximus")


def test_the_seven_dimensions_are_exactly_the_seven():
    assert set(COMPOUNDING_DIMENSIONS) == {
        "capability",
        "knowledge",
        "capital",
        "proof",
        "distribution",
        "autonomy",
        "infrastructure",
    }


# ------------------------------------------------------------------ #
# Declaration
# ------------------------------------------------------------------ #


def test_component_declaring_no_dimension_is_refused(ledger, session):
    with pytest.raises(UndeclaredCompoundingError, match="at least one"):
        _register(ledger, session, dimensions=[])


def test_component_declaring_an_invented_dimension_is_refused(ledger, session):
    with pytest.raises(UndeclaredCompoundingError, match="not a compounding dimension"):
        _register(ledger, session, dimensions=["elegance"])


def test_component_declaring_a_real_dimension_is_admitted(ledger, session):
    """Negative control: the guard permits."""
    record = _register(ledger, session, dimensions=["capital"])
    assert record.state == "PROVISIONAL"
    assert record.dimensions == ["capital"]


def test_component_without_a_named_consequence_is_refused(ledger, session):
    with pytest.raises(UndeclaredCompoundingError, match="external consequence"):
        _register(ledger, session, expected_external_consequence="   ")


def test_component_without_a_deadline_is_refused(ledger, session):
    with pytest.raises(UndeclaredCompoundingError, match="never comes due"):
        _register(ledger, session, proof_deadline_days=0)


def test_deadline_is_stored_ahead_of_now(ledger, session):
    record = _register(ledger, session, proof_deadline_days=14)
    assert record.proof_deadline > datetime.now(timezone.utc)


# ------------------------------------------------------------------ #
# Composition
# ------------------------------------------------------------------ #


def test_a_component_cannot_compose_into_a_lower_tier(ledger, session):
    business = _register(ledger, session, name="storefront", tier="business")
    with pytest.raises(UndeclaredCompoundingError, match="cannot compose into"):
        _register(
            ledger,
            session,
            name="the network",
            tier="network",
            parent_id=business.id,
        )


def test_a_component_composes_into_a_higher_tier(ledger, session):
    """Negative control: upward composition is the normal case."""
    network = _register(ledger, session, name="the network", tier="network")
    child = _register(
        ledger, session, name="storefront", tier="business", parent_id=network.id
    )
    assert child.parent_id == network.id


def test_orphans_are_named(ledger, session):
    _register(ledger, session, name="a clever asset", tier="asset")
    report = ledger.compounding_report(session)
    assert "a clever asset" in report["orphans"]


def test_infrastructure_is_not_an_orphan(ledger, session):
    _register(ledger, session, name="the rails", tier="infrastructure")
    assert ledger.orphans(session) == []


# ------------------------------------------------------------------ #
# Proof must come from outside
# ------------------------------------------------------------------ #


def test_a_repository_path_is_not_a_consequence(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(SelfReferentialProofError):
        ledger.record_proof(
            session,
            record.id,
            evidence_tier="real_payment",
            external_reference="tests/test_compounding_ledger.py",
        )


def test_a_simulation_reference_is_not_a_consequence(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(SelfReferentialProofError):
        ledger.record_proof(
            session,
            record.id,
            evidence_tier="reconciled_real_outcome",
            external_reference="shadow publish receipt SIMULATION-1",
        )


def test_one_component_cannot_be_evidence_for_another(ledger, session):
    """The exact failure this module exists to catch: internal coherence."""
    _register(ledger, session, name="the mailing list", tier="asset")
    subject = _register(ledger, session, name="daily edition", tier="system")
    with pytest.raises(SelfReferentialProofError, match="outside the work"):
        ledger.record_proof(
            session,
            subject.id,
            evidence_tier="real_user_behavior",
            external_reference="growth of the mailing list",
        )


def test_evidence_below_the_bar_is_refused(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(InsufficientProofError, match="inside the building"):
        ledger.record_proof(
            session,
            record.id,
            evidence_tier="reproduced_test",
            external_reference="a stranger in Lisbon replied to the edition",
        )


def test_a_tier_off_the_hierarchy_is_refused(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(InsufficientProofError, match="evidence hierarchy"):
        ledger.record_proof(
            session,
            record.id,
            evidence_tier="vibes",
            external_reference="a stranger in Lisbon replied to the edition",
        )


def test_external_evidence_at_the_bar_is_admitted(ledger, session):
    """Negative control: the guard permits real outside consequence."""
    record = _register(ledger, session)
    proof = ledger.record_proof(
        session,
        record.id,
        evidence_tier=MINIMUM_PROOF_TIER,
        external_reference="a stranger in Lisbon ran the pilot for two weeks",
    )
    assert proof.admitted is True
    assert record.state == "PROVEN"
    assert record.verdict == "INTEGRATE"


def test_refused_proof_is_still_recorded(ledger, session):
    """A refusal is a finding about the world, not an absence of one."""
    record = _register(ledger, session)
    with pytest.raises(InsufficientProofError):
        ledger.record_proof(
            session,
            record.id,
            evidence_tier="simulation",
            external_reference="a stranger in Lisbon replied",
        )
    assert record.rejected_proof_count == 1
    assert len(ledger.proofs_for(session, record.id)) == 1


def test_best_evidence_tier_only_rises(ledger, session):
    record = _register(ledger, session)
    ledger.record_proof(
        session,
        record.id,
        evidence_tier="reconciled_real_outcome",
        external_reference="bank settlement 8812 cleared",
    )
    ledger.record_proof(
        session,
        record.id,
        evidence_tier="authorized_pilot",
        external_reference="a second pilot ran in Porto",
    )
    assert record.best_evidence_tier == "reconciled_real_outcome"


def test_internal_reference_detection_permits_the_world():
    assert is_internal_reference("services/canon.py") is True
    assert is_internal_reference("") is True
    assert is_internal_reference("invoice 4471 settled by Banco Santander") is False


# ------------------------------------------------------------------ #
# Deadlines force a verdict, and INTEGRATE is not among them
# ------------------------------------------------------------------ #


def test_overdue_unproven_component_cannot_be_integrated(ledger, session):
    record = _register(ledger, session, proof_deadline_days=1)
    later = datetime.now(timezone.utc) + timedelta(days=2)
    due = ledger.adjudicate(session, now=later)
    assert len(due) == 1
    assert due[0]["allowed_verdicts"] == list(FORCED_VERDICTS)
    assert "INTEGRATE" not in due[0]["allowed_verdicts"]


def test_never_attempted_is_recommended_for_harvest(ledger, session):
    record = _register(ledger, session, proof_deadline_days=1)
    later = datetime.now(timezone.utc) + timedelta(days=2)
    assert ledger.adjudicate(session, now=later)[0]["recommended"] == "HARVEST"


def test_attempted_and_missed_is_recommended_for_modify(ledger, session):
    """Reaching for the consequence and missing is different from not reaching."""
    record = _register(ledger, session, proof_deadline_days=1)
    with pytest.raises(InsufficientProofError):
        ledger.record_proof(
            session,
            record.id,
            evidence_tier="working_prototype",
            external_reference="two readers in Lisbon opened it",
        )
    later = datetime.now(timezone.utc) + timedelta(days=2)
    assert ledger.adjudicate(session, now=later)[0]["recommended"] == "MODIFY"


def test_a_proven_component_is_never_overdue(ledger, session):
    """Negative control: proof stops the clock."""
    record = _register(ledger, session, proof_deadline_days=1)
    ledger.record_proof(
        session,
        record.id,
        evidence_tier="real_payment",
        external_reference="invoice 4471 settled by Banco Santander",
    )
    later = datetime.now(timezone.utc) + timedelta(days=400)
    assert ledger.adjudicate(session, now=later) == []


def test_modification_without_a_change_is_refused(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(UndeclaredCompoundingError, match="just an extension"):
        ledger.modify(session, record.id, change="", extra_days=30)


def test_modification_rearms_the_clock(ledger, session):
    """Negative control: a real change buys real time."""
    record = _register(ledger, session, proof_deadline_days=1)
    ledger.modify(
        session,
        record.id,
        change="stop publishing to a rented feed, publish to the list",
        extra_days=30,
    )
    later = datetime.now(timezone.utc) + timedelta(days=2)
    assert ledger.adjudicate(session, now=later) == []


# ------------------------------------------------------------------ #
# Nothing dies unharvested
# ------------------------------------------------------------------ #


def test_killing_before_harvesting_is_refused(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(UnharvestedKillError, match="tuition"):
        ledger.kill(session, record.id, reason="no one read it")


def test_harvest_without_a_lesson_is_a_deletion_and_is_refused(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(UndeclaredCompoundingError, match="deletion"):
        ledger.harvest(session, record.id, lesson="  ")


def test_harvest_then_kill_is_permitted(ledger, session):
    """Negative control: the sequence the rule is protecting works."""
    record = _register(ledger, session)
    ledger.harvest(
        session,
        record.id,
        lesson="a daily cadence outruns the supply of things worth saying",
        transferable_to=["weekly edition"],
        cost_paid="six weeks",
    )
    killed = ledger.kill(session, record.id, reason="cadence was wrong, not the format")
    assert killed.state == "KILLED"
    assert len(ledger.harvests(session)) == 1


def test_the_lesson_outlives_the_component(ledger, session):
    record = _register(ledger, session)
    ledger.harvest(session, record.id, lesson="daily is too fast")
    ledger.kill(session, record.id, reason="killed")
    assert ledger.harvests(session)[0].lesson == "daily is too fast"
    report = ledger.compounding_report(session)
    assert report["lessons_banked"] == 1
    assert report["components"] == 0


# ------------------------------------------------------------------ #
# The ceiling: no new construction on top of unproven construction
# ------------------------------------------------------------------ #


def test_debt_ceiling_stops_further_building(ledger, session):
    for index in range(ARCHITECTURE_DEBT_CEILING):
        _register(ledger, session, name=f"component {index}", tier="asset")
    with pytest.raises(ArchitectureDebtError, match="before building more"):
        _register(ledger, session, name="one more clever idea", tier="asset")


def test_proving_something_reopens_the_ceiling(ledger, session):
    """Negative control: the way past the ceiling is proof, and it works."""
    first = None
    for index in range(ARCHITECTURE_DEBT_CEILING):
        record = _register(ledger, session, name=f"component {index}", tier="asset")
        first = first or record
    ledger.record_proof(
        session,
        first.id,
        evidence_tier="real_payment",
        external_reference="invoice 4471 settled by Banco Santander",
    )
    admitted = _register(ledger, session, name="one earned idea", tier="asset")
    assert admitted.state == "PROVISIONAL"


def test_harvesting_also_reopens_the_ceiling(ledger, session):
    """Killing your own work is a legitimate way to earn the right to build."""
    first = None
    for index in range(ARCHITECTURE_DEBT_CEILING):
        record = _register(ledger, session, name=f"component {index}", tier="asset")
        first = first or record
    ledger.harvest(session, first.id, lesson="this tier was never the constraint")
    assert _register(ledger, session, name="a replacement", tier="asset")


# ------------------------------------------------------------------ #
# The report refuses to flatter
# ------------------------------------------------------------------ #


def test_a_perfectly_coherent_system_with_no_outside_proof_reads_as_architecture_only(
    ledger, session
):
    """The whole point. Six tiers, all consistent, all imaginary."""
    parent = None
    for tier in reversed(TIERS):
        parent = ledger.register(
            session,
            name=f"the {tier} layer",
            tier=tier,
            dimensions=["capability", "knowledge"],
            expected_external_consequence=f"someone outside uses the {tier} layer",
            proof_deadline_days=30,
            parent_id=parent.id if parent else None,
        )

    report = ledger.compounding_report(session)
    assert report["verdict"] == "ARCHITECTURE_ONLY"
    assert report["components"] == len(TIERS)
    assert report["proven"] == 0
    assert report["proof_ratio"] == 0.0
    assert report["highest_proven_tier"] is None
    assert report["dimensions_claimed_but_unproven"] == ["capability", "knowledge"]


def test_report_reads_as_compounding_only_when_most_of_it_is_proven(ledger, session):
    """Negative control: the report can say yes, and only for the right reason."""
    a = _register(ledger, session, name="the list", tier="asset")
    b = _register(ledger, session, name="the edition", tier="system")
    for record, reference in (
        (a, "invoice 4471 settled by Banco Santander"),
        (b, "a stranger in Lisbon ran the pilot for two weeks"),
    ):
        ledger.record_proof(
            session,
            record.id,
            evidence_tier="real_payment" if record is a else "authorized_pilot",
            external_reference=reference,
        )
    report = ledger.compounding_report(session)
    assert report["verdict"] == "COMPOUNDING"
    assert report["proof_ratio"] == 1.0
    assert report["highest_proven_tier"] == "system"
    assert report["dimensions_claimed_but_unproven"] == []


def test_empty_ledger_says_empty_not_compounding(ledger, session):
    assert ledger.compounding_report(session)["verdict"] == "EMPTY"


def test_report_names_the_dimensions_claimed_but_never_shown(ledger, session):
    _register(ledger, session, name="the rails", tier="infrastructure",
              dimensions=["autonomy", "infrastructure"])
    proven = _register(ledger, session, name="the list", tier="asset",
                       dimensions=["distribution"])
    ledger.record_proof(
        session,
        proven.id,
        evidence_tier="real_user_behavior",
        external_reference="412 people opened it twice without a prompt",
    )
    report = ledger.compounding_report(session)
    assert report["dimensions_proven"] == ["distribution"]
    assert report["dimensions_claimed_but_unproven"] == ["autonomy", "infrastructure"]


def test_mutating_a_component_does_not_duplicate_it(ledger, session):
    """The store's add() appends, so re-adding a tracked record clones it."""
    record = _register(ledger, session)
    ledger.modify(session, record.id, change="narrow the audience", extra_days=10)
    ledger.harvest(session, record.id, lesson="the audience was the wrong shape")
    ledger.kill(session, record.id, reason="wrong shape")
    assert len(session.query(ComponentRecord).all()) == 1


def test_composition_does_not_duplicate_either(ledger, session):
    parent = _register(ledger, session, name="the network", tier="network")
    child = _register(ledger, session, name="the list", tier="asset")
    ledger.compose(session, child.id, parent.id)
    ledger.compose(session, child.id, parent.id)
    assert len(session.query(ComponentRecord).all()) == 2
    assert child.parent_id == parent.id


def test_composing_downward_is_still_refused_after_registration(ledger, session):
    parent = _register(ledger, session, name="one action", tier="action")
    child = _register(ledger, session, name="the rails", tier="infrastructure")
    with pytest.raises(UndeclaredCompoundingError, match="cannot compose into"):
        ledger.compose(session, child.id, parent.id)


def test_a_component_cannot_compose_into_itself(ledger, session):
    record = _register(ledger, session)
    with pytest.raises(UndeclaredCompoundingError, match="into itself"):
        ledger.compose(session, record.id, record.id)
