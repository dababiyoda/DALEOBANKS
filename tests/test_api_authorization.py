from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import httpx
import jwt
import pytest
from fastapi import WebSocketException

import app as app_module
from config import get_config, validate_production_security
from services.security import require_websocket_authenticated


@pytest.mark.asyncio
async def test_consequential_mutations_reject_anonymous_callers() -> None:
    cases = [
        ("/api/crisis", {"active": True}),
        ("/api/toggle", {"live": False}),
        ("/api/mode", {"mode": "FAME"}),
        ("/api/propose", None),
        ("/api/note", {"text": "bounded note"}),
        ("/api/redirect", {"label": "test", "target_url": "https://example.com"}),
    ]
    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path, body in cases:
            response = await client.post(path, json=body)
            assert response.status_code == 403, (path, response.text)


@pytest.mark.asyncio
async def test_private_operator_reads_require_a_valid_identity() -> None:
    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/api/dashboard", "/api/opportunities", "/api/persona"):
            response = await client.get(path)
            assert response.status_code == 401, (path, response.text)

        assert (await client.get("/api/health")).status_code == 200


@pytest.mark.asyncio
async def test_authenticated_read_uses_bound_issuer_and_audience() -> None:
    cfg = get_config()
    claims = {"sub": "test-admin", "roles": ["admin"]}
    if cfg.JWT_ISSUER:
        claims["iss"] = cfg.JWT_ISSUER
    if cfg.JWT_AUDIENCE:
        claims["aud"] = cfg.JWT_AUDIENCE
    token = jwt.encode(claims, cfg.JWT_SECRET, algorithm="HS256")

    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/persona",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200, response.text


def test_websocket_rejects_missing_bearer_identity() -> None:
    websocket = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))

    with pytest.raises(WebSocketException, match="Authentication required"):
        require_websocket_authenticated(websocket)


def test_websocket_rejects_token_without_subject() -> None:
    cfg = get_config()
    claims = {"roles": ["admin"]}
    if cfg.JWT_ISSUER:
        claims["iss"] = cfg.JWT_ISSUER
    if cfg.JWT_AUDIENCE:
        claims["aud"] = cfg.JWT_AUDIENCE
    token = jwt.encode(claims, cfg.JWT_SECRET, algorithm="HS256")
    websocket = SimpleNamespace(
        headers={"authorization": f"Bearer {token}"},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    with pytest.raises(WebSocketException, match="Token subject is required"):
        require_websocket_authenticated(websocket)


def test_websocket_accepts_bound_authenticated_identity() -> None:
    cfg = get_config()
    claims = {"sub": "operator", "roles": ["admin"]}
    if cfg.JWT_ISSUER:
        claims["iss"] = cfg.JWT_ISSUER
    if cfg.JWT_AUDIENCE:
        claims["aud"] = cfg.JWT_AUDIENCE
    token = jwt.encode(claims, cfg.JWT_SECRET, algorithm="HS256")
    websocket = SimpleNamespace(
        headers={"authorization": f"Bearer {token}"},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    context = require_websocket_authenticated(websocket)

    assert context.subject == "operator"
    assert context.roles == ["admin"]


def test_production_configuration_rejects_placeholders_and_wildcards() -> None:
    unsafe = replace(
        get_config(),
        APP_ENV="production",
        ADMIN_TOKEN="choose-a-long-random-string",
        JWT_SECRET="change-me-please",
        JWT_ISSUER=None,
        JWT_AUDIENCE=None,
        ALLOWED_ORIGINS=["*"],
    )
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        validate_production_security(unsafe)


def test_production_configuration_accepts_explicit_identity_and_origins() -> None:
    safe = replace(
        get_config(),
        APP_ENV="production",
        ADMIN_TOKEN="a" * 32,
        JWT_SECRET="b" * 32,
        JWT_ISSUER="https://auth.example.test",
        JWT_AUDIENCE="daleobanks-api",
        ALLOWED_ORIGINS=["https://operator.example.test"],
    )
    validate_production_security(safe)
