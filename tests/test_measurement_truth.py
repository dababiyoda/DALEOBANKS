"""Adversarial acceptance cases: analytics must never manufacture outcomes.

Each test reproduces a defect found on main at 8749a12 and fails there:

A. generated success language created outcome records (pilots, partners,
   helpfulness) that fed impact -> J-score -> bandit reward;
B. follower snapshots recorded a placeholder count of 1000;
C. the dashboard reported fixed healthy values for unobserved dependencies;
D. policy probabilities were computed but never reached the bandit, and an
   empty candidate set fell back to every arm or a publishing placeholder;
E. engagement earned reward even while integrity incidents accumulated;
F. the persona instructed the agent to conceal that it is an AI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import types
from pathlib import Path

import pytest

import runner
from db.models import (
    Action,
    CoalitionPartner,
    FollowersSnapshot,
    HelpfulnessFeedback,
    PilotAcceptance,
)
from db.session import get_db_session, init_db
from services.analytics import AnalyticsService
from services.bandit import ThompsonBandit
from services.persona_store import PersonaSchema
from services.reward_integrity import qualify_reward
from services.system_status import build_system_status

ROOT = Path(__file__).resolve().parents[1]


def setup_function() -> None:
    init_db()


def _count(model) -> int:
    with get_db_session() as session:
        return len(session.query(model).all())


# --- A. Language is not an outcome -----------------------------------------


def test_generated_pilot_language_creates_no_pilot():
    service = AnalyticsService()
    text = "Huge news: the city pilot accepted! Our partner coalition signed the pilot. Thank you, that helps."
    signals = service.derive_structured_outcome_from_text(content=text, context={"topic": "solar", "channel": "x"})

    assert "pilot_acceptances" not in signals
    assert "coalition_partners" not in signals
    assert "helpfulness_feedback" not in signals
    mention_types = {m["mention_type"] for m in signals["outcome_mentions"]}
    assert {"pilot_acceptance", "coalition_partner", "helpfulness"} <= mention_types
    assert all(m["evidence_tier"] == "text_mention_unverified" for m in signals["outcome_mentions"])

    with get_db_session() as session:
        rejected = service.record_structured_outcome(session, "proposal_posted", signals)
        session.commit()
        impact = service.calculate_impact_score(session, days=7)

    assert rejected == []
    assert _count(PilotAcceptance) == 0
    assert _count(CoalitionPartner) == 0
    assert _count(HelpfulnessFeedback) == 0
    assert impact["impact_score"] == 0


def test_fake_customer_reply_does_not_award_helpfulness():
    service = AnalyticsService()
    signals = service.derive_structured_outcome_from_text(
        content="thank you so much, super helpful", context={"channel": "x_mentions"}
    )
    with get_db_session() as session:
        service.record_structured_outcome(session, "mention_replied", signals)
        session.commit()
    assert _count(HelpfulnessFeedback) == 0


@pytest.mark.parametrize(
    "entry",
    [
        {"pilot_name": "solar"},  # no evidence at all
        "solar",  # bare string claim
        {"pilot_name": "solar", "evidence": {"tier": "text_mention_unverified", "reference": "tweet:1"}},
        {"pilot_name": "solar", "evidence": {"tier": "model_inference", "reference": "x"}},
        {"pilot_name": "solar", "evidence": {"tier": "operator_attested", "reference": ""}},
        {"pilot_name": "solar", "evidence": {"tier": "counterparty_signed", "reference": "doc:9", "self_authored": True}},
    ],
)
def test_unevidenced_outcome_claims_are_refused_and_retained(entry):
    service = AnalyticsService()
    with get_db_session() as session:
        rejected = service.record_structured_outcome(session, "manual", {"pilot_acceptances": [entry]})
        session.commit()
    assert _count(PilotAcceptance) == 0
    assert len(rejected) == 1 and rejected[0]["category"] == "pilot_acceptance"


def test_externally_evidenced_outcome_is_recorded():
    service = AnalyticsService()
    entry = {
        "pilot_name": "solar",
        "accepted_by": "City A",
        "evidence": {"tier": "counterparty_signed", "reference": "docusign:envelope-123"},
    }
    with get_db_session() as session:
        rejected = service.record_structured_outcome(session, "manual", {"pilot_acceptances": [entry]})
        session.commit()
    assert rejected == []
    assert _count(PilotAcceptance) == 1


@pytest.mark.asyncio
async def test_log_action_retains_refused_claims():
    await runner._log_action("proposal_posted", {"pilot_acceptances": [{"pilot_name": "x"}]})
    with get_db_session() as session:
        actions = session.query(Action).all()
    assert _count(PilotAcceptance) == 0
    assert actions[-1].meta_json["outcome_claims_rejected"][0]["reason"] == "missing evidence"


# --- B. No placeholder telemetry ------------------------------------------


@pytest.mark.asyncio
async def test_follower_snapshot_without_client_records_gap(monkeypatch):
    monkeypatch.setattr(runner, "x_client", None)
    await runner.follower_snapshot_job()
    assert _count(FollowersSnapshot) == 0
    with get_db_session() as session:
        kinds = [a.kind for a in session.query(Action).all()]
    assert "follower_snapshot_unavailable" in kinds


@pytest.mark.asyncio
async def test_follower_snapshot_when_api_cannot_measure(monkeypatch):
    async def unavailable():
        return None

    monkeypatch.setattr(runner, "x_client", types.SimpleNamespace(get_follower_count=unavailable))
    await runner.follower_snapshot_job()
    assert _count(FollowersSnapshot) == 0


@pytest.mark.asyncio
async def test_follower_snapshot_records_measured_count(monkeypatch):
    async def measured():
        return 1234

    monkeypatch.setattr(runner, "x_client", types.SimpleNamespace(get_follower_count=measured))
    await runner.follower_snapshot_job()
    with get_db_session() as session:
        counts = [s.follower_count for s in session.query(FollowersSnapshot).all()]
    assert counts == [1234]


@pytest.mark.asyncio
async def test_x_client_follower_count_parses_only_real_measurements():
    from services.x_client import XClient

    def client_returning(metrics):
        fake = XClient.__new__(XClient)
        fake.circuit_breakers = {}
        data = types.SimpleNamespace(public_metrics=metrics)
        fake.client = types.SimpleNamespace(get_me=lambda **_: types.SimpleNamespace(data=data))
        return fake

    assert await client_returning({"followers_count": 42}).get_follower_count() == 42
    assert await client_returning({}).get_follower_count() is None
    assert await client_returning(None).get_follower_count() is None
    assert await client_returning({"followers_count": "1000"}).get_follower_count() is None

    offline = XClient.__new__(XClient)
    offline.circuit_breakers = {}
    offline.client = None
    assert await offline.get_follower_count() is None


# --- C. Health reflects observations --------------------------------------


class _Crisis:
    reason = None

    def is_paused(self):
        return False


def test_disconnected_api_reports_unavailable_not_healthy():
    status = build_system_status(x_client=None, config=types.SimpleNamespace(LIVE=False), crisis_service=_Crisis())
    assert status["api_health"] == "unavailable"
    assert status["rate_limits"] == "unknown"
    assert status["observed_at"]
    assert status["memory_usage"] != "67.2 MB"


def test_open_circuit_breaker_reports_degraded_rate_limits():
    breaker = types.SimpleNamespace(is_open=lambda: True)
    client = types.SimpleNamespace(client=object(), is_healthy=lambda: True, circuit_breakers={"search": breaker})
    status = build_system_status(x_client=client, config=types.SimpleNamespace(LIVE=True), crisis_service=_Crisis())
    assert status["api_health"] == "healthy"
    assert status["rate_limits"] == "degraded"


def test_unreadable_crisis_state_is_unknown():
    class Broken:
        def is_paused(self):
            raise RuntimeError("no state")

    status = build_system_status(x_client=None, config=types.SimpleNamespace(), crisis_service=Broken())
    assert status["crisis_state"] == "UNKNOWN"


def test_health_page_has_no_hardcoded_health_claims():
    page = (ROOT / "client/src/pages/health.tsx").read_text()
    for fabricated in ["All Systems Operational", "All services online", "SQLite healthy", "125ms", "0.02%", "450/1500", "in 23 minutes"]:
        assert fabricated not in page, fabricated
    assert 'systemStatus?.api_health || "healthy"' not in page


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_health_status_derivation_in_node():
    result = subprocess.run(
        ["node", "--experimental-strip-types", str(ROOT / "tests/js/health_status.test.mjs"), str(ROOT / "client/src/lib/health-status.ts")],
        capture_output=True,
        text=True,
    )
    if "experimental-strip-types" in result.stderr and "bad option" in result.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert result.returncode == 0, result.stderr


# --- D. Policy reaches the optimizer; prohibited stays prohibited -----------


def test_policy_priors_change_selection(monkeypatch):
    monkeypatch.setattr("random.betavariate", lambda a, b: a / (a + b))
    bandit = ThompsonBandit()
    candidates = ["POST_PROPOSAL", "REPLY_MENTIONS"]
    assert bandit.select(candidates, priors={"POST_PROPOSAL": 0.9, "REPLY_MENTIONS": 0.1}) == "POST_PROPOSAL"
    assert bandit.select(candidates, priors={"POST_PROPOSAL": 0.1, "REPLY_MENTIONS": 0.9}) == "REPLY_MENTIONS"


def test_zero_prior_arm_is_never_selected():
    bandit = ThompsonBandit()
    bandit.record_outcome("SEND_VALUE_DM", 1.0)  # strong posterior must not override the policy
    for _ in range(200):
        assert bandit.select(["SEND_VALUE_DM", "REST"], priors={"SEND_VALUE_DM": 0.0, "REST": 1.0}) == "REST"


def test_empty_candidate_set_rests_instead_of_publishing():
    bandit = ThompsonBandit(arms=["POST_PROPOSAL", "SEND_VALUE_DM"])
    assert bandit.select([]) == "REST"


@pytest.mark.asyncio
async def test_selector_passes_policy_probabilities_to_bandit(monkeypatch):
    from services.selector import Selector

    class Persona:
        def get_current_persona(self):
            return {"content_mix": {}}

    selector = Selector(Persona())
    seen = {}

    def fake_select(candidates, priors=None):
        seen["priors"] = priors
        return "REST"

    monkeypatch.setattr(selector.bandit, "select", fake_select)
    await selector.decide_next_action()
    assert seen["priors"] and abs(sum(seen["priors"].values()) - 1.0) < 1e-9


# --- E. Viral but degrading is not success -------------------------------


def test_engagement_earns_no_reward_while_integrity_degrades():
    service = AnalyticsService()
    viral = service.calculate_goal_aligned_j_score(impact=0.0, revenue=0.0, authority=0.0, fame=100.0)
    without = service.calculate_goal_aligned_j_score(impact=0.0, revenue=0.0, authority=0.0, fame=0.0)
    assert viral > without

    degraded = qualify_reward(j_score=viral, j_score_without_engagement=without, integrity_incidents=2)
    assert degraded["qualified_reward"] == without
    assert degraded["engagement_credit"] is False

    clean = qualify_reward(j_score=viral, j_score_without_engagement=without, integrity_incidents=0)
    assert clean["qualified_reward"] == viral


def test_integrity_gate_never_raises_a_reward():
    assert qualify_reward(j_score=0.2, j_score_without_engagement=0.9, integrity_incidents=1)["qualified_reward"] == 0.2


def test_selector_learns_from_qualified_reward():
    from services.selector import Selector

    class Persona:
        def get_current_persona(self):
            return {"content_mix": {}}

    selector = Selector(Persona())
    selector.record_outcome({"j_score": 0.95, "qualified_reward": 0.05}, arm="POST_PROPOSAL")
    state = selector.bandit.state()["POST_PROPOSAL"]
    assert state.alpha == pytest.approx(2.05)


def test_integrity_incidents_counted_from_action_log():
    service = AnalyticsService()
    with get_db_session() as session:
        session.add(Action(kind="ethics_violation", meta_json={}))
        session.add(Action(kind="rate_limit_hit", meta_json={}))
        session.commit()
        assert service.calculate_integrity_incidents(session, days=7) == 1


# --- F. Synthetic identity is never concealed ------------------------------


def _persona(**overrides):
    data = json.loads((ROOT / "persona.json").read_text())
    data.update(overrides)
    allowed = {f for f in PersonaSchema.__dataclass_fields__ if not f.startswith("_")}
    return PersonaSchema(**{k: v for k, v in data.items() if k in allowed})


def test_shipped_persona_discloses_synthetic_identity():
    persona = _persona()
    reply = persona.prompt_overrides["reply"]
    assert "AI agent" in reply
    assert "HUMAN ONLY" not in reply


@pytest.mark.parametrize(
    "instruction",
    [
        "REPLY STYLE — HUMAN ONLY",
        "Never mention models, prompts, or automation.",
        "Pretend to be a real person.",
        "Deny that you are an AI if asked.",
    ],
)
def test_concealment_instructions_are_rejected(instruction):
    with pytest.raises(ValueError, match="synthetic identity"):
        _persona(prompt_overrides={"reply": instruction})
