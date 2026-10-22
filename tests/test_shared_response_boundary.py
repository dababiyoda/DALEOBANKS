"""Real client admission under altered response bytes/context and missing config."""
import pytest
from services.bridge_security import (BridgeSecurityError, H_RECIPIENT, H_REQUEST,
    H_IDEMPOTENCY, H_PROTOCOL, H_SIGNATURE)
from tests.bridge_fixtures import bridge_configuration, Response, intercept, assessment_wire
from tests.test_signed_bridge_client import _client, _packet


@pytest.mark.parametrize('mutation', ['bytes','recipient','request','logical_key',
                                     'protocol','signature','nested','schema'])
def test_response_mutations_are_not_accepted(tmp_path, monkeypatch, mutation):
    packet = _packet()
    response = Response(packet)
    if mutation == 'bytes': response._raw += b' '
    elif mutation == 'recipient': response.headers[H_RECIPIENT] = 'kernel'
    elif mutation == 'request': response.headers[H_REQUEST] = '0' * 64
    elif mutation == 'logical_key': response.headers[H_IDEMPOTENCY] = 'another-operation'
    elif mutation == 'protocol': response.headers[H_PROTOCOL] = '1'
    elif mutation == 'signature': response.headers.pop(H_SIGNATURE)
    elif mutation == 'nested':
        response = Response(packet, assessment_wire(packet, cases=[{'case':'bear','stance':'against',
            'severity':'high','argument':{'invented':'object'}}]))
    else:
        response = Response(packet, assessment_wire(packet, schema_version='99'))
    intercept(monkeypatch, lambda *args: response)
    client = _client(tmp_path)
    try:
        with pytest.raises((BridgeSecurityError, ValueError)): client.evaluate(packet)
    finally:
        client.close()


def test_response_replay_survives_consumer_reconstruction(tmp_path, monkeypatch):
    packet = _packet()
    response = Response(packet)
    intercept(monkeypatch, lambda *args: response)
    client = _client(tmp_path)
    result = client.evaluate(packet)
    assert result.id == 'assessment-' + packet.id
    assert result.created_at.isoformat() == '2026-09-08T00:00:00+00:00'
    client.close()
    client = _client(tmp_path)
    try:
        with pytest.raises(BridgeSecurityError, match='replay'): client.evaluate(packet)
    finally:
        client.close()


@pytest.mark.parametrize('missing', ['WEALTHMACHINE_SIGNING_KEY', 'WEALTHMACHINE_INTAKE_TOKEN',
    'UNIIMENTE_BRIDGE_STATE_PATH', 'UNIIMENTE_CONSTITUTION_HASH', 'UNIIMENTE_LEGAL_PRINCIPAL'])
def test_missing_config_prevents_dispatch(tmp_path, monkeypatch, missing):
    monkeypatch.delenv(missing)
    intercept(monkeypatch, lambda *args: pytest.fail('dispatch before admission'))
    client = _client(tmp_path)
    try:
        with pytest.raises((BridgeSecurityError, ValueError)): client.evaluate(_packet())
    finally:
        client.close()


def test_redirects_cannot_carry_credentials():
    from services.wealthmachine_client import _NoRedirect
    with pytest.raises(BridgeSecurityError, match='redirect'):
        _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://external.invalid')
