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
    strongest_objection: str = ""  # the best argument against approving
    status: str = "pending"  # pending | approved | rejected | edited | held | expired
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: Optional[datetime] = None  # stale requests close automatically
    decided_at: Optional[datetime] = None
    decided_via: Optional[str] = None  # "sms" | "dashboard"


@dataclass
class CapabilityGrant:
    """The executable authorization artifact: a single-purpose, exactly
    scoped, expiring, revocable permission minted from a human approval.
    Approval never widens standing autonomy — a grant authorizes one exact
    action against one exact resource, a bounded number of times, for a
    bounded window. Everything about its lifecycle is ledgered."""

    id: str = field(default_factory=_uuid)
    requester_identity: str = ""  # organ/service that asked
    approver_identity: str = ""  # human actor who said yes
    approval_request_id: str = ""  # the ApprovalRequest it was minted from
    action_type: str = ""  # e.g. "publish_post" | "send_dm" | "run_validation"
    exact_action: str = ""  # human-readable exact act authorized
    resource: str = ""  # exact resource id (draft id, packet id, lane id...)
    account_lane_id: str = ""
    named_targets: List[str] = field(default_factory=list)
    max_cost: float = 0.0
    currency: str = "USD"
    max_frequency: str = ""  # e.g. "1/day"; informational bound
    maximum_uses: int = 1
    uses_consumed: int = 0
    issued_at: datetime = field(default_factory=_utcnow)
    not_before: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    evidence_refs: List[str] = field(default_factory=list)
    policy_version: str = ""
    constitution_hash: str = ""
    risk_tier: str = "tier4"  # consequential by default
    rollback_note: str = ""
    revocation_status: str = "active"  # active | revoked
    revoked_at: Optional[datetime] = None
    revoked_by: str = ""
    revocation_reason: str = ""
    idempotency_key: str = field(default_factory=_uuid)
    trace_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


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
class Idea:
    """A raw operator thought entering the idea refinery."""

    id: str = field(default_factory=_uuid)
    raw_text: str = ""
    thesis: str = ""
    audiences: List[Dict[str, Any]] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    status: str = "pending"  # pending | refined | archived
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class OpportunityPacket:
    """A business signal distilled for venture evaluation (wire contract —
    see services/venture_protocol.py)."""

    id: str = field(default_factory=_uuid)
    source: str = ""  # daleobanks sensor or "operator"
    source_ref: str = ""  # idea id, mention id, url...
    signal_type: str = "operator_thought"
    observed_pain: str = ""
    core_thesis: str = ""
    audience: str = ""
    cultural_context: str = ""
    language: str = "en"
    customer_segment: str = ""
    buyer_type: str = ""
    urgency: str = "medium"  # low | medium | high
    evidence: List[str] = field(default_factory=list)
    possible_offer: str = ""
    monetization_paths: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    smallest_validation_action: str = ""
    confidence: float = 0.5
    created_at: datetime = field(default_factory=_utcnow)
    status: str = "pending"  # pending | approved | rejected | sent | assessed


@dataclass
class VentureAssessment:
    """WealthMachineIntelligence's verdict on an OpportunityPacket."""

    id: str = field(default_factory=_uuid)
    opportunity_packet_id: str = ""
    go_no_go: str = "needs_more_evidence"  # go | defer | kill | needs_more_evidence
    opportunity_score: float = 0.0
    market_alignment: float = 0.0
    expected_roi: str = ""
    risk_level: str = "medium"  # low | medium | high
    legal_readiness: str = "unreviewed"
    product_hypothesis: str = ""
    pricing_hypothesis: str = ""
    validation_plan: List[str] = field(default_factory=list)
    monetization_paths: List[str] = field(default_factory=list)
    recommended_next_action: str = ""
    requires_human_approval: bool = True
    reasons: List[str] = field(default_factory=list)
    cases: List[Dict[str, Any]] = field(default_factory=list)  # adversarial cases
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class ValidationResult:
    """What the world said when an approved validation action ran.

    The terminal object of the institutional loop. Negative, mixed, and
    inconclusive results are first-class records — zero response is still
    a completed observation, not an absence."""

    id: str = field(default_factory=_uuid)
    schema_version: str = "1.1"
    opportunity_packet_id: str = ""
    venture_assessment_id: str = ""
    experiment_ref: str = ""
    capability_grant_id: str = ""
    account_lane_id: str = ""
    validation_type: str = ""  # content_probe | landing_page | interviews | waitlist
    hypothesis: str = ""
    intervention: str = ""
    observation_window_start: str = ""  # ISO timestamp
    observation_window_end: str = ""  # ISO timestamp
    success_threshold: str = ""
    failure_threshold: str = ""
    measured_outcomes: Dict[str, Any] = field(default_factory=dict)
    raw_evidence_refs: List[str] = field(default_factory=list)
    evidence_tier: str = "observation"  # payment|commitment|conversation|engagement|observation
    evidence_quality: float = 0.0  # [0, 1]
    confounders: List[str] = field(default_factory=list)
    result_classification: str = "inconclusive"  # success|failure|mixed|inconclusive|negative
    causal_note: str = ""
    economic_result: str = ""
    trust_result: str = ""
    next_decision: str = ""
    recorded_by: str = ""
    trace_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    signal_count: int = 0
    reply_quality: str = ""
    signup_count: int = 0
    paid_count: int = 0
    revenue_amount: float = 0.0
    objections: List[str] = field(default_factory=list)
    qualitative_notes: str = ""
    next_recommendation: str = ""
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class MediaAssetDraft:
    """A draft piece of media. Drafts never publish themselves — they wait
    in the approval queue like everything else with real-world consequences."""

    id: str = field(default_factory=_uuid)
    source_opportunity_packet_id: Optional[str] = None
    source_thought: str = ""
    account_lane: str = "main"
    platform: str = "x"
    language: str = "en"
    cultural_context: str = ""
    format: str = "post"  # post | thread | video_script | landing_page | interview_script | outreach_dm | newsletter
    title: str = ""
    draft_text: str = ""
    script: str = ""
    caption: str = ""
    hook: str = ""
    cta: str = ""
    disclosure_needed: bool = False
    risk_level: str = "low"  # low | medium | high
    approval_status: str = "pending"  # pending | approved | rejected | edited
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class AccountLane:
    """A distinct, authentic publishing lane (brand/project/page). Never a
    fake person — identity types are validated by services/venture_protocol.py."""

    id: str = field(default_factory=_uuid)
    name: str = ""
    platform: str = "x"
    identity_type: str = "brand_account"
    purpose: str = ""
    audience: str = ""
    language: str = "en"
    cultural_context: str = ""
    allowed_topics: List[str] = field(default_factory=list)
    forbidden_topics: List[str] = field(default_factory=list)
    monetization_policy: str = "none"
    disclosure_policy: str = "always_disclose_sponsorships"
    posting_policy: str = "approval_required"
    approval_required: bool = True
    risk_level: str = "low"
    active: bool = False


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
    "CapabilityGrant",
    "SelfSignal",
    "ContextPacket",
    "Idea",
    "OpportunityPacket",
    "VentureAssessment",
    "ValidationResult",
    "MediaAssetDraft",
    "AccountLane",
    "PersonaVersion",
]
