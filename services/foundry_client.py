"""Signed client for WealthMachine's proposal-only Foundry envelope endpoint.

This client carries operator-supplied commercial foundation to the exact
OpportunityPacket already assessed by WealthMachine. It receives underwriting
data only. It cannot launch, spend, publish, contact, approve, or mint grants.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
import time
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote
import urllib.request

from services.bridge_security import (
    BridgeSecurityError,
    NonceCache,
    build_headers,
    signing_key,
    verify_headers,
)
from services.ledger import DecisionLedger, get_ledger
from services.venture_protocol import SCHEMA_VERSION

FOUNDRY_UNDERWRITING_VERSION = "0.1"


class FoundryClientError(ValueError):
    pass


class FoundryCircuitOpenError(ConnectionError):
    pass


def _canonical_sha256(value: Any, field_name: str) -> str:
    text = str(value or "")
    if not text.startswith("sha256:") or len(text) != 71:
        raise FoundryClientError(f"{field_name} must be a canonical sha256 reference")
    return text


def validate_foundry_envelope(payload: Dict[str, Any], packet_id: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise FoundryClientError("Foundry envelope must be an object")
    if payload.get("schema_version") != FOUNDRY_UNDERWRITING_VERSION:
        raise FoundryClientError("unsupported Foundry envelope schema")
    if payload.get("source_organ") != "WealthMachineIntelligence":
        raise FoundryClientError("unexpected Foundry envelope source")
    if payload.get("opportunity_packet_id") != packet_id:
        raise FoundryClientError("Foundry envelope does not belong to the requested packet")
    if payload.get("requires_human_approval") is not True:
        raise FoundryClientError("Foundry envelope must require human approval")
    if payload.get("execution_authority") != "none":
        raise FoundryClientError("Foundry envelope must carry zero execution authority")
    _canonical_sha256(payload.get("packet_digest"), "packet_digest")
    _canonical_sha256(payload.get("assessment_digest"), "assessment_digest")

    missing = payload.get("missing_fields") or []
    blocking = payload.get("blocking_reasons") or []
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        raise FoundryClientError("missing_fields must be a list of strings")
    if not isinstance(blocking, list) or not all(isinstance(item, str) for item in blocking):
        raise FoundryClientError("blocking_reasons must be a list of strings")

    ready = payload.get("ready_for_foundry")
    if not isinstance(ready, bool):
        raise FoundryClientError("ready_for_foundry must be boolean")
    if ready:
        if missing or blocking or payload.get("go_no_go") != "go":
            raise FoundryClientError("ready envelope cannot retain missing or blocking state")
        for key in (
            "buyer", "beneficiary", "pain_owner", "budget_owner",
            "recurring_transaction", "accepted_artifact", "external_consequence",
            "lawful_path", "legal_operator",
        ):
            if not str(payload.get(key) or "").strip():
                raise FoundryClientError(f"ready envelope is missing {key}")
        evidence = payload.get("evidence_refs")
        if not isinstance(evidence, list) or not evidence:
            raise FoundryClientError("ready envelope requires evidence_refs")
    return payload


class FoundryEnvelopeClient:
    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 300

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger
        self._response_nonces = NonceCache()
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    @property
    def url(self) -> str:
        return os.getenv("WEALTHMACHINE_URL", "").rstrip("/")

    def request(self, packet_id: str, foundation: Mapping[str, Any]) -> Dict[str, Any]:
        if not packet_id:
            raise FoundryClientError("packet_id is required")
        if not self.url:
            raise FoundryClientError("WEALTHMACHINE_URL is required for Foundry underwriting")
        if time.time() < self._circuit_open_until:
            raise FoundryCircuitOpenError("Foundry bridge circuit is open")
        if not isinstance(foundation, Mapping):
            raise FoundryClientError("foundation must be an object")

        body = json.dumps(dict(foundation), sort_keys=True, default=str).encode()
        digest = sha256(body).hexdigest()
        headers = {"Content-Type": "application/json"}
        token = os.getenv("WEALTHMACHINE_INTAKE_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers.update(build_headers(
            body,
            identity="daleobanks",
            schema_version=SCHEMA_VERSION,
            idempotency_key=f"foundry:{packet_id}:{digest[:16]}",
            trace_id=packet_id,
        ))
        request = urllib.request.Request(
            f"{self.url}/api/ventures/{quote(packet_id, safe='')}/foundry-envelope",
            data=body,
            headers=headers,
            method="POST",
        )
        timeout = float(os.getenv("WEALTHMACHINE_TIMEOUT", "20"))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                response_headers = dict(response.headers.items())
            if signing_key():
                verify_headers(
                    response_headers,
                    raw,
                    nonce_cache=self._response_nonces,
                )
            payload = json.loads(raw)
            validate_foundry_envelope(payload, packet_id)
        except (BridgeSecurityError, ValueError, json.JSONDecodeError, OSError):
            self._record_failure()
            raise

        self._consecutive_failures = 0
        self.ledger.record("foundry_underwriting_envelope", {
            "packet_id": packet_id,
            "ready_for_foundry": payload["ready_for_foundry"],
            "missing_fields": payload.get("missing_fields") or [],
            "blocking_reasons": payload.get("blocking_reasons") or [],
            "packet_digest": payload["packet_digest"],
            "assessment_digest": payload["assessment_digest"],
            "execution_authority": "none",
        })
        return payload

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.FAILURE_THRESHOLD:
            self._circuit_open_until = time.time() + self.COOLDOWN_SECONDS
            self.ledger.record("foundry_bridge_circuit_opened", {
                "failures": self._consecutive_failures,
                "cooldown_seconds": self.COOLDOWN_SECONDS,
            })


__all__ = [
    "FOUNDRY_UNDERWRITING_VERSION",
    "FoundryCircuitOpenError",
    "FoundryClientError",
    "FoundryEnvelopeClient",
    "validate_foundry_envelope",
]
