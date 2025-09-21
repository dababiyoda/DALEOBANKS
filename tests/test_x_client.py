"""Unit tests for the X client wrapper covering DM and media helpers."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# Provide a minimal tweepy stub so the client module can be imported without the
# real dependency present in the test environment.
class _TooManyRequests(Exception):
    pass


class _Paginator:
    def __init__(self, *args, **kwargs):  # pragma: no cover - simple stub
        self.args = args
        self.kwargs = kwargs

    def flatten(self, limit=None):  # pragma: no cover - simple stub
        return []


sys.modules.setdefault(
    "tweepy",
    types.SimpleNamespace(
        Client=MagicMock,
        TooManyRequests=_TooManyRequests,
        Paginator=_Paginator,
    ),
)

from services.x_client import XClient


def _bind_async(method, instance):
    return types.MethodType(method, instance)


@pytest.mark.asyncio
async def test_send_dm_respects_live_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    client = XClient()

    captured = {}

    async def fake_execute(
        self,
        *,
        endpoint,
        enabled,
        live_required,
        default_result,
        func,
        **kwargs,
    ):
        captured.update(
            {
                "endpoint": endpoint,
                "enabled": enabled,
                "live_required": live_required,
            }
        )
        return default_result

    monkeypatch.setattr(client, "_execute_write", _bind_async(fake_execute, client))

    result = await client.send_dm("42", "hello")

    assert result is True
    assert captured["endpoint"] == "send_dm"
    assert captured["enabled"] is True
    # Default config has LIVE disabled, so the call should be a dry run.
    assert captured["live_required"] is False


@pytest.mark.asyncio
async def test_send_dm_executes_when_live(monkeypatch: pytest.MonkeyPatch) -> None:
    client = XClient()
    client.config.LIVE = True
    client.config.ENABLE_DMS = True

    class DummyClient:
        def __init__(self):
            self.calls = []

        def send_direct_message(self, recipient_id: str, text: str):
            self.calls.append((recipient_id, text))
            return {"ok": True}

    dummy = DummyClient()
    client.client = dummy

    async def fake_execute(
        self,
        *,
        endpoint,
        enabled,
        live_required,
        default_result,
        func,
        **kwargs,
    ):
        assert endpoint == "send_dm"
        assert enabled is True
        assert live_required is True
        return func()

    monkeypatch.setattr(client, "_execute_write", _bind_async(fake_execute, client))

    result = await client.send_dm("123", "Value-first note")

    assert result is True
    assert dummy.calls == [("123", "Value-first note")]


@pytest.mark.asyncio
async def test_upload_media_supports_video(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    client = XClient()
    client.config.LIVE = True
    client.config.ENABLE_MEDIA = True

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"fake")

    class DummyClient:
        def __init__(self):
            self.categories = []

        def media_upload(self, filename: str, media_category: str):
            self.categories.append((filename, media_category))
            response = MagicMock()
            response.media_id_string = "9876543210"
            return response

    dummy = DummyClient()
    client.client = dummy

    async def fake_execute(
        self,
        *,
        endpoint,
        enabled,
        live_required,
        default_result,
        func,
        **kwargs,
    ):
        assert endpoint == "upload_media"
        assert enabled is True
        assert live_required is True
        return func()

    monkeypatch.setattr(client, "_execute_write", _bind_async(fake_execute, client))

    media_id = await client.upload_media(str(media_file), media_type="video")

    assert media_id == "9876543210"
    # Ensure the X API receives the correct media category for video uploads.
    assert dummy.categories[-1][1] == "tweet_video"
