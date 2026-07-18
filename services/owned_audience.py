"""Consent-first owned audience registry and campaign approval router.

This is the durable audience layer behind DALEOBANKS' authentic account lanes.
It captures direct, permissioned relationships instead of treating platform
followers as owned distribution. Campaigns are export-only in v1 and always
require the existing human approval line before recipient data can leave the
registry. No endpoint sends email, posts content, or simulates engagement.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from db.models import AccountLane, ApprovalRequest
from db.session import get_db_session
from services.ledger import get_ledger
from services.operator_line import get_operator_line
from services.security import RequestContext, require_role

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_APPROVED_STATUSES = {"approved", "edited"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 320 or not _EMAIL_RE.match(email):
        raise ValueError("a valid email address is required")
    return email


def _clean_list(values: List[str], *, limit: int = 20, item_limit: int = 80) -> List[str]:
    cleaned: List[str] = []
    for value in values or []:
        item = str(value).strip()
        if item and item not in cleaned:
            cleaned.append(item[:item_limit])
        if len(cleaned) >= limit:
            break
    return cleaned


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    visible = local[:1]
    return f"{visible}***@{domain}"


class SubscribeRequest(BaseModel):
    email: str
    consent: bool
    lane_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    locale: str = "en"
    consent_source: str = "direct_signup"
    consent_version: str = "v1"
    referral: str = ""


class UnsubscribeRequest(BaseModel):
    token: str


class CampaignCreateRequest(BaseModel):
    lane_id: str
    name: str
    subject: str
    body: str
    segment_tags: List[str] = Field(default_factory=list)
    locale: str = ""
    purpose: str = "newsletter"
    send_mode: str = "export_only"


class AudienceRegistry:
    """Append-only event log projected into current subscriber/campaign state."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path or os.getenv("AUDIENCE_STORE_PATH", "data/audience_events.jsonl"))
        self._lock = threading.RLock()
        self._subscribers: Dict[str, Dict[str, Any]] = {}
        self._campaigns: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self._lock:
            for raw in self.path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._apply(event)

    def _append(self, event_type: str, payload: Dict[str, Any]) -> None:
        event = {"event_id": str(uuid.uuid4()), "type": event_type, "ts": _now(), "payload": payload}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._apply(event)

    def _apply(self, event: Dict[str, Any]) -> None:
        event_type = event.get("type")
        payload = dict(event.get("payload") or {})
        if event_type == "subscriber_upserted":
            self._subscribers[payload["id"]] = payload
        elif event_type == "subscriber_unsubscribed":
            subscriber = self._subscribers.get(payload.get("id"))
            if subscriber:
                subscriber["status"] = "unsubscribed"
                subscriber["updated_at"] = payload.get("updated_at") or event.get("ts")
        elif event_type == "campaign_created":
            self._campaigns[payload["id"]] = payload
        elif event_type == "campaign_approval_bound":
            campaign = self._campaigns.get(payload.get("id"))
            if campaign:
                campaign["approval_request_id"] = payload.get("approval_request_id", "")
                campaign["updated_at"] = payload.get("updated_at") or event.get("ts")

    def subscribe(self, *, email: str, consent: bool, lane_ids: List[str], tags: List[str], locale: str, consent_source: str, consent_version: str, referral: str) -> Tuple[Dict[str, Any], str, bool]:
        if consent is not True:
            raise ValueError("explicit consent is required")
        normalized = _clean_email(email)
        email_hash = _sha256(normalized)
        existing = next((record for record in self._subscribers.values() if record["email_hash"] == email_hash), None)
        token = secrets.token_urlsafe(32)
        token_hash = _sha256(token)
        timestamp = _now()
        created = existing is None
        record = {
            "id": existing["id"] if existing else str(uuid.uuid4()),
            "email": normalized,
            "email_hash": email_hash,
            "unsubscribe_token_hash": token_hash,
            "status": "active",
            "lane_ids": _clean_list(list((existing or {}).get("lane_ids", [])) + lane_ids),
            "tags": _clean_list(list((existing or {}).get("tags", [])) + tags),
            "locale": (locale or "en").strip()[:20],
            "consent_source": (consent_source or "direct_signup").strip()[:80],
            "consent_version": (consent_version or "v1").strip()[:40],
            "referral": (referral or "").strip()[:200],
            "consented_at": timestamp,
            "created_at": (existing or {}).get("created_at", timestamp),
            "updated_at": timestamp,
        }
        self._append("subscriber_upserted", record)
        return dict(record), token, created

    def unsubscribe(self, token: str) -> bool:
        token_hash = _sha256((token or "").strip())
        for subscriber in self._subscribers.values():
            if secrets.compare_digest(subscriber.get("unsubscribe_token_hash", ""), token_hash):
                if subscriber.get("status") != "unsubscribed":
                    self._append("subscriber_unsubscribed", {"id": subscriber["id"], "updated_at": _now()})
                return True
        return False

    def list_subscribers(self, *, include_pii: bool = False) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for subscriber in sorted(self._subscribers.values(), key=lambda item: item["created_at"], reverse=True):
            row = dict(subscriber)
            row["email"] = subscriber["email"] if include_pii else _mask_email(subscriber["email"])
            row.pop("unsubscribe_token_hash", None)
            rows.append(row)
        return rows

    def create_campaign(self, request: CampaignCreateRequest) -> Dict[str, Any]:
        if request.send_mode != "export_only":
            raise ValueError("v1 supports export_only campaigns; direct sending is intentionally disabled")
        if not request.name.strip() or not request.subject.strip() or not request.body.strip():
            raise ValueError("name, subject, and body are required")
        timestamp = _now()
        campaign = {
            "id": str(uuid.uuid4()),
            "lane_id": request.lane_id,
            "name": request.name.strip()[:160],
            "subject": request.subject.strip()[:240],
            "body": request.body.strip()[:20000],
            "segment_tags": _clean_list(request.segment_tags),
            "locale": request.locale.strip()[:20],
            "purpose": request.purpose.strip()[:80],
            "send_mode": "export_only",
            "approval_request_id": "",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._append("campaign_created", campaign)
        return dict(campaign)

    def bind_approval(self, campaign_id: str, approval_request_id: str) -> None:
        if campaign_id not in self._campaigns:
            raise KeyError(campaign_id)
        self._append("campaign_approval_bound", {"id": campaign_id, "approval_request_id": approval_request_id, "updated_at": _now()})

    def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        campaign = self._campaigns.get(campaign_id)
        return dict(campaign) if campaign else None

    def list_campaigns(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in sorted(self._campaigns.values(), key=lambda row: row["created_at"], reverse=True)]

    def select_recipients(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        required_tags = set(campaign.get("segment_tags") or [])
        locale = campaign.get("locale") or ""
        lane_id = campaign.get("lane_id") or ""
        selected: List[Dict[str, Any]] = []
        for subscriber in self._subscribers.values():
            if subscriber.get("status") != "active":
                continue
            if lane_id and lane_id not in subscriber.get("lane_ids", []):
                continue
            if locale and subscriber.get("locale") != locale:
                continue
            if required_tags and not required_tags.issubset(set(subscriber.get("tags", []))):
                continue
            selected.append(dict(subscriber))
        return selected

    def stats(self) -> Dict[str, Any]:
        active = [item for item in self._subscribers.values() if item.get("status") == "active"]
        by_lane: Dict[str, int] = {}
        by_tag: Dict[str, int] = {}
        for subscriber in active:
            for lane_id in subscriber.get("lane_ids", []):
                by_lane[lane_id] = by_lane.get(lane_id, 0) + 1
            for tag in subscriber.get("tags", []):
                by_tag[tag] = by_tag.get(tag, 0) + 1
        return {"active_subscribers": len(active), "unsubscribed": len(self._subscribers) - len(active), "total_relationships": len(self._subscribers), "campaigns": len(self._campaigns), "by_lane": by_lane, "by_tag": by_tag}


_REGISTRY: Optional[AudienceRegistry] = None
_REGISTRY_PATH: Optional[str] = None


def get_audience_registry() -> AudienceRegistry:
    global _REGISTRY, _REGISTRY_PATH
    path = os.getenv("AUDIENCE_STORE_PATH", "data/audience_events.jsonl")
    if _REGISTRY is None or _REGISTRY_PATH != path:
        _REGISTRY = AudienceRegistry(path)
        _REGISTRY_PATH = path
    return _REGISTRY


def _require_lane(lane_id: str) -> AccountLane:
    with get_db_session() as session:
        lane = session.query(AccountLane).filter(lambda item: item.id == lane_id).first()
        if lane is None:
            raise HTTPException(status_code=422, detail="unknown account lane")
        return lane


def _approval_status(approval_request_id: str) -> str:
    if not approval_request_id:
        return "missing"
    with get_db_session() as session:
        request = session.query(ApprovalRequest).filter(lambda item: item.id == approval_request_id).first()
        return request.status if request else "missing"


audience_router = APIRouter(tags=["owned-audience"])


@audience_router.post("/api/audience/subscribe")
async def subscribe(request: SubscribeRequest, http_request: Request):
    lane_ids = _clean_list(request.lane_ids)
    for lane_id in lane_ids:
        _require_lane(lane_id)
    try:
        subscriber, token, created = get_audience_registry().subscribe(email=request.email, consent=request.consent, lane_ids=lane_ids, tags=request.tags, locale=request.locale, consent_source=request.consent_source, consent_version=request.consent_version, referral=request.referral)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_ledger().record("audience_subscribed", {"subscriber_id": subscriber["id"], "email_hash": subscriber["email_hash"], "lane_ids": subscriber["lane_ids"], "created": created, "source": subscriber["consent_source"], "request_id": getattr(http_request.state, "request_id", None)})
    return {"success": True, "created": created, "subscriber_id": subscriber["id"], "unsubscribe_token": token, "message": "Subscription recorded. Keep the unsubscribe token private."}


@audience_router.post("/api/audience/unsubscribe")
async def unsubscribe(request: UnsubscribeRequest):
    removed = get_audience_registry().unsubscribe(request.token)
    get_ledger().record("audience_unsubscribe_requested", {"matched": removed})
    return {"success": True, "message": "The subscription is inactive if the token was valid."}


@audience_router.get("/api/audience/stats")
async def audience_stats(_: RequestContext = Depends(require_role("admin"))):
    return get_audience_registry().stats()


@audience_router.get("/api/audience/subscribers")
async def list_subscribers(_: RequestContext = Depends(require_role("admin"))):
    subscribers = get_audience_registry().list_subscribers(include_pii=False)
    return {"count": len(subscribers), "subscribers": subscribers}


@audience_router.post("/api/audience/campaigns")
async def create_campaign(request: CampaignCreateRequest, _: RequestContext = Depends(require_role("admin"))):
    lane = _require_lane(request.lane_id)
    registry = get_audience_registry()
    try:
        campaign = registry.create_campaign(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    recipients = registry.select_recipients(campaign)
    with get_db_session() as session:
        approval = get_operator_line().request_approval(
            session,
            kind="audience_campaign_export",
            summary=f"Approve campaign '{campaign['name']}' for {len(recipients)} consented recipients",
            payload={"campaign_id": campaign["id"], "lane_id": lane.id, "lane_name": lane.name, "recipient_count": len(recipients), "subject": campaign["subject"], "content": campaign["body"], "send_mode": "export_only"},
            rationale="This exports a consented recipient list for one reviewed campaign. It does not send automatically or widen standing autonomy.",
            strongest_objection="Even consented outreach can damage trust if audience fit, claims, frequency, or unsubscribe handling are weak.",
            priority="P2",
        )
    registry.bind_approval(campaign["id"], approval.id)
    get_ledger().record("audience_campaign_created", {"campaign_id": campaign["id"], "lane_id": lane.id, "recipient_count": len(recipients), "approval_request_id": approval.id})
    return {"success": True, "campaign_id": campaign["id"], "recipient_count": len(recipients), "approval_request_id": approval.id, "approval_code": approval.code, "status": "pending_approval"}


@audience_router.get("/api/audience/campaigns")
async def list_campaigns(_: RequestContext = Depends(require_role("admin"))):
    campaigns = get_audience_registry().list_campaigns()
    for campaign in campaigns:
        campaign["approval_status"] = _approval_status(campaign.get("approval_request_id", ""))
        campaign["recipient_count"] = len(get_audience_registry().select_recipients(campaign))
        campaign.pop("body", None)
    return {"count": len(campaigns), "campaigns": campaigns}


@audience_router.get("/api/audience/campaigns/{campaign_id}/export")
async def export_campaign(campaign_id: str, _: RequestContext = Depends(require_role("admin"))):
    registry = get_audience_registry()
    campaign = registry.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    approval_status = _approval_status(campaign.get("approval_request_id", ""))
    if approval_status not in _APPROVED_STATUSES:
        raise HTTPException(status_code=409, detail=f"campaign export requires an approved request; current status is {approval_status}")
    recipients = registry.select_recipients(campaign)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["email", "locale", "tags", "lane_ids", "consent_source", "consented_at"])
    for subscriber in recipients:
        writer.writerow([subscriber["email"], subscriber.get("locale", ""), "|".join(subscriber.get("tags", [])), "|".join(subscriber.get("lane_ids", [])), subscriber.get("consent_source", ""), subscriber.get("consented_at", "")])
    get_ledger().record("audience_campaign_exported", {"campaign_id": campaign_id, "recipient_count": len(recipients)})
    filename = re.sub(r"[^a-zA-Z0-9_-]+", "-", campaign.get("name", "campaign")).strip("-") or "campaign"
    return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})


__all__ = ["AudienceRegistry", "SubscribeRequest", "CampaignCreateRequest", "audience_router", "get_audience_registry"]
