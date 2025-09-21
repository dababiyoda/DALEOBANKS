import pytest

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
