"""Client side of the zero-trust bridge: outbound signing, response
verification, replayed-response rejection, and the circuit breaker that
fails closed instead of hammering a degraded remote."""

import io
import json
import time

import pytest

from db.models import OpportunityPacket
from db.session import init_db
from services.bridge_security import (
    H_IDENTITY, H_NONCE, H_SCHEMA, H_SIGNATURE, H_TIMESTAMP, H_IDEMPOTENCY,
    build_headers, sign,
)
from services.ledger import DecisionLedger
from services.venture_protocol import SCHEMA_VERSION
from services.wealthmachine_client import CircuitOpenError, WealthMachineClient

KEY = "test-signing-key"


class _FakeResponse:
    def __init__(self, payload, headers=None):
        self._raw = json.dumps(payload).encode()
        self.headers = _HeaderBag(headers or {})

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _HeaderBag(dict):
    def items(self):
        return super().items()


def _client(tmp_path):
    init_db()
    return WealthMachineClient(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def _packet():
    return OpportunityPacket(evidence=["e1"], possible_offer="guide",
                             monetization_paths=["paid guide"])


def _assessment_wire(packet):
    return {
        "opportunity_packet_id": packet.id, "go_no_go": "defer",
        "opportunity_score": 0.5, "requires_human_approval": True,
    }


def _signed_response(packet):
    body = json.dumps(_assessment_wire(packet)).encode()
    headers = build_headers(body, identity="wealthmachine",
                            schema_version=SCHEMA_VERSION)
    return _FakeResponse(_assessment_wire(packet), headers)


def test_outbound_requests_are_signed(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wm.local")
    monkeypatch.setenv("WEALTHMACHINE_SIGNING_KEY", KEY)
    client = _client(tmp_path)
    packet = _packet()
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["headers"] = {k.lower(): v for k, v in request.header_items()}
        seen["body"] = request.data
        return _signed_response(packet)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assessment = client.evaluate(packet)

    headers = seen["headers"]
    assert headers[H_IDENTITY.lower()] == "daleobanks"
    assert headers[H_IDEMPOTENCY.lower()] == packet.id  # packet id = idempotency
    assert headers[H_SCHEMA.lower()] == SCHEMA_VERSION
    # The signature verifies against the exact bytes that were sent.
    expected = sign(KEY, "daleobanks", headers[H_TIMESTAMP.lower()],
                    headers[H_NONCE.lower()], packet.id, SCHEMA_VERSION,
                    seen["body"])
    assert headers[H_SIGNATURE.lower()] == expected
    assert assessment.requires_human_approval is True


def test_forged_response_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wm.local")
    monkeypatch.setenv("WEALTHMACHINE_SIGNING_KEY", KEY)
    client = _client(tmp_path)
    packet = _packet()

    def fake_urlopen(request, timeout=None):
        body = json.dumps(_assessment_wire(packet)).encode()
        headers = build_headers(body, identity="wealthmachine",
                                schema_version=SCHEMA_VERSION)
        headers[H_SIGNATURE] = "0" * 64  # forged
        return _FakeResponse(_assessment_wire(packet), headers)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(Exception):
        client.evaluate(packet)


def test_replayed_response_nonce_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wm.local")
    monkeypatch.setenv("WEALTHMACHINE_SIGNING_KEY", KEY)
    client = _client(tmp_path)
    packet = _packet()
    canned = _signed_response(packet)  # one signed response, served twice

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda request, timeout=None: canned)
    client.evaluate(packet)  # first use of the nonce: fine
    with pytest.raises(Exception):
        client.evaluate(packet)  # replayed nonce: refused


def test_circuit_breaker_opens_and_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wm.local")
    monkeypatch.delenv("WEALTHMACHINE_SIGNING_KEY", raising=False)
    client = _client(tmp_path)
    packet = _packet()

    def failing_urlopen(request, timeout=None):
        raise ConnectionError("service unavailable")

    monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)
    for _ in range(client.FAILURE_THRESHOLD):
        with pytest.raises(ConnectionError):
            client.evaluate(packet)

    # The circuit is now open: no further network attempts are made.
    def must_not_be_called(request, timeout=None):  # pragma: no cover
        raise AssertionError("network call while circuit open")

    monkeypatch.setattr("urllib.request.urlopen", must_not_be_called)
    with pytest.raises(CircuitOpenError):
        client.evaluate(packet)
    assert client.ledger.replay("bridge_circuit_opened")


def test_unsigned_local_mode_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("WEALTHMACHINE_URL", "http://wm.local")
    monkeypatch.delenv("WEALTHMACHINE_SIGNING_KEY", raising=False)
    client = _client(tmp_path)
    packet = _packet()

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(_assessment_wire(packet)),
    )
    assessment = client.evaluate(packet)
    assert assessment.go_no_go == "defer"
