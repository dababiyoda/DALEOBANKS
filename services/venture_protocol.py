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

SCHEMA_VERSION = "1.1"

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

# --------------------------------------------------------------------- #
# Assessment provenance
# --------------------------------------------------------------------- #
# A simulated verdict and a WealthMachineIntelligence verdict have the same
# shape by design — that is what lets the loop run offline. It also means
# shape cannot tell them apart, so provenance travels on the object.
#
# One question, one answer: "did WMI actually produce this?" is decided here
# and nowhere else. When that rule lives at each call site instead, the copies
# drift, and the loosest copy silently becomes the system's real policy.

EXECUTION_CLASS_SIMULATION = "SIMULATION"
EXECUTION_CLASS_WMI_HTTP_AUTHENTICATED = "EXTERNAL_WMI_HTTP_AUTHENTICATED"
EXECUTION_CLASS_HTTP_UNVERIFIED = "EXTERNAL_HTTP_UNVERIFIED"
EXECUTION_CLASS_INBOUND_CONTRACT = "INBOUND_CONTRACT"
EXECUTION_CLASS_UNCLASSIFIED = "UNCLASSIFIED"

EVIDENCE_CLASS_MOCK = "MOCK"
EVIDENCE_CLASS_EXTERNAL_ASSESSMENT = "EXTERNAL_ASSESSMENT"
EVIDENCE_CLASS_EXTERNAL_UNVERIFIED = "EXTERNAL_UNVERIFIED"
EVIDENCE_CLASS_UNVERIFIED = "UNVERIFIED"

# Stamped verbatim onto simulated assessments, for as long as they exist.
SIMULATION_LABELS = ("SIMULATION", "MOCK", "NON_EXTERNAL", "NON_WMI_EXECUTION")
MOCK_ASSESSMENT_LABEL = " | ".join(SIMULATION_LABELS)
UNVERIFIED_ASSESSMENT_LABEL = (
    "EXTERNAL | UNVERIFIED_RUNTIME_IDENTITY | NON_AUTHORITATIVE"
)


class SimulatedEvidenceError(ValueError):
    """Non-authoritative evidence was offered where a real WMI verdict is required."""


def is_authoritative_wmi_assessment(assessment: Any) -> bool:
    """The single rule. Both conditions are required.

    Reads through ``getattr`` defaults so an object that predates provenance,
    or comes from somewhere else entirely, fails closed instead of passing by
    omission.
    """
    external = getattr(assessment, "external_execution", False) is True
    evidence = getattr(assessment, "evidence_class", EVIDENCE_CLASS_UNVERIFIED)
    return external and evidence == EVIDENCE_CLASS_EXTERNAL_ASSESSMENT


def is_simulated_assessment(assessment: Any) -> bool:
    """True when this repo produced the verdict rather than receiving it."""
    return getattr(
        assessment, "execution_class", EXECUTION_CLASS_UNCLASSIFIED
    ) == EXECUTION_CLASS_SIMULATION


def require_authoritative_wmi(assessment: Any, *, action: str) -> None:
    """Gate an action that may only rest on a real WMI verdict.

    Raises rather than returning a boolean: a caller who forgets to check a
    return value would promote a simulation to evidence, which is the exact
    failure this exists to prevent.
    """
    if not is_authoritative_wmi_assessment(assessment):
        raise SimulatedEvidenceError(
            f"{action} requires an authoritative WealthMachineIntelligence "
            f"assessment; this one is execution_class="
            f"{getattr(assessment, 'execution_class', EXECUTION_CLASS_UNCLASSIFIED)!r} "
            f"evidence_class="
            f"{getattr(assessment, 'evidence_class', EVIDENCE_CLASS_UNVERIFIED)!r} "
            f"external_execution="
            f"{getattr(assessment, 'external_execution', False)!r}"
        )


def assessment_provenance(assessment: Any) -> Dict[str, Any]:
    """Provenance summary for episodes, dashboards, and operator surfaces."""
    return {
        "execution_class": getattr(
            assessment, "execution_class", EXECUTION_CLASS_UNCLASSIFIED),
        "evidence_class": getattr(
            assessment, "evidence_class", EVIDENCE_CLASS_UNVERIFIED),
        "external_execution": getattr(assessment, "external_execution", False),
        "authoritative_wmi": is_authoritative_wmi_assessment(assessment),
        "simulated": is_simulated_assessment(assessment),
    }


def packet_status_for_assessment(assessment: Any) -> str:
    """The packet status an assessment earns. Derived from the one rule."""
    if is_simulated_assessment(assessment):
        return "simulated"
    if is_authoritative_wmi_assessment(assessment):
        return "assessed"
    return "assessment_received_unverified"


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
    "EXECUTION_CLASS_SIMULATION", "EXECUTION_CLASS_WMI_HTTP_AUTHENTICATED",
    "EXECUTION_CLASS_HTTP_UNVERIFIED", "EXECUTION_CLASS_INBOUND_CONTRACT",
    "EXECUTION_CLASS_UNCLASSIFIED", "EVIDENCE_CLASS_MOCK",
    "EVIDENCE_CLASS_EXTERNAL_ASSESSMENT", "EVIDENCE_CLASS_EXTERNAL_UNVERIFIED",
    "EVIDENCE_CLASS_UNVERIFIED", "SIMULATION_LABELS", "MOCK_ASSESSMENT_LABEL",
    "UNVERIFIED_ASSESSMENT_LABEL", "SimulatedEvidenceError",
    "is_authoritative_wmi_assessment", "is_simulated_assessment",
    "require_authoritative_wmi", "assessment_provenance",
    "packet_status_for_assessment",
]
