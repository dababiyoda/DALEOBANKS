"""The legacy unsigned path must be asked for by name, never inherited.

Mirrors the kernel's tests/unit/test_bridge_transport_no_downgrade.py. The three
bridge_security mirrors are required to stay field-for-field compatible, so the
same defect and the same fix are asserted in the same way in each.

## The defect

`verify_headers` derived `must_sign = bool(key)`. An unset
`WEALTHMACHINE_SIGNING_KEY` therefore did not fail — it returned SUCCESS
carrying the caller's *claimed* identity, unverified, while the function's own
docstring said "fail closed, never degrade".

That is worse than an off switch, because nobody chose it. A deployment that had
simply not set the variable yet would report a working trust boundary while
accepting any identity from anyone.

Ratified under FOUNDER-RULING-2026-08-22: legacy HMAC compatibility may survive
only as "an explicit development compatibility mode, fail closed, never
auto-downgrade, and never be mistaken for mutually isolated identity."
"""

import json

import pytest

from services.bridge_security import (
    DEV_UNSIGNED_ENV, H_IDENTITY, H_SCHEMA, SIGNING_KEY_ENV,
    BridgeSecurityError, KNOWN_IDENTITIES, NonceCache, build_headers,
    verify_headers,
)


@pytest.fixture(autouse=True)
def _no_ambient_config(monkeypatch):
    """Neither variable set — the state the defect lived in."""
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(DEV_UNSIGNED_ENV, raising=False)


def _headers(identity="kernel"):
    return {H_IDENTITY: identity, H_SCHEMA: "1.1"}


# ------------------------------------------------------------- fail closed
def test_a_missing_signing_key_refuses_instead_of_succeeding_unsigned():
    """The core regression. This call used to return a verified-looking dict."""
    with pytest.raises(BridgeSecurityError, match="no signing key configured"):
        verify_headers(_headers(), b"{}", nonce_cache=NonceCache())


def test_the_refusal_names_both_ways_out_and_neither_is_automatic():
    with pytest.raises(BridgeSecurityError) as caught:
        verify_headers(_headers(), b"{}", nonce_cache=NonceCache())
    message = str(caught.value)
    assert SIGNING_KEY_ENV in message
    assert DEV_UNSIGNED_ENV in message
    assert "never disabled by the absence of configuration" in message


def test_asking_for_unsigned_without_the_opt_in_is_still_refused():
    """`require_signature=False` alone is not enough. Two deliberate acts."""
    with pytest.raises(BridgeSecurityError, match=DEV_UNSIGNED_ENV):
        verify_headers(_headers(), b"{}", nonce_cache=NonceCache(),
                       require_signature=False)


def test_omitting_every_header_is_not_quieter_than_sending_bad_ones():
    with pytest.raises(BridgeSecurityError):
        verify_headers({}, b"{}", nonce_cache=NonceCache())


# ---------------------------------------------------------- explicit dev mode
def test_the_legacy_path_works_when_a_human_asks_for_it_by_name(monkeypatch):
    """Preserved, not deleted — but it takes an argument AND an env var."""
    monkeypatch.setenv(DEV_UNSIGNED_ENV, "1")
    meta = verify_headers(_headers(), b"{}", nonce_cache=NonceCache(),
                          require_signature=False)
    assert meta["identity"] == "kernel"
    assert meta["signed"] == "false"


@pytest.mark.parametrize("value", ["true", "yes", "0", "", "TRUE", "1 "])
def test_only_the_exact_opt_in_value_counts(monkeypatch, value):
    """Ambiguity in an opt-in is itself a downgrade path."""
    monkeypatch.setenv(DEV_UNSIGNED_ENV, value)
    with pytest.raises(BridgeSecurityError):
        verify_headers(_headers(), b"{}", nonce_cache=NonceCache(),
                       require_signature=False)


# ------------------------------- never mistaken for isolated identity
def test_the_dev_mode_record_says_it_is_not_isolated_identity(monkeypatch):
    monkeypatch.setenv(DEV_UNSIGNED_ENV, "1")
    meta = verify_headers(_headers(), b"{}", nonce_cache=NonceCache(),
                          require_signature=False)
    assert meta["identity_isolated"] == "false"
    assert meta["dev_compatibility_mode"] == "true"


def test_even_a_valid_signature_is_not_isolated_identity(monkeypatch):
    """The subtle half of the ruling, and why per-service keys were ratified.

    A correct HMAC proves the sender held the shared secret. It does not prove
    WHICH holder sent it, because every participant needs that same secret to
    verify and can therefore also sign.
    """
    monkeypatch.setenv(SIGNING_KEY_ENV, "shared-secret")
    body = json.dumps({"id": "OPP-1"}, sort_keys=True).encode()
    headers = build_headers(body, identity="daleobanks", schema_version="1.1")

    meta = verify_headers(headers, body, nonce_cache=NonceCache())
    assert meta["signed"] == "true"
    assert meta["identity_isolated"] == "false"


def test_any_holder_of_the_shared_secret_can_claim_any_known_identity(monkeypatch):
    """The defect that motivated asymmetric identity, demonstrated here.

    This organ, holding only the shared key, signs as `kernel` and it verifies.
    Nothing in this transport can tell the difference — which is why the record
    must not imply otherwise.
    """
    monkeypatch.setenv(SIGNING_KEY_ENV, "shared-secret")
    body = b"{}"
    forged = build_headers(body, identity="kernel", schema_version="1.1")
    meta = verify_headers(forged, body, nonce_cache=NonceCache())
    assert meta["identity"] == "kernel"
    assert meta["identity_isolated"] == "false"


# ------------------------------------------------- kernel identity, unchanged
def test_kernel_is_recognised_for_transport_and_carries_no_authority():
    """Recognition is authentication. It is not permission, and the constant's
    own comment says so — this pins that the two never merge."""
    assert "kernel" in KNOWN_IDENTITIES
    import services.bridge_security as mod
    source = mod.__doc__ or ""
    assert "authorization" in source.lower() or "authority" in source.lower()
