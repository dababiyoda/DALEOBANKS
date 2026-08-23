"""The kernel is a recognised sender. It is not a privileged one.

This is the DALEOBANKS half of the one-line change the UNIIMENTE Phase Zero
report has listed as an open blocker since 2026-07-20: kernel-signed messages
could not verify here because `kernel` was absent from `KNOWN_IDENTITIES`.

Recognition is the whole of the change. Every test below exists to pin the
boundary of what was granted:

- a correctly signed kernel message verifies, and
- a kernel message that is forged, replayed or stale still fails closed, and
- verification returns transport facts only — no authority, no role, nothing
  that distinguishes `kernel` from any other known sender.

The shared-secret limit is asserted too, so nobody later reads "recognised"
as "authenticated in isolation". All mirrors share one signing key, so any
holder of that key can assert any known identity.
"""

import time

import pytest

from services.bridge_security import (
    H_IDEMPOTENCY,
    H_IDENTITY,
    H_NONCE,
    H_SCHEMA,
    H_SIGNATURE,
    H_TIMESTAMP,
    KNOWN_IDENTITIES,
    MIN_SCHEMA_VERSION,
    SIGNING_KEY_ENV,
    BridgeSecurityError,
    NonceCache,
    build_headers,
    sign,
)

KEY = "test-signing-key"
BODY = b'{"packet":"x"}'
SCHEMA = MIN_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def _signing_key(monkeypatch):
    """Signing is only required once a key exists. Every test here needs one."""
    monkeypatch.setenv(SIGNING_KEY_ENV, KEY)


def _headers(identity="kernel", **over):
    h = build_headers(BODY, identity=identity, schema_version=SCHEMA,
                      idempotency_key="idem-1")
    h.update(over)
    return h


def test_kernel_is_a_known_transport_identity():
    assert "kernel" in KNOWN_IDENTITIES
    assert {"daleobanks", "wealthmachine", "kernel"} == set(KNOWN_IDENTITIES)


def test_a_correctly_signed_kernel_message_verifies():
    from services.bridge_security import verify_headers

    result = verify_headers(_headers(), BODY, nonce_cache=NonceCache(),
                            require_signature=True)
    assert result["identity"] == "kernel"
    assert result["signed"] == "true"


def test_verification_returns_transport_facts_and_no_authority():
    """Recognition must not smuggle in a role, a permission or a capability.

    The allowlist moved on 2026-08-23 to admit `identity_isolated`, and the
    move is deliberate rather than accommodating. That field is a transport
    fact and an ANTI-authority one: it reports that a valid signature proves
    possession of the shared secret and not which holder sent it, because
    every participant needs that secret to verify and can therefore also sign.

    Adding it makes this result strictly less able to be mistaken for
    authorization, which is the property this test defends. The allowlist is
    kept closed so the next addition is also a decision.
    """
    from services.bridge_security import verify_headers

    result = verify_headers(_headers(), BODY, nonce_cache=NonceCache(),
                            require_signature=True)
    assert set(result) <= {"identity", "schema_version", "signed",
                           "identity_isolated", "dev_compatibility_mode",
                           "idempotency_key", "trace_id"}
    for forbidden in ("authority", "role", "permissions", "capabilities",
                      "approved", "grant"):
        assert forbidden not in result

    # The new field must say the transport is NOT isolated identity. A "true"
    # here would be the exact overclaim the field was added to prevent.
    assert result["identity_isolated"] == "false"


def test_kernel_gets_no_more_than_any_other_sender():
    """The result shape for `kernel` is identical to the shape for a peer organ."""
    from services.bridge_security import verify_headers

    k = verify_headers(_headers("kernel"), BODY, nonce_cache=NonceCache(),
                       require_signature=True)
    w = verify_headers(_headers("wealthmachine"), BODY, nonce_cache=NonceCache(),
                       require_signature=True)
    assert set(k) == set(w)
    assert {kk: vv for kk, vv in k.items() if kk != "identity"} == \
           {kk: vv for kk, vv in w.items() if kk != "identity"}


# ------------------------------------------------------------- fails closed
def test_forged_kernel_signature_fails_closed():
    from services.bridge_security import verify_headers

    bad = _headers(**{H_SIGNATURE: "0" * 64})
    with pytest.raises(BridgeSecurityError, match="signature"):
        verify_headers(bad, BODY, nonce_cache=NonceCache(), require_signature=True)


def test_kernel_identity_with_a_tampered_body_fails_closed():
    from services.bridge_security import verify_headers

    with pytest.raises(BridgeSecurityError, match="signature"):
        verify_headers(_headers(), b'{"packet":"tampered"}', nonce_cache=NonceCache(),
                       require_signature=True)


def test_replayed_kernel_nonce_fails_closed():
    from services.bridge_security import verify_headers

    cache = NonceCache()
    headers = _headers()
    assert verify_headers(headers, BODY, nonce_cache=cache, require_signature=True)
    with pytest.raises(BridgeSecurityError, match="replay"):
        verify_headers(headers, BODY, nonce_cache=cache, require_signature=True)


def test_stale_kernel_timestamp_fails_closed():
    from services.bridge_security import MAX_SKEW_SECONDS, verify_headers

    stale = str(int(time.time()) - MAX_SKEW_SECONDS - 60)
    nonce = "replay-me-not"
    headers = {
        H_IDENTITY: "kernel", H_TIMESTAMP: stale, H_NONCE: nonce,
        H_IDEMPOTENCY: "idem-1", H_SCHEMA: SCHEMA,
    }
    headers[H_SIGNATURE] = sign(KEY, "kernel", stale, nonce, "idem-1", SCHEMA, BODY)
    with pytest.raises(BridgeSecurityError, match="timestamp"):
        verify_headers(headers, BODY, nonce_cache=NonceCache(), require_signature=True)


def test_an_unknown_identity_is_still_refused():
    from services.bridge_security import verify_headers

    with pytest.raises(BridgeSecurityError, match="unknown service identity"):
        verify_headers(_headers(**{H_IDENTITY: "railscout"}), BODY, nonce_cache=NonceCache(),
                       require_signature=True)


def test_schema_downgrade_is_still_rejected_for_the_kernel():
    from services.bridge_security import verify_headers

    with pytest.raises(BridgeSecurityError, match="downgrade"):
        verify_headers(_headers(**{H_SCHEMA: "0.9"}), BODY, nonce_cache=NonceCache(),
                       require_signature=True)


# ------------------------------------------------- the limit of this change
def test_the_shared_secret_means_identity_is_claimed_not_isolated():
    """Any holder of the one shared key can assert any known identity.

    Recorded as an executable fact so "recognised" is never read as
    "cryptographically isolated". Per-service keys or mTLS is the hardening
    step, and it is not done.
    """
    from services.bridge_security import verify_headers

    # A caller who holds the key but is not the kernel signs as the kernel,
    # and the transport cannot tell the difference. That is the limit.
    impersonation = build_headers(BODY, identity="kernel",
                                  schema_version=SCHEMA, idempotency_key="idem-2")
    result = verify_headers(impersonation, BODY, nonce_cache=NonceCache(),
                            require_signature=True)
    assert result["identity"] == "kernel"

    doc = __import__("services.bridge_security", fromlist=["x"]).__doc__
    assert "CLAIMED identity" in doc
    assert "Per-service keys or mTLS" in doc
