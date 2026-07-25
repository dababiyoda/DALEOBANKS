"""Adversarial underwriting cases: the committee argues with itself.

Every assessment carries competing cases — bull, bear, fraud/manipulation,
incumbent response, adoption friction, do-nothing, opportunity cost. The
critics are deterministic (testable, model-free) and may disagree;
disagreement is preserved, never averaged away. A severe unresolved
"against" case caps the verdict regardless of score: model or heuristic
confidence is not authority.

This module is mirrored from WealthMachineIntelligence (src/services/adversarial.py) so
the mock evaluator and the real engine present the same case structure.
Keep the two files field-for-field compatible.
"""

from __future__ import annotations

from typing import Any, Dict, List

SEVERE = "high"


def _case(name: str, stance: str, severity: str, argument: str,
          resolved: bool = False) -> Dict[str, Any]:
    return {"case": name, "stance": stance, "severity": severity,
            "argument": argument, "resolved": resolved}


def build_cases(packet: Dict[str, Any], opportunity_score: float,
                market_alignment: float) -> List[Dict[str, Any]]:
    evidence: List[str] = list(packet.get("evidence") or [])
    monetization: List[str] = list(packet.get("monetization_paths") or [])
    urgency = packet.get("urgency", "medium")
    offer = packet.get("possible_offer") or "the offer"
    cases: List[Dict[str, Any]] = []

    # Bull: the strongest honest argument for.
    bull_points = []
    if opportunity_score >= 0.55:
        bull_points.append(f"opportunity score {opportunity_score} clears threshold")
    if urgency == "high":
        bull_points.append("urgency is high — the pain is current, not hypothetical")
    if monetization:
        bull_points.append(f"{len(monetization)} monetization paths identified")
    cases.append(_case(
        "bull", "for", "medium" if bull_points else "low",
        "; ".join(bull_points) or "no strong affirmative signal beyond the baseline",
    ))

    # Bear: always argues against — names the weakest link on purpose.
    weakest = []
    if len(evidence) < 3:
        weakest.append(f"only {len(evidence)} evidence item(s); demand is asserted, not shown")
    if not any("paid" in m or "pay" in m for m in monetization):
        weakest.append("no path implies anyone has agreed to pay")
    weakest.append("willingness to pay is untested until a buyer commits value")
    cases.append(_case("bear", "against",
                       SEVERE if len(evidence) == 0 else "medium",
                       "; ".join(weakest)))

    # Fraud / manipulation: sybil-shaped evidence caps the verdict.
    deduped = {e.strip().lower() for e in evidence if e and e.strip()}
    sybil = len(evidence) >= 2 and len(deduped) < len(evidence)
    thin_urgent = urgency == "high" and len(deduped) <= 1
    if sybil or thin_urgent:
        cases.append(_case(
            "fraud_manipulation", "against", SEVERE,
            ("evidence items are duplicated or near-identical — consistent with "
             "manufactured demand" if sybil else
             "high urgency asserted on a single evidence item — verify the "
             "signal is organic before acting"),
        ))
    else:
        cases.append(_case(
            "fraud_manipulation", "neutral", "low",
            "no sybil indicators in the evidence set; keep verifying provenance",
        ))

    # Incumbent response: who retaliates, and how cheaply?
    cases.append(_case(
        "incumbent_response", "against", "medium",
        f"an incumbent with distribution can copy {offer} quickly; the durable "
        "edge must be trust and cultural specificity, not the artifact itself",
    ))

    # Adoption friction: interest is not behavior change.
    cases.append(_case(
        "adoption_friction", "against",
        "medium" if packet.get("buyer_type") == "consumer" else "low",
        "audience interest does not imply workflow change; the smallest "
        "validation action must measure behavior, not applause",
    ))

    # Do-nothing: the mandatory comparison.
    cases.append(_case(
        "do_nothing", "against", "low",
        "skipping this preserves founder attention for a stronger signal; the "
        "cost of waiting is one cycle of learning, not the market",
    ))

    # Opportunity cost: every yes is a no to something else.
    cases.append(_case(
        "opportunity_cost", "against",
        "medium" if opportunity_score < 0.65 else "low",
        f"score {opportunity_score} vs. alignment {market_alignment}: compare "
        "against the best alternative use of the same attention and budget",
    ))

    return cases


def severe_unresolved(cases: List[Dict[str, Any]]) -> List[str]:
    """Names of severe, unresolved 'against' cases. A non-empty list caps
    the verdict — a high score may not erase a severe unresolved risk."""
    return [
        c["case"] for c in cases
        if c["stance"] == "against" and c["severity"] == SEVERE
        and not c.get("resolved")
    ]


__all__ = ["build_cases", "severe_unresolved", "SEVERE"]
