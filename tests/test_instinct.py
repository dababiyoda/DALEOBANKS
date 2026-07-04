"""Tests for the Instinct Engine (pre-generation reflex) and Identity Gate
(post-generation draft review)."""

from services.instinct import (
    ALLOW, BLOCK, CREATE_ASSET, DM_INSTEAD, ENGAGE, HUMAN_REVIEW, IGNORE,
    NEEDS_HUMAN, RESEARCH_FIRST, REWRITE, IdentityGate, InstinctEngine,
)
from services.ledger import DecisionLedger


# ---------------------------------------------------------------------- #
# Instinct Engine
# ---------------------------------------------------------------------- #
def test_ragebait_is_blocked():
    verdict = InstinctEngine().assess({
        "kind": "mention",
        "topic": "energy",
        "text": "RT if you agree! They DESTROYED him! Wake up sheeple!",
    })
    assert verdict["verdict"] == BLOCK
    assert verdict["scores"]["ragebait_risk"] >= 0.6


def test_insults_are_blocked():
    verdict = InstinctEngine().assess({
        "kind": "mention", "topic": "energy",
        "text": "only an idiot would post this",
    })
    assert verdict["verdict"] == BLOCK


def test_off_mission_stranger_is_ignored():
    verdict = InstinctEngine().assess({
        "kind": "mention",
        "topic": "gossip",
        "text": "did you watch that celebrity drama episode last night",
    })
    assert verdict["verdict"] == IGNORE


def test_unsourced_claims_demand_research_first():
    verdict = InstinctEngine().assess({
        "kind": "proposal",
        "topic": "energy",
        "text": "Solar always beats nuclear, 100% guaranteed, everyone knows the data",
    })
    assert verdict["verdict"] == RESEARCH_FIRST
    assert verdict["scores"]["evidence_need"] >= 0.6


def test_hostile_history_moves_to_dm():
    verdict = InstinctEngine().assess({
        "kind": "mention",
        "topic": "energy",
        "text": "you keep dodging my question about the grid",
        "relationship": {"interactions": 3, "sentiment": -0.6},
    })
    assert verdict["verdict"] == DM_INSTEAD


def test_high_stakes_goes_to_human():
    verdict = InstinctEngine().assess({
        "kind": "proposal", "topic": "energy policy", "stakes": "high",
    })
    assert verdict["verdict"] == HUMAN_REVIEW


def test_how_to_requests_become_assets():
    verdict = InstinctEngine().assess({
        "kind": "mention",
        "topic": "energy",
        "text": "how to structure a grid pilot for a small utility according to you",
    })
    assert verdict["verdict"] == CREATE_ASSET


def test_on_mission_topic_engages_and_is_ledgered(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    engine = InstinctEngine(ledger=ledger)

    verdict = engine.assess({"kind": "proposal", "topic": "energy"})
    assert verdict["verdict"] == ENGAGE

    entries = ledger.replay("instinct_verdict")
    assert entries and entries[-1]["payload"]["verdict"] == ENGAGE


def test_default_general_slot_still_engages():
    verdict = InstinctEngine().assess({"kind": "proposal", "topic": "general"})
    assert verdict["verdict"] == ENGAGE


# ---------------------------------------------------------------------- #
# Identity Gate
# ---------------------------------------------------------------------- #
def test_gate_blocks_insulting_draft():
    review = IdentityGate().review("Only an idiot would believe this take.", "reply", {})
    assert review["outcome"] == BLOCK
    assert review["scores"]["drift_risk"] >= 0.6


def test_gate_blocks_deceptive_draft():
    review = IdentityGate().review(
        "I am a human just like you, trust me on this.", "reply", {}
    )
    assert review["outcome"] == BLOCK


def test_gate_rewrites_off_voice_draft():
    review = IdentityGate().review(
        "THIS IS HUGE!!! CHECK IT OUT NOW!!! #wow #amazing #viral #trending",
        "proposal", {"topic": "energy"},
    )
    assert review["outcome"] == REWRITE
    assert review["scores"]["voice_fit"] < 0.5


def test_gate_escalates_unsourced_strong_claims():
    review = IdentityGate().review(
        "Nuclear is always guaranteed 100% safe, everyone knows this.",
        "proposal", {"topic": "energy"},
    )
    assert review["outcome"] == NEEDS_HUMAN
    assert review["scores"]["credibility_risk"] >= 0.7


def test_gate_allows_sourced_mission_fit_draft(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    gate = IdentityGate(ledger=ledger)

    review = gate.review(
        "Problem: interconnection queues stall energy pilots. Mechanism: shared "
        "dispatch incentives. Evidence: https://example.org/study. CTA: join the pilot.",
        "proposal", {"topic": "energy"},
    )
    assert review["outcome"] == ALLOW

    entries = ledger.replay("identity_gate")
    assert entries and entries[-1]["payload"]["outcome"] == ALLOW


def test_gate_allows_plain_reply_without_mission_vocabulary():
    review = IdentityGate().review(
        "Fair point — the queue history cuts both ways. What did your utility see?",
        "reply", {},
    )
    assert review["outcome"] == ALLOW
