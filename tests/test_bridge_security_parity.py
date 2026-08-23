"""Transport parity with the kernel mirror, pinned.

`services/bridge_security.py` is one of three mirrors of the same module — the
others are `adapters/bridge_transport.py` in uniimente-kernel and
`src/services/bridge_security.py` in WealthMachineIntelligence. They are meant
to stay field-for-field compatible, which means a security fix landing in one is
a divergence until it lands in the others.

The kernel took two changes on 2026-08-22 under FOUNDER-RULING-2026-08-22. This
mirror took them on 2026-08-23. These tests are why they cannot silently come
back apart.
"""
from __future__ import annotations

import os

import pytest

from services import bridge_security as bs


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(bs.SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(bs.DEV_UNSIGNED_ENV, raising=False)


def test_an_unset_signing_key_fails_closed_instead_of_returning_success():
    """The auto-downgrade, removed.

    `must_sign` was `bool(key)`, so an unset signing key did not fail — it
    returned SUCCESS carrying the caller's *claimed* identity, unverified. A
    forgotten environment variable in a new deployment read as a working trust
    boundary.
    """
    with pytest.raises(bs.BridgeSecurityError, match="no signing key configured"):
        bs.verify_headers({"X-Service-Identity": "daleobanks"}, b"{}",
                          nonce_cache=bs.NonceCache())


def test_the_unsigned_path_must_be_asked_for_by_name(monkeypatch):
    """Legacy compatibility survives only as an explicit development mode."""
    with pytest.raises(bs.BridgeSecurityError, match="must be asked for"):
        bs.verify_headers({"X-Service-Identity": "daleobanks"}, b"{}",
                          nonce_cache=bs.NonceCache(), require_signature=False)

    monkeypatch.setenv(bs.DEV_UNSIGNED_ENV, "1")
    result = bs.verify_headers({"X-Service-Identity": "daleobanks"}, b"{}",
                               nonce_cache=bs.NonceCache(),
                               require_signature=False)
    assert result["dev_compatibility_mode"] == "true"


def test_no_path_ever_reports_isolated_identity(monkeypatch):
    """The field the founder's ruling required, on every path.

    One shared secret both signs and verifies, so every participant able to
    check a signature is able to forge one: a recognized identity here is a
    CLAIMED identity. Isolated identity is the kernel's `identity/pki/`, where a
    private key proves a SPIFFE ID no other workload can assert.

    A valid signature must never read as isolation, so the record says so in its
    own field rather than leaving a reader to infer it from `signed`.
    """
    monkeypatch.setenv(bs.DEV_UNSIGNED_ENV, "1")
    unsigned = bs.verify_headers({"X-Service-Identity": "daleobanks"}, b"{}",
                                 nonce_cache=bs.NonceCache(),
                                 require_signature=False)
    assert unsigned["identity_isolated"] == "false"

    monkeypatch.setenv(bs.SIGNING_KEY_ENV, "k" * 32)
    body = b'{"a":1}'
    headers = bs.build_headers(body, identity="daleobanks",
                               schema_version="1.1")
    signed = bs.verify_headers(headers, body, nonce_cache=bs.NonceCache())

    assert signed["signed"] == "true"
    assert signed["identity_isolated"] == "false", (
        "the shared-secret path claimed isolated identity; only an asymmetric "
        "per-workload key can earn that")


def test_a_valid_signature_still_proves_authenticity(monkeypatch):
    """The parity changes hardened the module without breaking it."""
    monkeypatch.setenv(bs.SIGNING_KEY_ENV, "k" * 32)
    body = b'{"a":1}'
    headers = bs.build_headers(body, identity="daleobanks",
                               schema_version="1.1")

    assert bs.verify_headers(headers, body,
                             nonce_cache=bs.NonceCache())["identity"] == "daleobanks"

    tampered = dict(headers)
    tampered["X-Signature"] = "0" * 64
    with pytest.raises(bs.BridgeSecurityError):
        bs.verify_headers(tampered, body, nonce_cache=bs.NonceCache())
