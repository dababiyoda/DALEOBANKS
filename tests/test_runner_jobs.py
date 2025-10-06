import types

import pytest

import runner
from db.models import Action, Tweet
from db.session import get_db_session, init_db
from services.social_base import SocialPostResult


@pytest.mark.asyncio
async def test_publish_thread_job_records_posts(monkeypatch):
    init_db()

    publish_calls = []

    async def fake_publish(content, *, kind, intensity, in_reply_to, metadata, quote_to=None):
        publish_calls.append({
            "content": content,
            "in_reply_to": in_reply_to,
            "metadata": metadata,
        })
        index = len(publish_calls)
        return {
            "x": SocialPostResult(platform="x", post_id=f"id{index}", dry_run=False, meta=metadata)
        }

    async def fake_decide():
        return {"type": "POST_THREAD", "topic": "energy", "intensity": 3}

    async def fake_make_thread(topic, intensity):
        return {
            "posts": [
                {"content": "Segment one https://www.reuters.com/a", "media": []},
                {"content": "Segment two https://www.reuters.com/b", "media": []},
            ],
            "dm_copy": "DM preview",
        }

    monkeypatch.setattr(runner.crisis_service, "guard", lambda action: True)
    monkeypatch.setattr(runner.selector, "decide_next_action", fake_decide)
    monkeypatch.setattr(runner.generator, "make_thread", fake_make_thread)
    monkeypatch.setattr(runner, "multiplexer", types.SimpleNamespace(publish=fake_publish))

    previous_live = runner.config.LIVE
    runner.config.LIVE = True

    await runner.publish_thread_job()

    runner.config.LIVE = previous_live

    assert len(publish_calls) == 2
    assert publish_calls[0]["in_reply_to"] is None
    assert publish_calls[1]["in_reply_to"] == "id1"
    assert publish_calls[0]["metadata"]["thread_index"] == 0

    with get_db_session() as session:
        tweets = session.query(Tweet).all()
        actions = session.query(Action).all()

    assert {tweet.kind for tweet in tweets} == {"thread_root", "thread_segment"}
    assert any(action.kind == "thread_published" for action in actions)


@pytest.mark.asyncio
async def test_value_dm_job_respects_live_toggle(monkeypatch):
    init_db()

    send_calls = []
    mark_calls = []

    class DMClient:
        def is_healthy(self):
            return True

        async def send_dm(self, user_id, text):
            send_calls.append((user_id, text))
            return True

    async def fake_decide():
        return {
            "type": "SEND_VALUE_DM",
            "recipient": {"username": "ally", "topics": ["energy"], "id": "42"},
            "intensity": 2,
        }

    async def fake_dm_copy(seed, *, topic, recipient, intensity):
        return {"content": "Helpful DM", "recipient": recipient, "topic": topic, "intensity": intensity}

    monkeypatch.setattr(runner.crisis_service, "guard", lambda action: True)
    monkeypatch.setattr(runner.selector, "decide_next_action", fake_decide)
    monkeypatch.setattr(runner.selector, "mark_dm_sent", lambda target_id: mark_calls.append(target_id))
    monkeypatch.setattr(runner.generator, "make_dm_copy", fake_dm_copy)
    monkeypatch.setattr(runner, "x_client", DMClient())

    previous_live = runner.config.LIVE
    previous_enable = runner.config.ENABLE_DMS
    runner.config.LIVE = False
    runner.config.ENABLE_DMS = True

    await runner.value_dm_job()

    runner.config.LIVE = previous_live
    runner.config.ENABLE_DMS = previous_enable

    with get_db_session() as session:
        actions = session.query(Action).all()

    assert send_calls == []
    assert mark_calls == []
    drafted_actions = [a for a in actions if a.kind == "value_dm_drafted"]
    assert drafted_actions, "Expected drafted DM action"
    assert drafted_actions[0].meta_json.get("dry_run") is True
