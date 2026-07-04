"""Lightweight data models used by the in-memory store for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


def _approval_code() -> str:
    """Short human-friendly code the operator types back (no ambiguous chars)."""
    import secrets

    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(4))


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Tweet:
    """Tweet records with engagement metrics."""

    id: str
    text: str
    kind: str  # proposal|reply|quote
    topic: Optional[str] = None
    hour_bin: Optional[int] = None
    cta_variant: Optional[str] = None
    intensity: Optional[int] = None
    ref_tweet_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    likes: int = 0
    rts: int = 0
    replies: int = 0
    quotes: int = 0
    authority_score: float = 0.0
    j_score: Optional[float] = 0.0
    predicted_j: Optional[float] = None  # simulator forecast at publish time


@dataclass
class Action:
    """Action logs for all system activities."""

    id: str = field(default_factory=_uuid)
    kind: str = ""
    meta_json: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class PilotAcceptance:
    """Records of pilots that were accepted by stakeholders."""

    id: str = field(default_factory=_uuid)
    pilot_name: str = ""
    accepted_by: Optional[str] = None
    scope: Optional[str] = None
    accepted_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactFork:
    """Records of artifacts created or forked from agent outputs."""

    id: str = field(default_factory=_uuid)
    artifact_name: str = ""
    source_url: Optional[str] = None
    platform: Optional[str] = None
    forked_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoalitionPartner:
    """Organizations or individuals that joined coalition efforts."""

    id: str = field(default_factory=_uuid)
    partner_name: str = ""
    partner_type: Optional[str] = None
    joined_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Citation:
    """External citations attributed to the agent's work."""

    id: str = field(default_factory=_uuid)
    source_title: str = ""
    url: Optional[str] = None
    context: Optional[str] = None
    cited_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HelpfulnessFeedback:
    """Feedback captured about the agent's helpfulness."""

    id: str = field(default_factory=_uuid)
    channel: str = ""
    rating: float = 0.0
    comment: Optional[str] = None
    reference_id: Optional[str] = None
    captured_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KPI:
    """KPI tracking over time."""

    id: str = field(default_factory=_uuid)
    name: str = ""
    value: float = 0.0
    period_start: datetime = field(default_factory=_utcnow)
    period_end: datetime = field(default_factory=_utcnow)


@dataclass
class Note:
    """Improvement notes and reflections."""

    id: str = field(default_factory=_uuid)
    text: str = ""
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class FollowersSnapshot:
    """Daily follower count snapshots."""

    ts: datetime = field(default_factory=_utcnow)
    follower_count: int = 0


@dataclass
class Redirect:
    """Tracked redirect links for revenue measurement."""

    id: str = field(default_factory=_uuid)
    label: str = ""
    target_url: str = ""
    utm: Optional[str] = None
    clicks: int = 0
    revenue: float = 0.0


@dataclass
class ArmsLog:
    """Multi-armed bandit experiment logs."""

    id: str = field(default_factory=_uuid)
    tweet_id: Optional[str] = None
    post_type: str = ""
    topic: Optional[str] = None
    hour_bin: Optional[int] = None
    cta_variant: Optional[str] = None
    intensity: Optional[int] = None
    sampled_prob: float = 0.0
    reward_j: Optional[float] = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class SensedEvent:
    """Events captured during the perception scan."""

    id: str = field(default_factory=_uuid)
    source: str = ""
    kind: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class Relationship:
    """Durable social memory: one record per account the agent interacts with."""

    id: str = ""  # platform user id (or handle when no id is available)
    handle: Optional[str] = None
    platform: str = "x"
    interaction_count: int = 0
    first_interaction_at: datetime = field(default_factory=_utcnow)
    last_interaction_at: datetime = field(default_factory=_utcnow)
    sentiment_score: float = 0.0  # running average in [-1, 1]
    topics: List[str] = field(default_factory=list)
    kinds: Dict[str, int] = field(default_factory=dict)  # interaction kind -> count


