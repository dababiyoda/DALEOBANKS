"""Lightweight data models used by the in-memory store for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


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
    "PersonaVersion",
]
