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
        return {
            "type": "POST_THREAD",
            "topic": "energy",
            "intensity": 3,
            "hour_bin": 15,
            "cta_variant": "thread_default",
            "arm_metadata": {
                "post_type": "thread",
                "topic": "energy",
                "hour_bin": 15,
                "cta_variant": "thread_default",
                "intensity": 3,
                "sampled_prob": 0.42,
            },
        }

    async def fake_make_thread(topic, intensity):
        return {
            "posts": [
                {"content": "Segment one https://www.reuters.com/a", "media": []},
                {"content": "Segment two https://www.reuters.com/b", "media": []},
            ],
            "dm_copy": "DM preview",
        }

    log_calls = []

    def fake_log(session, *, tweet_id, post_type, topic, hour_bin, cta_variant, intensity, sampled_prob):
        log_calls.append(
            {
                "tweet_id": tweet_id,
                "post_type": post_type,
                "topic": topic,
                "hour_bin": hour_bin,
                "cta_variant": cta_variant,
                "intensity": intensity,
                "sampled_prob": sampled_prob,
            }
        )

    monkeypatch.setattr(runner.crisis_service, "guard", lambda action: True)
    monkeypatch.setattr(runner.selector, "decide_next_action", fake_decide)
    monkeypatch.setattr(runner.generator, "make_thread", fake_make_thread)
    monkeypatch.setattr(runner, "multiplexer", types.SimpleNamespace(publish=fake_publish))
    monkeypatch.setattr(runner.optimizer.experiments, "log_arm_selection", fake_log)

    previous_live = runner.config.LIVE
    runner.config.LIVE = True

    await runner.publish_thread_job()

    runner.config.LIVE = previous_live

    assert len(publish_calls) == 2
    assert publish_calls[0]["in_reply_to"] is None
    assert publish_calls[1]["in_reply_to"] == "id1"
    assert publish_calls[0]["metadata"]["thread_index"] == 0
    assert publish_calls[0]["metadata"]["hour_bin"] == 15

    with get_db_session() as session:
        tweets = session.query(Tweet).all()
        actions = session.query(Action).all()

    assert {tweet.kind for tweet in tweets} == {"thread_root", "thread_segment"}
    root_tweet = next(tweet for tweet in tweets if tweet.kind == "thread_root")
    assert root_tweet.hour_bin == 15
    assert root_tweet.cta_variant == "thread_default"
    assert any(action.kind == "thread_published" for action in actions)
    assert log_calls and log_calls[0]["post_type"] == "thread"
    assert log_calls[0]["hour_bin"] == 15


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


@pytest.mark.asyncio
async def test_reply_mentions_logs_bandit_metadata(monkeypatch):
    init_db()

    mention = {"id": "m1", "text": "Hello there", "username": "ally"}
    contexts = []

    class FakeXClient:
        async def get_mentions(self):
            return [mention]

    async def fake_make_reply(context, intensity):
        contexts.append(context)
        return {"content": "Thanks for the tag!"}

    async def fake_publish(content, *, kind, intensity, in_reply_to, metadata=None, quote_to=None):
        return {
            "x": SocialPostResult(platform="x", post_id="reply1", dry_run=False, meta=metadata)
        }

    async def fake_decide():
        return {
            "type": "REPLY_MENTIONS",
            "intensity": 2,
            "topic": "coordination",
            "hour_bin": 9,
            "cta_variant": "reply_default",
            "arm_metadata": {
                "post_type": "reply",
                "topic": "coordination",
                "hour_bin": 9,
                "cta_variant": "reply_default",
                "intensity": 2,
                "sampled_prob": 0.6,
            },
        }

    log_calls = []

    def fake_log(session, *, tweet_id, post_type, topic, hour_bin, cta_variant, intensity, sampled_prob):
        log_calls.append(
            {
                "tweet_id": tweet_id,
                "post_type": post_type,
                "topic": topic,
                "hour_bin": hour_bin,
                "cta_variant": cta_variant,
                "intensity": intensity,
                "sampled_prob": sampled_prob,
            }
        )

    previous_live = runner.config.LIVE

    monkeypatch.setattr(runner.crisis_service, "guard", lambda action: True)
    monkeypatch.setattr(runner.selector, "decide_next_action", fake_decide)
    monkeypatch.setattr(runner.generator, "make_reply", fake_make_reply)
    monkeypatch.setattr(runner, "multiplexer", types.SimpleNamespace(publish=fake_publish))
    monkeypatch.setattr(runner, "x_client", FakeXClient())
    monkeypatch.setattr(runner.optimizer.experiments, "log_arm_selection", fake_log)

    runner.config.LIVE = True

    await runner.reply_mentions_job()

    runner.config.LIVE = previous_live

    assert contexts and contexts[0]["topic"] == "coordination"

    with get_db_session() as session:
        tweets = session.query(Tweet).all()

    assert len(tweets) == 1
    stored = tweets[0]
    assert stored.topic == "coordination"
    assert stored.hour_bin == 9
    assert stored.cta_variant == "reply_default"
    assert log_calls and log_calls[0]["post_type"] == "reply"
    assert log_calls[0]["hour_bin"] == 9
