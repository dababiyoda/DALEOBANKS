"""Issue #57 — kernel contract consumption for DALEOBANKS.

The kernel's ``/contracts`` are canonical wire law (v1.1, vendored and
SHA-256 pinned under ``contracts/kernel/``). This module is the SINGLE
mapping point between that law and the DALEOBANKS transport dialect
(``services/venture_protocol.py``).

DALEOBANKS sends packets and receives assessments, so the two load-bearing
translations are:

  - ``wire_packet_to_kernel`` — outbound: enrich a dialect packet into
    kernel format for kernel-side recording. Fails closed without the
    mandatory enrichment fields (pain_owner, budget_owner,
    governing_bottleneck, cheapest_decisive_test).
  - ``wire_assessment_to_kernel`` — inbound: translate a WealthMachine
    dialect assessment into kernel format. Constitutional constants are
    synthesized, never taken from the wire: requires_human_approval is
    always True, execution_authority always False — an assessment that
    claims otherwise is refused, not sanitized.

``LANE_POLICY`` and ``validate_identity_type`` stay local: they are
DALEOBANKS media-company safety gates, not wire contracts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

KERNEL_SCHEMA_VERSION = "1.1"

# sha256 of the vendored kernel schemas (pinned; drift fails parity tests)
PINNED_SCHEMA_HASHES = {
    "opportunity-packet": "aaa3970164b14bb7dcca6c9dde10017f5c376c4db40f0292ad4356e0442e4c64",
    "venture-assessment": "c0ad6578fb8ded2319bb03f37c6d99c38514068c5565dbfde0ae2577219f46a7",
}

GO_NO_GO_TO_VERDICT = {"go": "go", "defer": "defer", "kill": "kill",
                       "needs_more_evidence": "needs_more_evidence"}

KERNEL_MANDATORY_ENRICHMENT = ("pain_owner", "budget_owner", "governing_bottleneck",
                               "cheapest_decisive_test")


class ContractRefusal(ValueError):
    """Translation would lose mandatory kernel law. Fails closed."""


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def wire_packet_to_kernel(wire: dict, *, enrichment: dict) -> dict:
    """DALEOBANKS dialect OpportunityPacket -> kernel format (enriching)."""
    missing = [k for k in KERNEL_MANDATORY_ENRICHMENT if not enrichment.get(k)]
    if missing:
        raise ContractRefusal(
            f"dialect packet cannot become kernel law without enrichment: {missing}")
    packet_id = wire.get("id")
    if not packet_id:
        raise ContractRefusal("dialect packet missing id")
    return {
        "packet_id": str(packet_id) if _is_uuid(packet_id) else str(uuid.uuid4()),
        "schema_version": KERNEL_SCHEMA_VERSION,
        "created_by": "spiffe://uniimente.internal/organ/daleobanks",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "observed_failure": wire.get("observed_pain") or wire.get("core_thesis", ""),
        "affected_actors": [wire["audience"]] if wire.get("audience") else [],
        "pain_owner": enrichment["pain_owner"],
        "budget_owner": enrichment["budget_owner"],
        "payer": wire.get("customer_segment", ""),
        "mandate_capable_actor": wire.get("buyer_type", ""),
        "existing_workaround": None,
        "missing_proof": "",
        "governing_bottleneck": enrichment["governing_bottleneck"],
        "smallest_intervention": wire.get("smallest_validation_action", ""),
        "cheapest_decisive_test": enrichment["cheapest_decisive_test"],
        "possible_business_form": wire.get("possible_offer") or None,
        "capital_requirement_usd": 0.0,
        "key_risks": list(wire.get("risk_flags", [])),
        "wedge_to_control_path": wire.get("core_thesis", ""),
        "evidence_refs": [e for e in wire.get("evidence", [])
                          if isinstance(e, str) and e.startswith("sha256:")],
    }


def wire_assessment_to_kernel(wire: dict) -> dict:
    """WealthMachine dialect VentureAssessment -> kernel format.

    Constitutional constants are synthesized locally, never read from the
    wire: an inbound assessment claiming execution authority or waiving
    human approval is refused, not sanitized.
    """
    if not isinstance(wire, dict):
        raise ContractRefusal("assessment payload must be an object")
    if wire.get("requires_human_approval") is False or \
            wire.get("execution_authority") is True:
        raise ContractRefusal("assessment violates constitution: execution authority "
                              "or waived human approval on the wire")
    verdict = wire.get("go_no_go")
    if verdict not in GO_NO_GO_TO_VERDICT:
        raise ContractRefusal(f"unknown go_no_go {verdict!r}")
    if not wire.get("opportunity_packet_id"):
        raise ContractRefusal("opportunity_packet_id is required")
    return {
        "assessment_id": str(uuid.uuid4()),
        "packet_id": str(wire["opportunity_packet_id"])
        if _is_uuid(wire["opportunity_packet_id"]) else str(uuid.uuid4()),
        "schema_version": KERNEL_SCHEMA_VERSION,
        "assessed_by": "spiffe://uniimente.internal/organ/wealthmachine",
        "assessed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "verdict": GO_NO_GO_TO_VERDICT[verdict],
        "opportunity_score": wire.get("opportunity_score"),
        "adversarial_cases": {
            "bull": "see structured_reasons",
            "bear": "see structured_reasons",
            "do_nothing": "status quo persists",
        },
        "structured_reasons": list(wire.get("reasons", [])),
        "requires_human_approval": True,       # constitutional constant
        "execution_authority": False,          # constitutional constant
    }


__all__ = ["KERNEL_SCHEMA_VERSION", "PINNED_SCHEMA_HASHES", "ContractRefusal",
           "wire_packet_to_kernel", "wire_assessment_to_kernel"]
