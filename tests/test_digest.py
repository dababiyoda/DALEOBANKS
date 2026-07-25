"""Tests for the weekly state-of-the-mind digest and gated experiment
proposals."""

from db.models import ApprovalRequest, Conversion, ExperimentProposal, Relationship, Tweet
from db.session import get_db_session, init_db
from services.digest import DigestService
from services.experiments import ExperimentsService
from services.ledger import DecisionLedger
from services.simulator import ReceptionPredictor


def _digest(tmp_path):
    return DigestService(ledger=DecisionLedger(path=str(tmp_path / "ledger.jsonl")))


def test_digest_reports_calibration_memory_and_pending(tmp_path):
    init_db()
    service = _digest(tmp_path)

    with get_db_session() as session:
        session.add(Tweet(id="t1", text="x", kind="proposal", topic="energy",
                          j_score=0.7, predicted_j=0.5))
        session.add(Relationship(id="u1", handle="ally", interaction_count=4,
                                 sentiment_score=0.3))
        session.add(Conversion(value=25.0, source="test"))
        session.add(ApprovalRequest(kind="publish", summary="pending thing"))
        session.commit()

        digest = service.build(session, ReceptionPredictor())

    assert digest["calibration"]["pairs"] == 1
    assert abs(digest["calibration"]["mean_error"] - 0.2) < 1e-6
    assert digest["activity"]["posts_total"] == 1
    assert digest["relationships"]["recurring_accounts"] == 1
    assert digest["revenue"]["measured_conversions"] == 1
    assert digest["revenue"]["measured_revenue_total"] == 25.0
    assert digest["pending_human_decisions"]["approvals"] == 1
    assert set(digest["memory"]) == {"lessons", "world_observations", "evidence"}
    assert "armed" in digest["safety"]
    # The digest itself is ledgered.
    assert service.ledger.replay("weekly_digest")


def test_digest_handles_empty_state(tmp_path):
    init_db()
    with get_db_session() as session:
        digest = _digest(tmp_path).build(session, ReceptionPredictor())

    assert digest["calibration"]["pairs"] == 0
    assert digest["activity"]["posts_total"] == 0
    assert digest["relationships"]["known_accounts"] == 0
    assert digest["activity"]["mean_j_score_this_week"] is None


def test_strong_unknown_topic_becomes_a_proposal_not_a_change(tmp_path):
    init_db()
    service = _digest(tmp_path)
    experiments = ExperimentsService()
    original_topics = list(experiments.arms["topic"])

    with get_db_session() as session:
        for i in range(4):
            session.add(Tweet(id=f"h{i}", text="x", kind="proposal",
                              topic="housing", j_score=0.8))
        session.commit()

        proposals = service.propose_experiments(session, experiments)

    assert len(proposals) == 1
    assert proposals[0].dimension == "topic"
    assert proposals[0].value == "housing"
    assert proposals[0].status == "pending"
    # Crucially: the arm space is untouched until a human approves.
    assert experiments.arms["topic"] == original_topics


def test_only_approval_widens_the_arm_space(tmp_path):
    init_db()
    service = _digest(tmp_path)
    experiments = ExperimentsService()

    with get_db_session() as session:
        for i in range(3):
            session.add(Tweet(id=f"h{i}", text="x", kind="proposal",
                              topic="housing", j_score=0.9))
        session.commit()
        service.propose_experiments(session, experiments)

        # Pending: nothing applies.
        assert service.apply_approved_experiments(session, experiments) == 0
        assert "housing" not in experiments.arms["topic"]

        # Approved: applies exactly once.
        proposal = session.query(ExperimentProposal).first()
        proposal.status = "approved"
        session.commit()

        assert service.apply_approved_experiments(session, experiments) == 1
        assert "housing" in experiments.arms["topic"]
        assert service.apply_approved_experiments(session, experiments) == 0


def test_weak_or_known_topics_are_not_proposed(tmp_path):
    init_db()
    service = _digest(tmp_path)
    experiments = ExperimentsService()

    with get_db_session() as session:
        # Known arm value -> no proposal.
        for i in range(4):
            session.add(Tweet(id=f"k{i}", text="x", kind="proposal",
                              topic="energy", j_score=0.9))
        # Weak performance -> no proposal.
        for i in range(4):
            session.add(Tweet(id=f"w{i}", text="x", kind="proposal",
                              topic="knitting", j_score=0.1))
        # Too few samples -> no proposal.
        session.add(Tweet(id="s1", text="x", kind="proposal",
                          topic="shipping", j_score=0.95))
        session.commit()

        assert service.propose_experiments(session, experiments) == []
