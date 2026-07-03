"""Tests for the world model: durable memory of the observed environment."""

from services.world_model import WorldModel


def _model(tmp_path):
    return WorldModel(path=str(tmp_path / "world.jsonl"))


def test_observations_are_recallable(tmp_path):
    model = _model(tmp_path)
    model.observe(kind="mention", entity="gridwonk",
                  summary="interconnection queues are the real bottleneck")
    model.observe(kind="trend", summary="quadratic funding")

    hits = model.recall("interconnection bottleneck", k=1)
    assert len(hits) == 1
    assert hits[0]["meta"]["kind"] == "mention"
    assert hits[0]["meta"]["entity"] == "gridwonk"
    assert "observed_at" in hits[0]["meta"]


def test_perception_payload_is_folded_in(tmp_path):
    model = _model(tmp_path)
    payload = {
        "x": {
            "mentions": [
                {"id": "m1", "username": "ally", "text": "love the grid proposal"},
            ],
            "home_timeline": [
                {"id": "t1", "username": "wonk", "text": "transmission reform news"},
            ],
            "trending_topics": [{"name": "energy markets"}, "governance"],
        }
    }

    observed = model.observe_perception(payload)

    assert observed == 4
    assert len(model) == 4
    trends = [r for r in model.recall("energy markets", k=4) if r["meta"]["kind"] == "trend"]
    assert trends


def test_world_model_survives_restart(tmp_path):
    path = str(tmp_path / "world.jsonl")
    WorldModel(path=path).observe(kind="mention", entity="ally", summary="pilot feedback")

    reloaded = WorldModel(path=path)
    assert len(reloaded) == 1
    assert reloaded.recall("pilot feedback", k=1)


def test_empty_and_malformed_observations_are_safe(tmp_path):
    model = _model(tmp_path)
    assert model.observe(kind="mention", summary="") is None
    assert model.observe_perception({}) == 0
    assert model.observe_perception({"x": {"mentions": ["not-a-dict"]}}) == 0


def test_generation_context_includes_world_context(tmp_path, monkeypatch):
    from services import world_model as wm_module
    from db.session import init_db, get_db_session
    from services.memory import MemoryService

    isolated = WorldModel(path=str(tmp_path / "world.jsonl"))
    isolated.observe(kind="trend", summary="grid interconnection reform")
    monkeypatch.setattr(wm_module, "_SHARED_WORLD_MODEL", isolated)

    init_db()
    service = MemoryService()
    with get_db_session() as session:
        context = service.get_context_for_generation(session, topic="interconnection")

    assert context["world_context"] == ["grid interconnection reform"]
