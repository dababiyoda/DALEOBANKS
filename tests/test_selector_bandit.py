import pytest
from unittest.mock import patch

from services.selector import Selector
from db.session import init_db, get_db_session
from db.models import Tweet


class StubPersonaStore:
    def get_current_persona(self):
        return {"content_mix": {}}


class StubAnalytics:
    def __init__(self, *, penalty: float = 0.0, authority: float = 0.0):
        self._penalty = penalty
        self._authority = authority

    def calculate_penalty_score(self, session, days: int = 1):  # pragma: no cover - trivial
        return self._penalty

    def calculate_authority_signals(self, session, days: int = 1):  # pragma: no cover - trivial
        return self._authority


class StubCrisis:
    def __init__(self, *, signal: float = 0.0, paused: bool = False, threshold: float = 12.0, resume: float = 6.0):
        self._signal = signal
        self._paused = paused
        self.signal_threshold = threshold
        self.resume_threshold = resume

    def is_paused(self):  # pragma: no cover - trivial
        return self._paused

    @property
    def last_signal(self):  # pragma: no cover - trivial
        return self._signal


@pytest.mark.asyncio
async def test_selector_decide_and_record_outcome():
    selector = Selector(StubPersonaStore())
    action = await selector.decide_next_action()
    assert "type" in action
    selector.record_outcome({"j_score": 0.7}, arm=action["type"])
    state = selector.bandit.state()
    assert action["type"] in state
    assert state[action["type"]].pulls >= 1


@pytest.mark.asyncio
@patch("services.selector.Optimizer.sample_arm_combination")
@patch("random.betavariate")
async def test_bandit_rewards_shift_follow_up(mock_betavariate, mock_sample):
    mock_sample.return_value = {
        "post_type": "proposal",
        "topic": "technology",
        "hour_bin": 10,
        "cta_variant": "learn_more",
        "intensity": 2,
        "selection_method": "exploitation",
        "sampled_prob": 0.75,
    }

    mock_betavariate.side_effect = lambda alpha, beta: alpha / (alpha + beta)

    selector = Selector(StubPersonaStore())

    first_action = await selector.decide_next_action()
    assert first_action["type"] == "POST_PROPOSAL"

    # Clear cooldowns so all arms are available for the next decision
    selector.last_actions.clear()

    # Provide negative feedback for proposals and positive for replies
    selector.record_outcome({"j_score": 0.0}, arm="POST_PROPOSAL")
    selector.record_outcome({"j_score": 1.0}, arm="REPLY_MENTIONS")

    second_action = await selector.decide_next_action()
    assert second_action["type"] == "REPLY_MENTIONS"


@pytest.mark.asyncio
async def test_intensity_dampens_when_penalties_rise():
    init_db()
    with get_db_session() as session:
        session.add(Tweet(id="t1", text="hello", kind="reply", j_score=0.6))
        session.add(Tweet(id="t2", text="world", kind="reply", j_score=0.6))

    analytics = StubAnalytics(penalty=9, authority=20)
    crisis = StubCrisis(signal=3.0, paused=False)
    selector = Selector(StubPersonaStore(), analytics_service=analytics, crisis_service=crisis)
    selector.config.ADAPTIVE_INTENSITY = True
    selector._last_successful_intensity["REPLY_MENTIONS"] = 3
    selector._last_intensity_by_action["REPLY_MENTIONS"] = 3

    params = await selector._get_action_parameters("REPLY_MENTIONS")

    assert params["intensity"] == 2


@pytest.mark.asyncio
async def test_intensity_escalates_with_authority():
    init_db()
    with get_db_session() as session:
        session.add(Tweet(id="h1", text="great", kind="reply", j_score=0.9))

    analytics = StubAnalytics(penalty=0, authority=80)
    crisis = StubCrisis(signal=0.0, paused=False)
    selector = Selector(StubPersonaStore(), analytics_service=analytics, crisis_service=crisis)
    selector.config.ADAPTIVE_INTENSITY = True
    selector._last_successful_intensity["REPLY_MENTIONS"] = 1
    selector._last_intensity_by_action["REPLY_MENTIONS"] = 1

    params = await selector._get_action_parameters("REPLY_MENTIONS")

    assert params["intensity"] == 2


@pytest.mark.asyncio
async def test_intensity_crisis_forces_minimum():
    init_db()
    with get_db_session() as session:
        session.add(Tweet(id="c1", text="steady", kind="reply", j_score=0.7))

    analytics = StubAnalytics(penalty=0, authority=40)
    crisis = StubCrisis(signal=20.0, paused=True, threshold=12.0)
    selector = Selector(StubPersonaStore(), analytics_service=analytics, crisis_service=crisis)
    selector.config.ADAPTIVE_INTENSITY = True
    selector._last_successful_intensity["REPLY_MENTIONS"] = 3
    selector._last_intensity_by_action["REPLY_MENTIONS"] = 3

    params = await selector._get_action_parameters("REPLY_MENTIONS")

    assert params["intensity"] == selector.config.MIN_INTENSITY_LEVEL
