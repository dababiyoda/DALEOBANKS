"""The anti-cathedral rule as executable policy, and the lexicographic
metric hierarchy that keeps lower-level output from purchasing its way
past constitutional health.

Anti-cathedral: when the configured external-evidence window is empty —
no ValidationResults recorded inside EVIDENCE_WINDOW_DAYS — internal
expansion is denied. Security repair, compliance repair, critical
reliability repair, and work that directly produces or unblocks external
evidence remain permitted. The institution must not become a
sophisticated procrastination machine.

Metric hierarchy (lexicographic — no lower layer buys off a higher one):
  1. constitutional health   (a breach hard-zeros the period)
  2. evidence quality        (external reality gates everything below)
  3. trusted usefulness / 4. adoption / 5. economics / 6. efficiency /
  7. option value            (reported, never traded upward)

Evidence-Weighted J = goal-aligned J × evidence multiplier × health gate.
With zero external evidence the multiplier is zero: activity without
reality-contact is not progress, by construction.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, UTC
from typing import Any, Dict, Optional

from db.models import ApprovalRequest, ValidationResult
from services.ledger import DecisionLedger, get_ledger

# Work categories the policy evaluator recognizes. Anything else is denied.
WORK_CATEGORIES = frozenset({
    "external_evidence_producing",
    "unblocks_external_evidence",
    "security_repair",
    "compliance_repair",
    "critical_reliability_repair",
    "internal_expansion",
})

# Categories permitted even when the evidence window is empty.
ALWAYS_PERMITTED = frozenset({
    "external_evidence_producing",
    "unblocks_external_evidence",
    "security_repair",
    "compliance_repair",
    "critical_reliability_repair",
})

# Evidence tiers → weight. Payment outranks everything; passive
# observation barely counts. Matches ALLOWED_EVIDENCE_TIERS.
TIER_WEIGHTS = {
    "payment": 1.0,
    "commitment": 0.8,
    "conversation": 0.6,
    "engagement": 0.4,
    "observation": 0.2,
}

# Ledger events that constitute a material constitutional breach.
BREACH_EVENTS = frozenset({"constitutional_violation"})


def window_days() -> int:
    try:
        return int(os.getenv("EVIDENCE_WINDOW_DAYS", "14"))
    except ValueError:
        return 14


def evidence_window(session: Any) -> Dict[str, Any]:
    """State of the external-evidence window: recorded ValidationResults
    inside the configured horizon."""
    horizon = datetime.now(UTC) - timedelta(days=window_days())
    results = [
        r for r in session.query(ValidationResult).all()
        if r.created_at >= horizon
    ]
    return {
        "window_days": window_days(),
        "validation_results": len(results),
        "empty": len(results) == 0,
    }


def evaluate_work(
    session: Any,
    category: str,
    *,
    description: str = "",
    ledger: Optional[DecisionLedger] = None,
) -> Dict[str, Any]:
    """Classify proposed work and decide whether it may proceed under the
    anti-cathedral rule. Decisions are ledgered — the record of what the
    institution refused to build is part of its memory."""
    ledger = ledger or get_ledger()
    window = evidence_window(session)

    if category not in WORK_CATEGORIES:
        decision = {"allowed": False, "category": category, "window": window,
                    "reason": f"unknown work category; allowed: {sorted(WORK_CATEGORIES)}"}
    elif category in ALWAYS_PERMITTED:
        decision = {"allowed": True, "category": category, "window": window,
                    "reason": "permitted regardless of evidence window"}
    elif window["empty"]:
        decision = {"allowed": False, "category": category, "window": window,
                    "reason": (
                        "external-evidence window is empty: internal expansion is "
                        "blocked until the institution records contact with reality"
                    )}
    else:
        decision = {"allowed": True, "category": category, "window": window,
                    "reason": "evidence window is non-empty"}

    ledger.record("anti_cathedral_decision", {
        "category": category,
        "allowed": decision["allowed"],
        "description": (description or "")[:200],
        "window_results": window["validation_results"],
    })
    return decision


# --------------------------------------------------------------------- #
# Metric hierarchy
# --------------------------------------------------------------------- #
def constitutional_health(ledger: Optional[DecisionLedger] = None) -> Dict[str, Any]:
    """Layer 1. A broken ledger chain or a recorded breach event zeroes
    the period — nothing below can buy it back."""
    ledger = ledger or get_ledger()
    chain_ok, broken_at = ledger.verify_chain()
    breaches = [e for e in ledger.entries() if e.get("event") in BREACH_EVENTS]
    healthy = chain_ok and not breaches
    return {
        "healthy": healthy,
        "gate": 1.0 if healthy else 0.0,
        "chain_ok": chain_ok,
        "breach_events": len(breaches),
    }


def evidence_quality_multiplier(session: Any) -> float:
    """Layer 2. The average tier-weighted quality of in-window results.
    Zero results means zero — internal activity earns nothing here."""
    horizon = datetime.now(UTC) - timedelta(days=window_days())
    results = [
        r for r in session.query(ValidationResult).all()
        if r.created_at >= horizon
    ]
    if not results:
        return 0.0
    scores = [
        TIER_WEIGHTS.get(r.evidence_tier, 0.2) * max(0.0, min(1.0, r.evidence_quality))
        for r in results
    ]
    return round(sum(scores) / len(scores), 4)


def evidence_weighted_j(
    base_j: float,
    session: Any,
    ledger: Optional[DecisionLedger] = None,
) -> Dict[str, Any]:
    health = constitutional_health(ledger)
    multiplier = evidence_quality_multiplier(session)
    return {
        "base_j": base_j,
        "constitutional_gate": health["gate"],
        "evidence_multiplier": multiplier,
        "evidence_weighted_j": round(base_j * multiplier * health["gate"], 4),
    }


def institutional_metrics(
    session: Any,
    ledger: Optional[DecisionLedger] = None,
    base_j: Optional[float] = None,
) -> Dict[str, Any]:
    """The numbers the institution actually grows by."""
    from services.decision_episode import loop_closure_rate

    ledger = ledger or get_ledger()
    results = session.query(ValidationResult).all()
    negatives = [r for r in results if r.result_classification == "negative"]
    decided = [
        r for r in session.query(ApprovalRequest).all()
        if r.decided_at is not None and r.decided_via != "expiry"
    ]
    latencies = sorted((r.decided_at - r.created_at).total_seconds() for r in decided)

    metrics: Dict[str, Any] = {
        "constitutional_health": constitutional_health(ledger),
        "evidence_window": evidence_window(session),
        "evidence_multiplier": evidence_quality_multiplier(session),
        **loop_closure_rate(session, ledger=ledger),
        "validation_results_total": len(results),
        "negative_results_retained": len(negatives),
        "negative_retention_rate": (len(negatives) / len(results)) if results else 0.0,
        "founder_decisions": len(decided),
        "median_approval_latency_seconds": latencies[len(latencies) // 2] if latencies else None,
    }
    if base_j is not None:
        metrics["evidence_weighted"] = evidence_weighted_j(base_j, session, ledger)
    return metrics


__all__ = [
    "WORK_CATEGORIES", "ALWAYS_PERMITTED", "TIER_WEIGHTS",
    "window_days", "evidence_window", "evaluate_work",
    "constitutional_health", "evidence_quality_multiplier",
    "evidence_weighted_j", "institutional_metrics",
]
