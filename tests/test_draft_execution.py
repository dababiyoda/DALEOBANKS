"""The one lawful route for a specific approved post: approved draft +
grant pinned to its exact text → the gated publish seam → recorded
execution visible in the DecisionEpisode."""

import asyncio

import pytest
from fastapi import HTTPException

import app as app_module
from config import get_config, update_config
from db.models import MediaAssetDraft
from db.session import get_db_session, init_db
from services.decision_episode import build_episode
from services.idea_refinery import IdeaRefinery
from services.ledger import DecisionLedger, KillSwitch, RateGovernor, set_shared_instances, reset_shared_instances
from services.operator_line import OperatorLine
from services.social_base import BaseSocialClient, SocialPostResult
from services.wealthmachine_client import WealthMachineClient

THOUGHT = ("Financial independence is not selfish. It is protection from systems "
           "that profit from dependency. Maybe a starter kit could help.")


class Platform(BaseSocialClient):
    platform = "x"

    def __init__(self):
        super().__init__(enabled=True, live=True)
        self.sent = []

    async def _publish_impl(self, *, content, kind="post", in_reply_to=None,
                            quote_to=None, intensity=1, metadata=None):
        self.sent.append(content)
        return SocialPostResult(platform="x", post_id=f"live_{len(self.sent)}",
                                dry_run=False, meta=metadata)


class Multiplexer:
    def __init__(self):
        self.clients = {"x": Platform()}


@pytest.fixture
def chain(tmp_path, monkeypatch):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger, kill_switch=KillSwitch(ledger=ledger),
                         governor=RateGovernor(max_actions=100, window_seconds=3600))
    mux = Multiplexer()
    import runner
    monkeypatch.setattr(runner, "multiplexer", mux)
    previous = get_config().LIVE
    update_config(LIVE=True)

    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    client = WealthMachineClient(ledger=ledger)
    refinery = IdeaRefinery(ledger=ledger)
    loop = asyncio.new_event_loop()
    with get_db_session() as session:
        packet = loop.run_until_complete(
            refinery.refine(session, refinery.intake(session, THOUGHT)))["opportunity"]
        assessment = client.evaluate(packet)
        session.add(assessment)
        actions = client.assessment_to_actions(session, assessment, packet, line)
        draft = actions["landing_page"]
        draft.platform = "x"
        approval = actions["approval_request"]
        line.handle_command(session, f"YES {approval.code}")
    loop.close()
    yield {"ledger": ledger, "mux": mux, "packet": packet, "draft": draft,
           "approval": approval}
    update_config(LIVE=previous)
    reset_shared_instances()


async def _approve_draft(draft_id):
    await app_module.decide_media_draft(draft_id, app_module.DecisionRequest(approve=True), None)


async def _mint(c, resource=None):
    out = await app_module.create_capability_grant(app_module.CapabilityGrantRequest(
        approval_request_id=c["approval"].id, action_type="publish_post",
        exact_action="publish the approved landing draft",
        resource=resource or c["draft"].id, named_targets=["x"],
    ), None)
    return out["grant"]["id"]


async def _execute(draft_id, grant_id):
    return await app_module.execute_media_draft(
        draft_id, app_module.DraftExecuteRequest(capability_grant_id=grant_id), None)


async def test_approved_draft_publishes_once_and_closes_the_executed_stage(chain):
    await _approve_draft(chain["draft"].id)
    grant_id = await _mint(chain)
    first = await _execute(chain["draft"].id, grant_id)
    replay = await _execute(chain["draft"].id, grant_id)

    assert first["dry_run"] is False and first["post_id"] == "live_1"
    assert replay["dry_run"] is True  # the single use is spent
    assert chain["mux"].clients["x"].sent == [chain["draft"].draft_text]

    with get_db_session() as session:
        episode = build_episode(session, chain["packet"].id, ledger=chain["ledger"])
    assert episode["capability_grant"] and episode["executed_action"]
    assert len(episode["executed_action"]) == 2  # dry runs are recorded too


async def test_a_draft_edited_after_the_grant_does_not_publish(chain):
    await _approve_draft(chain["draft"].id)
    grant_id = await _mint(chain)
    with get_db_session() as session:
        draft = session.query(MediaAssetDraft).filter(lambda d: d.id == chain["draft"].id).first()
        draft.draft_text += "\n\nGuaranteed returns."
    with pytest.raises(HTTPException) as exc:
        await _execute(chain["draft"].id, grant_id)
    assert exc.value.status_code == 422 and "changed" in exc.value.detail
    assert chain["mux"].clients["x"].sent == []


async def test_unapproved_draft_and_foreign_grant_are_refused(chain):
    grant_id = await _mint(chain)
    with pytest.raises(HTTPException, match="not approved"):
        await _execute(chain["draft"].id, grant_id)

    await _approve_draft(chain["draft"].id)
    other_draft = chain["approval"].payload["draft_ids"][1]
    other_grant = await _mint(chain, resource=other_draft)
    with pytest.raises(HTTPException, match="does not authorize"):
        await _execute(chain["draft"].id, other_grant)
    assert chain["mux"].clients["x"].sent == []


async def test_live_off_records_a_dry_run_and_spends_nothing(chain):
    update_config(LIVE=False)
    await _approve_draft(chain["draft"].id)
    grant_id = await _mint(chain)
    result = await _execute(chain["draft"].id, grant_id)
    assert result["dry_run"] is True and chain["mux"].clients["x"].sent == []
    grant = (await app_module.get_capability_grant(grant_id, None))
    assert grant["uses_consumed"] == 0
