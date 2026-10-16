"""DALEOBANKS -> UNIIMENTE Foundry evidence envelope.

This adapter converts a media/signal-side OpportunityPacket into a versioned,
non-executing envelope. It never fills missing commercial facts with model
inference. Missing buyer, budget, permission, artifact, and consequence fields
remain explicit blockers for Foundry intake.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

FOUNDRY_ENVELOPE_VERSION = "0.1"
REQUIRED_FOUNDATION_FIELDS = (
    "buyer",
    "beneficiary",
    "pain_owner",
    "budget_owner",
    "recurring_transaction",
    "accepted_artifact",
    "external_consequence",
    "lawful_path",
)


@dataclass(frozen=True)
class FoundryOpportunityEnvelope:
    schema_version: str
    source_organ: str
    source_packet_id: str
    source_packet_digest: str
    observed_pain: str
    core_thesis: str
    buyer_hypothesis: str
    beneficiary_hypothesis: str
    evidence_refs: tuple[str, ...]
    risk_flags: tuple[str, ...]
    smallest_validation_action: str
    buyer: str = ""
    beneficiary: str = ""
    pain_owner: str = ""
    budget_owner: str = ""
    recurring_transaction: str = ""
    trapped_value_usd: float | None = None
    accepted_artifact: str = ""
    external_consequence: str = ""
    lawful_path: str = ""
    legal_operator: str = "alfonso_lopez"
    requires_human_approval: bool = True
    execution_authority: str = "none"
    missing_fields: tuple[str, ...] = field(default_factory=tuple)
    ready_for_foundry: bool = False

    def to_wire(self) -> dict[str, Any]:
        return asdict(self)


class FoundryEnvelopeError(ValueError):
    pass


def _packet_dict(packet: Any) -> dict[str, Any]:
    if is_dataclass(packet):
        return asdict(packet)
    if isinstance(packet, Mapping):
        return dict(packet)
    try:
        return dict(vars(packet))
    except TypeError as exc:
        raise FoundryEnvelopeError("packet must be a dataclass, mapping, or object") from exc


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def build_foundry_envelope(
    packet: Any,
    *,
    foundation: Mapping[str, Any] | None = None,
) -> FoundryOpportunityEnvelope:
    """Build a proposal-only Foundry envelope without fabricating readiness.

    `foundation` must come from accountable human or externally verified
    evidence. Packet-level segment and buyer-type fields are preserved only as
    hypotheses and never silently promoted into named commercial facts.
    """
    raw = _packet_dict(packet)
    packet_id = str(raw.get("id") or "").strip()
    if not packet_id:
        raise FoundryEnvelopeError("OpportunityPacket id is required")

    evidence = tuple(str(item) for item in (raw.get("evidence") or ()) if str(item).strip())
    supplied = dict(foundation or {})
    values = {name: str(supplied.get(name) or "").strip() for name in REQUIRED_FOUNDATION_FIELDS}
    missing = tuple(name for name in REQUIRED_FOUNDATION_FIELDS if not values[name])

    trapped_value = supplied.get("trapped_value_usd")
    if trapped_value is not None:
        trapped_value = float(trapped_value)
        if trapped_value < 0:
            raise FoundryEnvelopeError("trapped_value_usd cannot be negative")
    if not evidence:
        missing = tuple(dict.fromkeys((*missing, "evidence_refs")))
    if trapped_value is None:
        missing = tuple(dict.fromkeys((*missing, "trapped_value_usd")))

    legal_operator = str(supplied.get("legal_operator") or "alfonso_lopez").strip()
    if legal_operator == "UNIIMENTE":
        raise FoundryEnvelopeError("UNIIMENTE is never the legal operator")

    return FoundryOpportunityEnvelope(
        schema_version=FOUNDRY_ENVELOPE_VERSION,
        source_organ="DALEOBANKS",
        source_packet_id=packet_id,
        source_packet_digest=_canonical_digest(raw),
        observed_pain=str(raw.get("observed_pain") or ""),
        core_thesis=str(raw.get("core_thesis") or ""),
        buyer_hypothesis=str(raw.get("buyer_type") or ""),
        beneficiary_hypothesis=str(raw.get("customer_segment") or raw.get("audience") or ""),
        evidence_refs=evidence,
        risk_flags=tuple(str(item) for item in (raw.get("risk_flags") or ())),
        smallest_validation_action=str(raw.get("smallest_validation_action") or ""),
        buyer=values["buyer"],
        beneficiary=values["beneficiary"],
        pain_owner=values["pain_owner"],
        budget_owner=values["budget_owner"],
        recurring_transaction=values["recurring_transaction"],
        trapped_value_usd=trapped_value,
        accepted_artifact=values["accepted_artifact"],
        external_consequence=values["external_consequence"],
        lawful_path=values["lawful_path"],
        legal_operator=legal_operator,
        missing_fields=missing,
        ready_for_foundry=not missing,
    )


__all__ = [
    "FOUNDRY_ENVELOPE_VERSION",
    "REQUIRED_FOUNDATION_FIELDS",
    "FoundryEnvelopeError",
    "FoundryOpportunityEnvelope",
    "build_foundry_envelope",
]
