import asyncio
import importlib
import sys
import types


def test_live_toggle_short_circuits_tweepy(monkeypatch):
    calls = {"create": 0, "like": 0}

    class DummyClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_me(self):
            return types.SimpleNamespace()

        def create_tweet(self, **kwargs):
            calls["create"] += 1
            return types.SimpleNamespace(data={"id": "tweet123"})

        def like(self, tweet_id):
            calls["like"] += 1
            return True

    class DummyPaginator:
        def __init__(self, *args, **kwargs):
            pass

        def flatten(self, limit):
            return []

    tweepy_stub = types.SimpleNamespace(
        TooManyRequests=Exception,
        Client=DummyClient,
        Paginator=lambda *args, **kwargs: DummyPaginator(),
    )

    monkeypatch.setitem(sys.modules, "tweepy", tweepy_stub)
    monkeypatch.setenv("LIVE", "true")
    monkeypatch.setenv("X_API_KEY", "key")
    monkeypatch.setenv("X_API_SECRET", "secret")
    monkeypatch.setenv("X_ACCESS_TOKEN", "token")
    monkeypatch.setenv("X_ACCESS_SECRET", "access")
    monkeypatch.setenv("X_BEARER_TOKEN", "bearer")

    import config as config_module

    importlib.reload(config_module)
    config_module.reset_config()

    monkeypatch.setattr("services.persona_store.PersonaStore.load_persona", lambda self: None)

    for module_name in ["services.x_client", "services.multiplexer", "runner", "app"]:
        sys.modules.pop(module_name, None)

    import app as app_module

    response = asyncio.run(
        app_module.toggle_live_mode(app_module.ToggleRequest(live=False))
    )
    assert response["live"] is False

    assert config_module.get_config().LIVE is False

    tweet_id = asyncio.run(app_module.x_client.create_tweet("integration test"))
    assert tweet_id == "dry_run_tweet_id"
    assert calls["create"] == 0

    liked = asyncio.run(app_module.x_client.like("12345"))
    assert liked is True
    assert calls["like"] == 0
