"""The stable protocol between DALEOBANKS and WealthMachineIntelligence.

DALEOBANKS finds signals and builds public trust; WealthMachineIntelligence
evaluates whether signals are business opportunities. The two systems stay
separate and talk only through the wire contracts defined here:
``OpportunityPacket`` out, ``VentureAssessment`` back, ``ValidationResult``
recorded after the world responds. This module is designed to be copied
verbatim into the WealthMachineIntelligence repo (or replaced by a shared
package later) — keep it dependency-light and version every change.

The core rule: the machine prepares, the human authorizes, the world
responds, the system learns. Nothing in this protocol executes anything.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

SCHEMA_VERSION = "1.0"

ALLOWED_SIGNAL_TYPES = frozenset({
    "social_complaint",
    "news_trend",
    "regulatory_shift",
    "audience_reaction",
    "repeated_question",
    "relationship_signal",
    "content_opportunity",
    "product_opportunity",
    "partnership_opportunity",
    "operator_thought",
})

ALLOWED_GO_NO_GO = frozenset({"go", "defer", "kill", "needs_more_evidence"})

# ValidationResult contract: outcomes the world can hand back. Negative
# (no response) is a legitimate, recorded outcome — never an absence.
ALLOWED_RESULT_CLASSIFICATIONS = frozenset({
    "success", "failure", "mixed", "inconclusive", "negative",
})

# Evidence tiers, strongest first. Payment outranks commitment outranks
# conversation outranks engagement outranks passive observation.
ALLOWED_EVIDENCE_TIERS = frozenset({
    "payment", "commitment", "conversation", "engagement", "observation",
})

ALLOWED_IDENTITY_TYPES = frozenset({
    "main_identity",
    "brand_account",
    "project_account",
    "pseudonymous_brand",
    "faceless_media_page",
    "company_page",
})

FORBIDDEN_IDENTITY_TYPES = frozenset({
    "fake_person",
    "impersonation",
    "fake_expert_identity",
    "ban_evasion_account",
    "engagement_manipulation_account",
})

# Hardcoded, non-configurable media-company policy. These are not settings.
LANE_POLICY = (
    "No account may be used to simulate independent public support for another account.",
    "No fake consensus.",
    "No coordinated inauthentic amplification.",
    "No auto-DMs at scale.",
    "No impersonation.",
    "No undisclosed sponsorships.",
    "No stolen media.",
    "No guaranteed financial claims.",
    "No personalized legal or financial advice unless reviewed by a qualified professional.",
    "Every account lane must have a distinct purpose, audience, and content policy.",
)


def packet_to_wire(packet: Any) -> Dict[str, Any]:
    """Serialize an OpportunityPacket for transport (JSON-safe)."""
    payload = asdict(packet)
    payload["schema_version"] = SCHEMA_VERSION
    payload["created_at"] = packet.created_at.isoformat()
    return payload


def assessment_to_wire(assessment: Any) -> Dict[str, Any]:
    payload = asdict(assessment)
    payload["schema_version"] = SCHEMA_VERSION
    payload["created_at"] = assessment.created_at.isoformat()
    return payload


def validate_assessment_wire(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an inbound VentureAssessment payload. Raises ValueError on a
    contract violation — inbound wire data is untrusted input."""
    if not isinstance(payload, dict):
        raise ValueError("assessment payload must be an object")
    go_no_go = payload.get("go_no_go")
    if go_no_go not in ALLOWED_GO_NO_GO:
        raise ValueError(f"go_no_go must be one of {sorted(ALLOWED_GO_NO_GO)}")
    if not payload.get("opportunity_packet_id"):
        raise ValueError("opportunity_packet_id is required")
    score = payload.get("opportunity_score")
    if score is not None and not (0.0 <= float(score) <= 1.0):
        raise ValueError("opportunity_score must be within [0, 1]")
    return payload


def validate_identity_type(identity_type: str) -> str:
    """The load-bearing gate for account lanes: authentic lanes only."""
    if identity_type in FORBIDDEN_IDENTITY_TYPES:
        raise ValueError(
            f"identity_type '{identity_type}' is forbidden: account lanes are "
            "brands and projects, never fake people, impersonation, or "
            "engagement manipulation"
        )
    if identity_type not in ALLOWED_IDENTITY_TYPES:
        raise ValueError(
            f"identity_type '{identity_type}' is not recognized; allowed: "
            f"{sorted(ALLOWED_IDENTITY_TYPES)}"
        )
    return identity_type


__all__ = [
    "SCHEMA_VERSION", "ALLOWED_SIGNAL_TYPES", "ALLOWED_GO_NO_GO",
    "ALLOWED_RESULT_CLASSIFICATIONS", "ALLOWED_EVIDENCE_TIERS",
    "ALLOWED_IDENTITY_TYPES", "FORBIDDEN_IDENTITY_TYPES", "LANE_POLICY",
    "packet_to_wire", "assessment_to_wire", "validate_assessment_wire",
    "validate_identity_type",
]
