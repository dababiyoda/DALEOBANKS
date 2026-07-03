"""Tests for gated discovery: the mind proposes, the human decides."""

import pytest
from fastapi import HTTPException

import runner
from db.models import DiscoveryProposal, Relationship, Tweet
from db.session import get_db_session, init_db
from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances
from services.perception import PerceptionService


@pytest.fixture
def discovery_env(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    yield ledger
    reset_shared_instances()


def _seed_engagement(session):
    rel = Relationship(id="u1", handle="gridwonk", interaction_count=4,
                       sentiment_score=0.5, topics=["transmission"])
    session.add(rel)
    session.add(Relationship(id="u2", handle="passerby", interaction_count=1))
    for i in range(2):
        session.add(Tweet(id=f"t{i}", text="x", kind="proposal",
                          topic="interconnection", j_score=0.8))
    session.commit()


async def test_discovery_job_files_proposals_from_engagement(discovery_env):
    ledger = discovery_env
    with get_db_session() as session:
        _seed_engagement(session)

    await runner.discovery_job()

    with get_db_session() as session:
        proposals = session.query(DiscoveryProposal).all()

    by_kind = {(p.kind, p.value) for p in proposals}
    assert ("influencer", "gridwonk") in by_kind
    assert ("keyword", "interconnection") in by_kind
    # One-off contact doesn't qualify.
    assert not any(p.value == "passerby" for p in proposals)
    assert all(p.status == "pending" for p in proposals)
    assert len(ledger.replay("discovery_proposal")) == len(proposals)

    # Second run must not duplicate.
    await runner.discovery_job()
    with get_db_session() as session:
        assert session.query(DiscoveryProposal).count() == len(proposals)


async def test_only_approved_proposals_widen_perception(discovery_env):
    perception = PerceptionService()
    baseline_voices = len(perception._voices)
    baseline_keywords = len(perception._keywords)

    with get_db_session() as session:
        session.add(DiscoveryProposal(kind="influencer", value="gridwonk",
                                      status="pending"))
        session.add(DiscoveryProposal(kind="influencer", value="approvedvoice",
                                      status="approved",
                                      evidence={"topics": ["energy"]}))
        session.add(DiscoveryProposal(kind="keyword", value="interconnection",
                                      status="approved"))
        session.add(DiscoveryProposal(kind="keyword", value="rejectedword",
                                      status="rejected"))
        session.commit()

        added = perception.apply_approved_discoveries(session)

    assert added == 2
    assert len(perception._voices) == baseline_voices + 1
    assert len(perception._keywords) == baseline_keywords + 1
    assert "approvedvoice" in perception.known_influencers()
    assert "interconnection" in perception.known_keywords()
    assert "gridwonk" not in perception.known_influencers()

    # Idempotent: applying again adds nothing.
    with get_db_session() as session:
        assert perception.apply_approved_discoveries(session) == 0


async def test_decision_endpoint_flow(discovery_env):
    ledger = discovery_env
    import app as app_module

    with get_db_session() as session:
        proposal = DiscoveryProposal(kind="keyword", value="interconnection")
        session.add(proposal)
        session.commit()
        proposal_id = proposal.id

    listing = await app_module.list_discoveries(status_filter="pending", _=None)
    assert listing["count"] == 1

    result = await app_module.decide_discovery(
        proposal_id, app_module.DecisionRequest(approve=True), None
    )
    assert result["status"] == "approved"
    assert ledger.replay("discovery_decision")[0]["payload"]["decision"] == "approved"

    # Deciding twice is refused.
    with pytest.raises(HTTPException) as exc_info:
        await app_module.decide_discovery(
            proposal_id, app_module.DecisionRequest(approve=False), None
        )
    assert exc_info.value.status_code == 409
