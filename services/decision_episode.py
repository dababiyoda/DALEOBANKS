"""DecisionEpisode: a read-model projection over canonical records.

One episode per OpportunityPacket, linking signal → provenance →
interpretation → thesis → packet → assessments → human decisions →
capability grants → executed actions → validation results → causal notes
→ policy impact. The projection reads the in-memory store and the
hash-chained ledger; it never mutates either. Killed, deferred, and
negative-outcome episodes are episodes — missing stages are named
explicitly rather than hidden.

Post-hoc reinterpretation creates new ValidationResult/ledger records;
history is never rewritten here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from db.models import ApprovalRequest, Idea, OpportunityPacket, ValidationResult, VentureAssessment
from services.ledger import DecisionLedger, get_ledger
from services.venture_protocol import assessment_to_wire, packet_to_wire

# The canonical stage names, in loop order. A stage absent from an episode
# appears in missing_stages so incompleteness is visible, not silent.
STAGES = (
    "signal",
    "provenance",
    "interpretation",
    "thesis",
    "opportunity_packet",
    "venture_assessment",
    "human_decision",
    "capability_grant",
    "executed_action",
    "validation_result",
    "causal_note",
    "policy_impact",
)


def _ledger_events_for(ledger: DecisionLedger, packet_id: str) -> List[Dict[str, Any]]:
    events = []
    for entry in ledger.entries():
        payload = entry.get("payload") or {}
        if packet_id in (
            payload.get("id"), payload.get("packet_id"),
            payload.get("opportunity_packet_id"),
        ):
            events.append({"event": entry.get("event"), "ts": entry.get("ts"),
                           "payload": payload})
    return events


def build_episode(
    session: Any,
    packet_id: str,
    ledger: Optional[DecisionLedger] = None,
) -> Optional[Dict[str, Any]]:
    ledger = ledger or get_ledger()
    packet = session.query(OpportunityPacket).filter(lambda p: p.id == packet_id).first()
    if packet is None:
        return None

    idea = None
    if packet.source_ref:
        idea = session.query(Idea).filter(lambda i: i.id == packet.source_ref).first()

    assessments = session.query(VentureAssessment).filter(
        lambda a: a.opportunity_packet_id == packet_id
    ).all()
    results = session.query(ValidationResult).filter(
        lambda r: r.opportunity_packet_id == packet_id
    ).all()
    approvals = [
        a for a in session.query(ApprovalRequest).all()
        if (a.payload or {}).get("opportunity_packet_id") == packet_id
    ]
    # CapabilityGrant lands in a later stage; tolerate its absence so the
    # projection is honest about what exists rather than what is planned.
    grants: List[Any] = []
    try:
        from db.models import CapabilityGrant  # type: ignore
        grants = [
            g for g in session.query(CapabilityGrant).all()
            if getattr(g, "resource", "") == packet_id
            or (getattr(g, "metadata", {}) or {}).get("opportunity_packet_id") == packet_id
        ]
    except ImportError:
        pass

    events = _ledger_events_for(ledger, packet_id)
    decisions = [e for e in events if e["event"] in
                 ("opportunity_decision", "venture_assessment", "validation_result_recorded")]
    executed = [e for e in events if e["event"].startswith("publish")
                or e["event"].startswith("executed")]
    policy_events = [e for e in events if e["event"].startswith("policy")]

    episode: Dict[str, Any] = {
        "id": packet.id,
        "signal": ({"idea_id": idea.id, "raw_text": idea.raw_text} if idea else None),
        "provenance": ({"risk_flags": idea.risk_flags, "created_at": idea.created_at.isoformat()}
                       if idea else None),
        "interpretation": (idea.thesis or None) if idea else None,
        "thesis": packet.core_thesis or None,
        "opportunity_packet": packet_to_wire(packet),
        "venture_assessment": [assessment_to_wire(a) for a in assessments] or None,
        "human_decision": ({
            "packet_status": packet.status,
            "approval_requests": [{
                "id": a.id, "kind": a.kind, "status": a.status,
                "summary": a.summary, "created_at": a.created_at.isoformat(),
            } for a in approvals],
            "ledger_decisions": decisions,
        } if (approvals or decisions or packet.status != "pending") else None),
        "capability_grant": ([{"id": g.id, "action_type": g.action_type,
                               "revocation_status": g.revocation_status}
                              for g in grants] or None),
        "executed_action": executed or None,
        "validation_result": [{
            "id": r.id, "result_classification": r.result_classification,
            "evidence_tier": r.evidence_tier, "evidence_quality": r.evidence_quality,
            "hypothesis": r.hypothesis, "measured_outcomes": r.measured_outcomes,
            "causal_note": r.causal_note, "next_decision": r.next_decision,
            "created_at": r.created_at.isoformat(),
        } for r in results] or None,
        "causal_note": [r.causal_note for r in results if r.causal_note] or None,
        "policy_impact": policy_events or None,
        "ledger_events": events,
    }
    episode["missing_stages"] = [s for s in STAGES if not episode.get(s)]
    episode["loop_closed"] = "validation_result" not in episode["missing_stages"]
    return episode


def list_episodes(session: Any, ledger: Optional[DecisionLedger] = None) -> List[Dict[str, Any]]:
    packets = session.query(OpportunityPacket).all()
    episodes = []
    for packet in sorted(packets, key=lambda p: p.created_at, reverse=True):
        built = build_episode(session, packet.id, ledger=ledger)
        if built is not None:
            episodes.append(built)
    return episodes


def loop_closure_rate(session: Any, ledger: Optional[DecisionLedger] = None) -> Dict[str, Any]:
    episodes = list_episodes(session, ledger=ledger)
    closed = sum(1 for e in episodes if e["loop_closed"])
    return {
        "episodes": len(episodes),
        "closed": closed,
        "loop_closure_rate": (closed / len(episodes)) if episodes else 0.0,
    }


__all__ = ["STAGES", "build_episode", "list_episodes", "loop_closure_rate"]
