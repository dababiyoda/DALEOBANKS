"""Zero-trust transport for the DALEOBANKS <-> WealthMachineIntelligence
bridge: service identity, HMAC request signing, timestamp + nonce replay
protection, idempotency keys, and schema-version negotiation.

Mirrored in WealthMachineIntelligence (src/services/bridge_security.py) —
keep the two files field-for-field compatible.

Local-first: with no ``WEALTHMACHINE_SIGNING_KEY`` configured, transport
runs unsigned (mock/dev mode). The moment a key exists, signing is
required in both directions and verification failures fail closed.

A valid signature proves sender authenticity ONLY. It never carries
authorization: a perfectly signed assessment still has no execution
authority and still routes through the human approval queue.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Dict, Optional, Tuple

SIGNING_KEY_ENV = "WEALTHMACHINE_SIGNING_KEY"
MAX_SKEW_SECONDS = 300
MIN_SCHEMA_VERSION = "1.0"

H_IDENTITY = "X-Service-Identity"
H_TIMESTAMP = "X-Timestamp"
H_NONCE = "X-Nonce"
H_IDEMPOTENCY = "X-Idempotency-Key"
H_SCHEMA = "X-Schema-Version"
H_SIGNATURE = "X-Signature"
H_TRACE = "X-Trace-Id"

KNOWN_IDENTITIES = frozenset({"daleobanks", "wealthmachine"})


class BridgeSecurityError(PermissionError):
    """Transport verification failed. The payload must not be processed."""


def signing_key() -> str:
    return os.getenv(SIGNING_KEY_ENV, "")


def _canonical(identity: str, timestamp: str, nonce: str, idempotency: str,
               schema_version: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    return f"{identity}|{timestamp}|{nonce}|{idempotency}|{schema_version}|{body_hash}".encode()


def sign(key: str, identity: str, timestamp: str, nonce: str, idempotency: str,
         schema_version: str, body: bytes) -> str:
    return hmac.new(
        key.encode(), _canonical(identity, timestamp, nonce, idempotency,
                                 schema_version, body),
        hashlib.sha256,
    ).hexdigest()


def build_headers(
    body: bytes,
    *,
    identity: str,
    schema_version: str,
    idempotency_key: Optional[str] = None,
    trace_id: str = "",
) -> Dict[str, str]:
    """Signed transport headers for an outbound request/response. With no
    key configured, identity headers still travel (debuggability) but no
    signature is attached."""
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    idempotency = idempotency_key or secrets.token_hex(16)
    headers = {
        H_IDENTITY: identity,
        H_TIMESTAMP: timestamp,
        H_NONCE: nonce,
        H_IDEMPOTENCY: idempotency,
        H_SCHEMA: schema_version,
    }
    if trace_id:
        headers[H_TRACE] = trace_id
    key = signing_key()
    if key:
        headers[H_SIGNATURE] = sign(key, identity, timestamp, nonce,
                                    idempotency, schema_version, body)
    return headers


class NonceCache:
    """In-memory replay guard. A nonce is accepted exactly once inside the
    skew window; reuse fails closed."""

    def __init__(self, ttl_seconds: int = MAX_SKEW_SECONDS * 2) -> None:
        self.ttl = ttl_seconds
        self._seen: Dict[str, float] = {}

    def check_and_store(self, nonce: str) -> bool:
        now = time.time()
        for old, ts in list(self._seen.items()):
            if now - ts > self.ttl:
                del self._seen[old]
        if nonce in self._seen:
            return False
        self._seen[nonce] = now
        return True


def _version_tuple(version: str) -> Tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)


def verify_headers(
    headers: Dict[str, str],
    body: bytes,
    *,
    nonce_cache: NonceCache,
    require_signature: Optional[bool] = None,
) -> Dict[str, str]:
    """Verify inbound transport headers. Raises BridgeSecurityError on any
    failure — fail closed, never degrade. Returns the normalized header
    set for provenance recording."""
    getter = {k.lower(): v for k, v in headers.items()}

    def get(name: str) -> str:
        return getter.get(name.lower(), "")

    key = signing_key()
    must_sign = require_signature if require_signature is not None else bool(key)

    identity = get(H_IDENTITY)
    schema_version = get(H_SCHEMA) or MIN_SCHEMA_VERSION
    if _version_tuple(schema_version) < _version_tuple(MIN_SCHEMA_VERSION):
        raise BridgeSecurityError(
            f"schema version {schema_version} below minimum {MIN_SCHEMA_VERSION} — "
            "downgrade rejected"
        )

    if not must_sign:
        return {"identity": identity or "unsigned-local", "schema_version": schema_version,
                "signed": "false", "trace_id": get(H_TRACE)}

    if identity not in KNOWN_IDENTITIES:
        raise BridgeSecurityError(f"unknown service identity '{identity}'")

    timestamp = get(H_TIMESTAMP)
    try:
        skew = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        raise BridgeSecurityError("missing or malformed timestamp")
    if skew > MAX_SKEW_SECONDS:
        raise BridgeSecurityError("timestamp outside the accepted window")

    nonce = get(H_NONCE)
    if not nonce or not nonce_cache.check_and_store(nonce):
        raise BridgeSecurityError("nonce missing or already used — replay rejected")

    idempotency = get(H_IDEMPOTENCY)
    signature = get(H_SIGNATURE)
    expected = sign(key, identity, timestamp, nonce, idempotency,
                    schema_version, body)
    if not signature or not hmac.compare_digest(signature, expected):
        raise BridgeSecurityError("signature verification failed")

    return {"identity": identity, "schema_version": schema_version,
            "signed": "true", "idempotency_key": idempotency,
            "trace_id": get(H_TRACE)}


__all__ = [
    "BridgeSecurityError", "NonceCache", "build_headers", "verify_headers",
    "sign", "signing_key", "SIGNING_KEY_ENV", "MAX_SKEW_SECONDS",
    "MIN_SCHEMA_VERSION", "KNOWN_IDENTITIES",
    "H_IDENTITY", "H_TIMESTAMP", "H_NONCE", "H_IDEMPOTENCY",
    "H_SCHEMA", "H_SIGNATURE", "H_TRACE",
]
