"""Explicit synthetic transport fixtures; never packaged application defaults."""
import json
from datetime import datetime, timezone

import pytest

from services.bridge_security import build_headers, body_digest
from services.venture_protocol import packet_to_wire

KEY = 'synthetic-shared-bridge-key'


@pytest.fixture(autouse=True)
def bridge_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv('WEALTHMACHINE_URL', 'http://localhost')
    monkeypatch.setenv('WEALTHMACHINE_MODE', 'http')
    monkeypatch.setenv('WEALTHMACHINE_SIGNING_KEY', KEY)
    monkeypatch.setenv('WEALTHMACHINE_INTAKE_TOKEN', 'synthetic-unit-fixture-only')
    monkeypatch.setenv('UNIIMENTE_BRIDGE_MODE', 'synthetic-localhost')
    monkeypatch.setenv('UNIIMENTE_BRIDGE_STATE_PATH', str(tmp_path / 'bridge.jsonl'))
    monkeypatch.setenv('UNIIMENTE_CONSTITUTION_HASH', 'sha256:' + 'a' * 64)
    monkeypatch.setenv('UNIIMENTE_LEGAL_PRINCIPAL', 'alfonso_lopez')


def assessment_wire(packet, **overrides):
    value = dict(id='assessment-' + packet.id, opportunity_packet_id=packet.id,
        schema_version='1.1', created_at='2026-09-08T00:00:00+00:00',
        go_no_go='defer', opportunity_score=.5, requires_human_approval=True,
        cases=[dict(case=c, stance=s, severity='medium', argument='Synthetic retained dissent')
               for c, s in [('bull','for'),('bear','against'),('do_nothing','neutral')]])
    value.update(overrides)
    return value


class Response:
    def __init__(self, packet, payload=None):
        self._raw = json.dumps(payload or assessment_wire(packet)).encode()
        request_body = json.dumps(packet_to_wire(packet)).encode()
        self.headers = build_headers(self._raw, identity='wealthmachine', schema_version='1.1',
            recipient='daleobanks', direction='response', status='200',
            idempotency_key=packet.id, request_digest=body_digest(request_body))
    def read(self): return self._raw
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def intercept(monkeypatch, handler):
    monkeypatch.setattr('urllib.request.OpenerDirector.open',
                        lambda self, request, timeout=None: handler(request, timeout))
