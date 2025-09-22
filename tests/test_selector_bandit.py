import pytest
from unittest.mock import patch

from services.selector import Selector


class StubPersonaStore:
    def get_current_persona(self):
        return {"content_mix": {}}


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