@dataclass
class Conversion:
    """A real, recorded revenue event (vs. the legacy click estimate)."""

    id: str = field(default_factory=_uuid)
    redirect_id: Optional[str] = None
    value: float = 0.0
    currency: str = "USD"
    source: str = "webhook"
    occurred_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryProposal:
    """A proposed addition to the agent's perception seeds, pending human review."""

    id: str = field(default_factory=_uuid)
    kind: str = ""  # "influencer" | "keyword"
    value: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | approved | rejected
    created_at: datetime = field(default_factory=_utcnow)
    decided_at: Optional[datetime] = None
    actor: Optional[str] = None


@dataclass
class GoalProposal:
    """A proposed OKR adjustment from the planner, pending human review."""

    id: str = field(default_factory=_uuid)
    proposal: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    status: str = "pending"  # pending | approved | rejected
    created_at: datetime = field(default_factory=_utcnow)
    decided_at: Optional[datetime] = None
    actor: Optional[str] = None


@dataclass
class ContextPacket:
    """One sensed item distilled into a structured, sanitized decision packet.

    Every sensor (mentions, DMs, timeline, trends, articles, self-signals)
    speaks this one language before anything reaches the instinct engine,
    selector, or generator — raw external text never travels as prompt sludge.
    """

    id: str = field(default_factory=_uuid)
    source: str = ""  # mention | dm | timeline | trend | article | self_signal
    raw_ref: str = ""  # id/url of the underlying item
    actor: Optional[str] = None
    topic: Optional[str] = None
    text: str = ""  # sanitized content (firewall-cleaned)
    claims: List[str] = field(default_factory=list)
    stakes: str = "low"  # low | medium | high
    incentives: Optional[str] = None
    human_cost: Optional[str] = None
    system_failure: Optional[str] = None
    evidence_needed: bool = False
    risk: float = 0.0  # injection/reputation risk in [0, 1]
    recommended_action: Optional[str] = None
    confidence: float = 1.0
    provenance: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class ApprovalRequest:
    """A request for operator judgment, answered by SMS or the dashboard.

    ``YES <code>`` approves exactly this request — approval never widens
    standing autonomy. A bare ``YES`` is honored only when exactly one P1
    request is pending; otherwise the code is mandatory.
    """

    id: str = field(default_factory=_uuid)
    code: str = field(default_factory=_approval_code)
    kind: str = ""  # "publish" | "identity_gate" | "instinct" | ...
    priority: str = "P2"  # P1 (urgent, bare-YES eligible) | P2 (code required)
    summary: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    status: str = "pending"  # pending | approved | rejected | edited | held | expired
    created_at: datetime = field(default_factory=_utcnow)
    decided_at: Optional[datetime] = None
    decided_via: Optional[str] = None  # "sms" | "dashboard"


@dataclass
class SelfSignal:
    """An operator-supplied thought (OPINION command). A signal to weigh,
    never automatic doctrine."""

    id: str = field(default_factory=_uuid)
    text: str = ""
    source: str = "operator_opinion"
    topics: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class PersonaVersion:
    """Persona version history with audit trail."""

    version: int
    hash: str
    actor: Optional[str]
    payload: Dict[str, Any]
    created_at: datetime = field(default_factory=_utcnow)


__all__ = [
    "Tweet",
    "Action",
    "KPI",
    "PilotAcceptance",
    "ArtifactFork",
    "CoalitionPartner",
    "Citation",
    "HelpfulnessFeedback",
    "Note",
    "FollowersSnapshot",
    "Redirect",
    "ArmsLog",
    "SensedEvent",
    "Relationship",
    "Conversion",
    "DiscoveryProposal",
    "GoalProposal",
    "ApprovalRequest",
    "SelfSignal",
    "ContextPacket",
    "PersonaVersion",
]
