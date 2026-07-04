"""ContextPacket builders: every sensor speaks one structured language.

Raw articles, social posts, DMs, trends, and self-signals are distilled into
:class:`db.models.ContextPacket` objects — sanitized text plus extracted
claims, stakes, incentives, human cost, system failure, evidence needs, and
injection risk — before they can influence planning or generation. The
firewall runs here, once, at the boundary, so downstream consumers never
touch raw external text.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from db.models import ContextPacket, SelfSignal
from services.prompt_firewall import PromptFirewall, get_firewall
from services.raw_vault import get_raw_vault

_STAKES_HIGH_MARKERS = [
    "death", "died", "lawsuit", "outage", "breach", "emergency", "recall",
    "explosion", "crisis", "evacuation", "fatal",
]
_INCENTIVE_MARKERS = [
    "profit", "funding", "subsidy", "election", "lobbying", "bonus",
    "market share", "quarterly", "donor",
]
_HUMAN_COST_MARKERS = [
    "died", "deaths", "jobs lost", "layoffs", "evicted", "sick", "injured",
    "unemployed", "homeless", "waitlist",
]
_SYSTEM_FAILURE_MARKERS = [
    "outage", "backlog", "queue", "collapse", "failure", "shortage",
    "bottleneck", "delay", "understaffed", "cost overrun",
]
_SOURCE_MARKERS = ["http://", "https://", "source:", "according to"]

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _extract_claims(text: str) -> List[str]:
    """Sentences that assert something checkable (figures, studies)."""
    claims = []
    for sentence in _SENTENCE_RE.split(text or ""):
        sentence = sentence.strip()
        if not sentence:
            continue
        lower = sentence.lower()
        if any(c.isdigit() for c in sentence) or "%" in sentence or "$" in sentence \
                or "study" in lower or "research" in lower:
            claims.append(sentence[:200])
    return claims[:5]


def _first_marker(lower: str, markers: List[str]) -> Optional[str]:
    for marker in markers:
        if marker in lower:
            return marker
    return None


def build_packet(
    *,
    source: str,
    raw_ref: str = "",
    text: str = "",
    actor: Optional[str] = None,
    topic: Optional[str] = None,
    trust: str = "untrusted",
    firewall: Optional[PromptFirewall] = None,
) -> ContextPacket:
    fw = firewall or get_firewall()
    scan = fw.scan(text or "")
    sanitized = fw.sanitize(text or "")
    lower = sanitized.lower()

    # The sanitizer never destroys the source: raw text goes to the vault
    # verbatim (with provenance) so audits and replays see what actually
    # arrived, while only the sanitized form may travel toward prompts.
    vault_id = None
    if text:
        vault_id = get_raw_vault().deposit(
            source=source, text=text, raw_ref=raw_ref, actor=actor,
            meta={"trust": trust, "injection_patterns": scan["patterns"]},
        )

    claims = _extract_claims(sanitized)
    has_source = any(marker in lower for marker in _SOURCE_MARKERS)
    if _first_marker(lower, _STAKES_HIGH_MARKERS):
        stakes = "high"
    elif claims:
        stakes = "medium"
    else:
        stakes = "low"

    return ContextPacket(
        source=source,
        raw_ref=str(raw_ref or ""),
        actor=actor,
        topic=topic,
        text=sanitized,
        claims=claims,
        stakes=stakes,
        incentives=_first_marker(lower, _INCENTIVE_MARKERS),
        human_cost=_first_marker(lower, _HUMAN_COST_MARKERS),
        system_failure=_first_marker(lower, _SYSTEM_FAILURE_MARKERS),
        evidence_needed=bool(claims) and not has_source,
        risk=scan["risk"],
        confidence=round(max(0.0, 1.0 - scan["risk"] * 0.7), 3),
        provenance={
            "trust": trust,
            "injection_patterns": scan["patterns"],
            "vault_id": vault_id,
        },
    )


def from_mention(mention: Dict[str, Any], topic: Optional[str] = None) -> ContextPacket:
    return build_packet(
        source="mention",
        raw_ref=mention.get("id", ""),
        text=mention.get("text", ""),
        actor=mention.get("username") or mention.get("author_id"),
        topic=topic,
    )


def from_dm(event: Dict[str, Any]) -> ContextPacket:
    return build_packet(
        source="dm",
        raw_ref=event.get("id", ""),
        text=event.get("text", ""),
        actor=event.get("sender_id"),
    )


def from_timeline_post(post: Dict[str, Any]) -> ContextPacket:
    return build_packet(
        source="timeline",
        raw_ref=post.get("id", ""),
        text=post.get("text", ""),
        actor=post.get("username") or post.get("author_id"),
    )


def from_trend(trend: Any) -> ContextPacket:
    name = trend.get("name") if isinstance(trend, dict) else str(trend)
    return build_packet(source="trend", text=str(name or ""), topic=str(name or ""))


def from_self_signal(signal: SelfSignal) -> ContextPacket:
    # The operator is trusted — but their thoughts are still signals to
    # weigh, so they travel in the same structured form as everything else.
    return build_packet(
        source="self_signal",
        raw_ref=signal.id,
        text=signal.text,
        actor="operator",
        trust="operator",
    )


def as_opportunity(
    packet: ContextPacket,
    kind: Optional[str] = None,
    relationship: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Adapt a packet to the InstinctEngine's opportunity shape."""
    return {
        "kind": kind or packet.source,
        "topic": packet.topic,
        "text": packet.text,
        "stakes": packet.stakes if packet.stakes == "high" else None,
        "injection_risk": packet.risk,
        "relationship": relationship,
    }


__all__ = [
    "build_packet", "from_mention", "from_dm", "from_timeline_post",
    "from_trend", "from_self_signal", "as_opportunity",
]
