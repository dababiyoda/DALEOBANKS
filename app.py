#!/usr/bin/env python3
"""
DaLeoBanks - Autonomous AI Agent Dashboard
FastAPI application with real-time WebSocket updates
"""

import asyncio
import json
import os
import sys
import traceback
import uuid
import secrets
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Optional, Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ValidationError

from config import get_config, update_config
from db.session import init_db, get_db_session
from db.models import *
from services.persona_store import PersonaStore
from services.admin_rate import AdminRateLimiter
from services.analytics import AnalyticsService
from services.kpi import KPIService
from services.logging_utils import get_logger
from services.multiplexer import SocialMultiplexer
from services.x_client import XClient
from services.llm_adapter import LLMAdapter
from services.generator import Generator
from services.selector import Selector
from services.optimizer import Optimizer
from services.self_model import SelfModelService
from services.reflection import ReflectionService
from services.ledger import get_kill_switch, get_ledger
from services.operator_line import get_operator_line, validate_twilio_signature
from services.idea_refinery import IdeaRefinery
from services.wealthmachine_client import get_wealthmachine_client
from services.venture_protocol import validate_assessment_wire, validate_identity_type, LANE_POLICY
from services.security import (
    RequestContext,
    get_request_context,
    require_role,
    require_any_role,
)
from services.observability import (
    elapsed,
    metrics_router,
    record_request_metrics,
    request_timer,
)

# Import runner for background tasks
import runner

# Initialize logger
logger = get_logger(__name__)

# Global state
config = get_config()

# Initialize FastAPI app
app = FastAPI(
    title="DaLeoBanks AI Agent",
    description="Autonomous AI agent with self-evolution capabilities",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router)

persona_store = PersonaStore()
admin_limiter = AdminRateLimiter()
analytics_service = AnalyticsService()
kpi_service = KPIService()
x_client = XClient()
multiplexer = SocialMultiplexer(config=config, x_client=x_client)
llm_adapter = LLMAdapter()
generator = Generator(persona_store, llm_adapter)
selector = Selector(persona_store)
optimizer = Optimizer()
self_model_service = SelfModelService(persona_store)
reflection_service = ReflectionService()
idea_refinery = IdeaRefinery(llm_adapter)

# WebSocket connections for real-time updates
websocket_connections: List[WebSocket] = []

# Pydantic models for API
class ToggleRequest(BaseModel):
    live: bool

class ModeRequest(BaseModel):
    mode: str

class NoteRequest(BaseModel):
    text: str

class RedirectRequest(BaseModel):
    label: str
    target_url: str
    utm: Optional[str] = None
    rev_per_click: Optional[float] = None

class PersonaUpdateRequest(BaseModel):
    payload: Dict[str, Any]

class CrisisRequest(BaseModel):
    active: bool
    reason: Optional[str] = None

class ConversionRequest(BaseModel):
    value: float
    redirect_id: Optional[str] = None
    source: Optional[str] = "webhook"
    currency: Optional[str] = "USD"
    metadata: Optional[Dict[str, Any]] = None

class DecisionRequest(BaseModel):
    approve: bool

class TokenRequest(BaseModel):
    admin_token: str

class OperatorCommandRequest(BaseModel):
    command: str

class IdeaIntakeRequest(BaseModel):
    text: str
    refine: bool = True

class LaneRequest(BaseModel):
    name: str
    platform: str = "x"
    identity_type: str = "brand_account"
    purpose: str = ""
    audience: str = ""
    language: str = "en"
    cultural_context: str = ""
    allowed_topics: List[str] = []
    forbidden_topics: List[str] = []

class ValidationResultRequest(BaseModel):
    opportunity_packet_id: str
    venture_assessment_id: str = ""
    experiment_ref: str = ""
    capability_grant_id: str = ""
    account_lane_id: str = ""
    validation_type: str = "content_probe"
    hypothesis: str = ""
    intervention: str = ""
    observation_window_start: str = ""
    observation_window_end: str = ""
    success_threshold: str = ""
    failure_threshold: str = ""
    measured_outcomes: Dict[str, Any] = {}
    raw_evidence_refs: List[str] = []
    evidence_tier: str = "observation"
    evidence_quality: float = 0.0
    confounders: List[str] = []
    result_classification: str = "inconclusive"
    causal_note: str = ""
    economic_result: str = ""
    trust_result: str = ""
    next_decision: str = ""
    trace_id: str = ""
    metadata: Dict[str, Any] = {}

class OpportunityCreateRequest(BaseModel):
    signal_type: str = "operator_thought"
    source: str = "operator"
    source_ref: str = ""
    observed_pain: str
    core_thesis: str
    audience: str = ""
    cultural_context: str = ""
    language: str = "en"
    customer_segment: str = ""
    buyer_type: str = ""
    urgency: str = "medium"
    evidence: List[str] = []
    possible_offer: str = ""
    monetization_paths: List[str] = []
    risk_flags: List[str] = []
    smallest_validation_action: str = ""
    confidence: float = 0.5

# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_connections.append(websocket)
    logger.info("WebSocket connection established")
    
    try:
        while True:
            # Keep connection alive
            await asyncio.sleep(30)
            # Use send_ping for WebSocket keep-alive
            try:
                await websocket.send_text("ping")
            except Exception:
                # On send failure, remove connection and stop pinging
                if websocket in websocket_connections:
                    websocket_connections.remove(websocket)
                try:
                    await websocket.close()
                except Exception:
                    pass
                break
    except WebSocketDisconnect:
        websocket_connections.remove(websocket)
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get(config.REQUEST_ID_HEADER, str(uuid.uuid4()))
    request.state.request_id = request_id
    start = request_timer()
    try:
        response = await call_next(request)
    except HTTPException as exc:
        response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "request_id": request_id})
    except Exception as exc:
        logger.error("Unhandled application error", extra_data={"error": str(exc), "path": request.url.path})
        response = JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error", "request_id": request_id})

    duration = elapsed(start)
    ctx: Optional[RequestContext] = getattr(request.state, "request_context", None)
    role = ctx.roles[0] if ctx else "anonymous"
    record_request_metrics(request, response.status_code, duration, role)
    response.headers[config.REQUEST_ID_HEADER] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "request_id": request_id},
    )

# Broadcast updates to all connected clients
async def broadcast_update(data: Dict[str, Any]):
    if not websocket_connections:
        return
    
    disconnected = []
    for websocket in websocket_connections:
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"Failed to send WebSocket update: {e}")
            disconnected.append(websocket)
    
    # Remove disconnected clients
    for ws in disconnected:
        websocket_connections.remove(ws)

# Dashboard API endpoints
@app.get("/api/dashboard")
@app.get("/dashboard")  # Support both routes
async def get_dashboard(_: RequestContext = Depends(get_request_context)):
    """Get dashboard overview data"""
    try:
        with get_db_session() as session:
            # Get latest KPIs
            kpis = kpi_service.get_latest_kpis(session)
            
            # Get recent activity
            recent_actions = (
                session.query(Action)
                .order_by(lambda action: action.created_at, descending=True)
                .limit(10)
                .all()
            )
            
            # Get system status
            status = {
                "api_health": "healthy" if x_client and x_client.is_healthy() else "degraded",
                "rate_limits": "good",
                "ethics_guard": "active",
                "memory_usage": "67.2 MB",
                "uptime": runner.get_uptime() if hasattr(runner, 'get_uptime') else "Unknown",
                "live_mode": config.LIVE,
                "crisis_state": "PAUSED" if runner.crisis_service.is_paused() else "NORMAL",
                "crisis_reason": runner.crisis_service.reason,
            }
            
            # Get persona preview
            persona_preview = persona_store.get_current_persona()
            
            return {
                "kpis": kpis,
                "recent_activity": [
                    {
                        "id": action.id,
                        "kind": action.kind,
                        "meta": action.meta_json,
                        "created_at": action.created_at.isoformat()
                    } for action in recent_actions
                ],
                "system_status": status,
                "persona_preview": persona_preview,
                "goal_mode": config.GOAL_MODE
            }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/crisis")
async def set_crisis(request: CrisisRequest):
    """Toggle crisis mode manually from the dashboard."""
    if request.active:
        runner.crisis_service.activate(reason=request.reason or "manual_toggle")
    else:
        runner.crisis_service.resolve(reason=request.reason or "manual_clear")

    return {
        "crisis_state": "PAUSED" if runner.crisis_service.is_paused() else "NORMAL",
        "crisis_reason": runner.crisis_service.reason,
    }

@app.post("/api/auth/token")
async def issue_admin_token(request: TokenRequest):
    """Exchange the ADMIN_TOKEN for a short-lived admin JWT.

    This is what lets the dashboard perform admin actions (approvals,
    breaker reset, persona updates) without shipping the raw admin token
    on every request.
    """
    import jwt as pyjwt

    if not secrets.compare_digest(request.admin_token, config.ADMIN_TOKEN):
        logger.warning("Admin token exchange failed: invalid token")
        raise HTTPException(status_code=401, detail="Invalid admin token")

    now = datetime.now(UTC)
    expires_hours = 12
    claims: Dict[str, Any] = {
        "sub": "admin",
        "roles": ["admin"],
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
    }
    if config.JWT_ISSUER:
        claims["iss"] = config.JWT_ISSUER
    if config.JWT_AUDIENCE:
        claims["aud"] = config.JWT_AUDIENCE

    token = pyjwt.encode(claims, config.JWT_SECRET, algorithm="HS256")
    get_ledger().record("admin_token_issued", {"expires_hours": expires_hours})
    return {"token": token, "expires_in": expires_hours * 3600}


async def _arming_preflight() -> Dict[str, Any]:
    """Checks that must pass before live posting can be armed.

    Disarming is always unconditional; only the arm direction is gated.
    """
    chain_ok, bad_seq = get_ledger().verify_chain()
    breaker_clear = not runner.heartbeat.breaker_tripped
    credentials_ok = await x_client.verify_credentials()

    checks = {
        "ledger_chain": chain_ok,
        "breaker_clear": breaker_clear,
        "x_credentials": credentials_ok,
    }
    if not chain_ok:
        checks["ledger_chain_broken_at"] = bad_seq
    return {"passed": all(v for k, v in checks.items() if isinstance(v, bool)), "checks": checks}


@app.post("/api/toggle")
async def toggle_live_mode(request: ToggleRequest):
    """Toggle LIVE mode. Arming requires a preflight; disarming never does."""
    try:
        if request.live:
            preflight = await _arming_preflight()
            if not preflight["passed"]:
                get_ledger().record("arm_refused", {"checks": preflight["checks"]})
                logger.warning(f"Arming refused by preflight: {preflight['checks']}")
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Arming refused by preflight checks",
                        "checks": preflight["checks"],
                    },
                )
            get_kill_switch().set_armed(True, reason="manual_arm")
            get_ledger().record("armed", {"checks": preflight["checks"]})
        else:
            get_kill_switch().set_armed(False, reason="manual_disarm")

        # Broadcast update to clients
        await broadcast_update({
            "type": "live_mode_changed",
            "live": config.LIVE
        })

        logger.info(f"LIVE mode {'activated' if config.LIVE else 'paused'}")
        return {"live": config.LIVE}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Toggle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/breaker/reset")
async def reset_heartbeat_breaker(_: RequestContext = Depends(require_role("admin"))):
    """Clear the heartbeat breaker after a trip. Does NOT re-arm live mode."""
    runner.heartbeat.reset_breaker()
    return {
        "breaker_tripped": runner.heartbeat.breaker_tripped,
        "live": config.LIVE,
    }

@app.post("/api/mode")
async def set_goal_mode(request: ModeRequest):
    """Set goal mode (FAME/MONETIZE)"""
    try:
        if request.mode not in ["FAME", "MONETIZE"]:
            raise HTTPException(status_code=400, detail="Invalid mode")
        
        update_config(GOAL_MODE=request.mode)
        optimizer.update_goal_weights(request.mode)
        
        await broadcast_update({
            "type": "goal_mode_changed",
            "mode": config.GOAL_MODE
        })
        
        logger.info(f"Goal mode set to {config.GOAL_MODE}")
        return {"mode": config.GOAL_MODE}
    except Exception as e:
        logger.error(f"Mode change error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/propose")
async def trigger_proposal():
    """Trigger immediate proposal generation"""
    try:
        if not config.LIVE:
            raise HTTPException(status_code=400, detail="System not in LIVE mode")
        
        # Trigger proposal generation via selector
        action = await selector.get_next_action()
        if action.get("type") == "POST_PROPOSAL":
            result = await generator.make_proposal(action.get("topic", "general"))
            
            await broadcast_update({
                "type": "proposal_generated",
                "proposal": result
            })
            
            return {"success": True, "proposal": result}
        else:
            return {"success": False, "reason": "Not appropriate time for proposal"}
    except Exception as e:
        logger.error(f"Proposal generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/note")
async def add_note(request: NoteRequest):
    """Add improvement note"""
    try:
        with get_db_session() as session:
            note = Note(text=request.text)
            session.add(note)
            session.commit()
            
            await broadcast_update({
                "type": "note_added",
                "note": {
                    "id": note.id,
                    "text": note.text,
                    "created_at": note.created_at.isoformat()
                }
            })
            
            return {"success": True, "note_id": note.id}
    except Exception as e:
        logger.error(f"Note creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/redirect")
async def create_redirect(request: RedirectRequest):
    """Create tracked redirect link"""
    try:
        with get_db_session() as session:
            redirect = Redirect(
                label=request.label,
                target_url=request.target_url,
                utm=request.utm
            )
            session.add(redirect)
            session.commit()
            
            return {
                "id": redirect.id,
                "url": f"/r/{redirect.id}",
                "label": redirect.label
            }
    except Exception as e:
        logger.error(f"Redirect creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/conversions")
async def record_conversion(
    request: ConversionRequest,
    _: RequestContext = Depends(require_any_role(["admin", "service"])),
):
    """Record a real revenue event (e.g. from a payment provider webhook)."""
    try:
        conversion = Conversion(
            redirect_id=request.redirect_id,
            value=float(request.value),
            currency=request.currency or "USD",
            source=request.source or "webhook",
            metadata=request.metadata or {},
        )
        with get_db_session() as session:
            session.add(conversion)
            session.commit()

        get_ledger().record("revenue_event", {
            "conversion_id": conversion.id,
            "value": conversion.value,
            "currency": conversion.currency,
            "redirect_id": conversion.redirect_id,
            "source": conversion.source,
        })
        return {"success": True, "id": conversion.id}
    except Exception as e:
        logger.error(f"Conversion recording error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversions")
async def list_conversions(limit: int = 50, _: RequestContext = Depends(get_request_context)):
    """List recorded revenue events, newest first."""
    try:
        with get_db_session() as session:
            conversions = (
                session.query(Conversion)
                .order_by(lambda c: c.occurred_at, descending=True)
                .limit(limit)
                .all()
            )
            return {
                "count": len(conversions),
                "conversions": [
                    {
                        "id": c.id,
                        "value": c.value,
                        "currency": c.currency,
                        "source": c.source,
                        "redirect_id": c.redirect_id,
                        "occurred_at": c.occurred_at.isoformat(),
                    }
                    for c in conversions
                ],
            }
    except Exception as e:
        logger.error(f"Conversion list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discoveries")
async def list_discoveries(status_filter: str = "pending", _: RequestContext = Depends(get_request_context)):
    """List discovery proposals (new voices/keywords) awaiting review."""
    try:
        with get_db_session() as session:
            proposals = (
                session.query(DiscoveryProposal)
                .filter(lambda p: p.status == status_filter)
                .order_by(lambda p: p.created_at, descending=True)
                .all()
            )
            return {
                "count": len(proposals),
                "proposals": [
                    {
                        "id": p.id,
                        "kind": p.kind,
                        "value": p.value,
                        "evidence": p.evidence,
                        "status": p.status,
                        "created_at": p.created_at.isoformat(),
                    }
                    for p in proposals
                ],
            }
    except Exception as e:
        logger.error(f"Discovery list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/discoveries/{proposal_id}/decision")
async def decide_discovery(
    proposal_id: str,
    request: DecisionRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Approve or reject a discovery proposal. Only approval widens perception."""
    try:
        with get_db_session() as session:
            proposal = (
                session.query(DiscoveryProposal)
                .filter(lambda p: p.id == proposal_id)
                .first()
            )
            if proposal is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            if proposal.status != "pending":
                raise HTTPException(status_code=409, detail=f"Proposal already {proposal.status}")

            proposal.status = "approved" if request.approve else "rejected"
            proposal.decided_at = datetime.now(UTC)
            proposal.actor = "admin"
            session.commit()

        get_ledger().record("discovery_decision", {
            "id": proposal.id,
            "kind": proposal.kind,
            "value": proposal.value,
            "decision": proposal.status,
        })
        return {"success": True, "status": proposal.status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Discovery decision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/goals/proposals")
async def list_goal_proposals(status_filter: str = "pending", _: RequestContext = Depends(get_request_context)):
    """List proposed OKR changes awaiting human review."""
    try:
        with get_db_session() as session:
            proposals = (
                session.query(GoalProposal)
                .filter(lambda p: p.status == status_filter)
                .order_by(lambda p: p.created_at, descending=True)
                .all()
            )
            return {
                "count": len(proposals),
                "proposals": [
                    {
                        "id": p.id,
                        "proposal": p.proposal,
                        "rationale": p.rationale,
                        "status": p.status,
                        "created_at": p.created_at.isoformat(),
                    }
                    for p in proposals
                ],
            }
    except Exception as e:
        logger.error(f"Goal proposal list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/goals/proposals/{proposal_id}/decision")
async def decide_goal_proposal(
    proposal_id: str,
    request: DecisionRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Approve or reject a proposed OKR change. Approved proposals become
    the active OKR at the next planning cycle."""
    try:
        with get_db_session() as session:
            proposal = (
                session.query(GoalProposal)
                .filter(lambda p: p.id == proposal_id)
                .first()
            )
            if proposal is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            if proposal.status != "pending":
                raise HTTPException(status_code=409, detail=f"Proposal already {proposal.status}")

            proposal.status = "approved" if request.approve else "rejected"
            proposal.decided_at = datetime.now(UTC)
            proposal.actor = "admin"
            session.commit()

        get_ledger().record("okr_decision", {
            "id": proposal.id,
            "decision": proposal.status,
            "proposal": proposal.proposal,
        })
        return {"success": True, "status": proposal.status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Goal proposal decision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/operator/requests")
async def list_operator_requests(status_filter: str = "pending", _: RequestContext = Depends(get_request_context)):
    """The operator's approval inbox: ranked (P1 first, then oldest),
    capped so founder attention is a protected resource, expiring so
    silence never becomes consent. Overflow is batched, never approved."""
    try:
        max_active = int(os.getenv("MAX_ACTIVE_APPROVALS", "10"))
        with get_db_session() as session:
            get_operator_line().sweep_expired(session)
            requests = (
                session.query(ApprovalRequest)
                .filter(lambda r: r.status == status_filter)
                .all()
            )
            # Rank: urgent first, then oldest waiting.
            requests.sort(key=lambda r: (r.priority != "P1", r.created_at))
            active = requests[:max_active] if status_filter == "pending" else requests
            batched = len(requests) - len(active)

            # Approval-fatigue metric: median decision latency (seconds).
            decided = [
                r for r in session.query(ApprovalRequest).all()
                if r.decided_at is not None and r.decided_via != "expiry"
            ]
            latencies = sorted(
                (r.decided_at - r.created_at).total_seconds() for r in decided
            )
            median_latency = latencies[len(latencies) // 2] if latencies else None

            return {
                "count": len(active),
                "batched_count": batched,
                "max_active": max_active,
                "median_decision_latency_seconds": median_latency,
                "requests": [
                    {
                        "id": r.id,
                        "code": r.code,
                        "kind": r.kind,
                        "priority": r.priority,
                        "summary": r.summary,
                        "rationale": r.rationale,
                        "strongest_objection": r.strongest_objection,
                        "payload": r.payload,
                        "status": r.status,
                        "created_at": r.created_at.isoformat(),
                        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    }
                    for r in active
                ],
            }
    except Exception as e:
        logger.error(f"Operator request list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/operator/command")
async def operator_command(
    request: OperatorCommandRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Run an operator command (YES/NO/EDIT/WHY/HOLD/FREEZE/NEWS/INTERVIEW/
    OPINION) from the dashboard."""
    try:
        with get_db_session() as session:
            result = get_operator_line().handle_command(session, request.command, via="dashboard")
        return result
    except Exception as e:
        logger.error(f"Operator command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/operator/sms")
async def operator_sms_webhook(request: Request):
    """Twilio inbound-SMS webhook. Only signed requests from the configured
    operator phone are honored; everything else is rejected before parsing
    reaches any agent logic."""
    from urllib.parse import parse_qs

    raw = (await request.body()).decode("utf-8", errors="replace")
    params = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    url = os.getenv("TWILIO_WEBHOOK_URL") or str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    if not validate_twilio_signature(url, params, signature):
        logger.warning("Rejected SMS webhook: bad Twilio signature")
        get_ledger().record("operator_sms_rejected", {"reason": "bad_signature"})
        raise HTTPException(status_code=403, detail="Invalid signature")

    operator_phone = os.getenv("OPERATOR_PHONE", "")
    if not operator_phone or params.get("From") != operator_phone:
        logger.warning("Rejected SMS webhook: sender is not the operator")
        get_ledger().record("operator_sms_rejected", {"reason": "unknown_sender"})
        raise HTTPException(status_code=403, detail="Unknown sender")

    with get_db_session() as session:
        result = get_operator_line().handle_command(session, params.get("Body", ""), via="sms")

    from fastapi.responses import Response as PlainResponse
    from xml.sax.saxutils import escape

    twiml = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{escape(result['reply'])}</Message></Response>"
    return PlainResponse(content=twiml, media_type="application/xml")


# --------------------------------------------------------------------- #
# Idea refinery + venture cockpit (drafts only; approvals gate the world)
# --------------------------------------------------------------------- #
@app.post("/api/ideas/intake")
async def intake_idea(request: IdeaIntakeRequest, _: RequestContext = Depends(require_role("admin"))):
    """Accept a raw operator thought; optionally refine it immediately."""
    try:
        with get_db_session() as session:
            idea = idea_refinery.intake(session, request.text)
            result: Dict[str, Any] = {"idea_id": idea.id, "risk_flags": idea.risk_flags}
            if request.refine:
                refined = await idea_refinery.refine(session, idea)
                result.update({
                    "thesis": refined["thesis"],
                    "audiences": refined["audiences"],
                    "draft_ids": [d.id for d in refined["drafts"]],
                    "opportunity_id": refined["opportunity"].id if refined["opportunity"] else None,
                })
        return result
    except Exception as e:
        logger.error(f"Idea intake error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ideas")
async def list_ideas(_: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        ideas = session.query(Idea).order_by(lambda i: i.created_at, descending=True).all()
        return {"count": len(ideas), "ideas": [{
            "id": i.id, "raw_text": i.raw_text, "thesis": i.thesis,
            "audiences": i.audiences, "status": i.status,
            "risk_flags": i.risk_flags, "created_at": i.created_at.isoformat(),
        } for i in ideas]}


@app.post("/api/ideas/{idea_id}/refine")
async def refine_idea(idea_id: str, _: RequestContext = Depends(require_role("admin"))):
    try:
        with get_db_session() as session:
            idea = session.query(Idea).filter(lambda i: i.id == idea_id).first()
            if idea is None:
                raise HTTPException(status_code=404, detail="Idea not found")
            refined = await idea_refinery.refine(session, idea)
        return {
            "thesis": refined["thesis"],
            "audiences": refined["audiences"],
            "draft_ids": [d.id for d in refined["drafts"]],
            "opportunity_id": refined["opportunity"].id if refined["opportunity"] else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Idea refine error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/opportunities")
async def create_opportunity(
    request: OpportunityCreateRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Create an OpportunityPacket directly (operator-observed signals that
    didn't come through the idea refinery). Packets start pending — nothing
    is evaluated or sent anywhere without an explicit approve + send."""
    from services.prompt_firewall import get_firewall
    from services.venture_protocol import ALLOWED_SIGNAL_TYPES

    if request.signal_type not in ALLOWED_SIGNAL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"signal_type must be one of {sorted(ALLOWED_SIGNAL_TYPES)}",
        )
    if request.urgency not in ("low", "medium", "high"):
        raise HTTPException(status_code=422, detail="urgency must be low|medium|high")
    if not (0.0 <= request.confidence <= 1.0):
        raise HTTPException(status_code=422, detail="confidence must be within [0, 1]")

    firewall = get_firewall()
    with get_db_session() as session:
        packet = OpportunityPacket(
            source=request.source,
            source_ref=request.source_ref,
            signal_type=request.signal_type,
            observed_pain=firewall.sanitize(request.observed_pain).strip(),
            core_thesis=firewall.sanitize(request.core_thesis).strip(),
            audience=request.audience,
            cultural_context=request.cultural_context,
            language=request.language,
            customer_segment=request.customer_segment,
            buyer_type=request.buyer_type,
            urgency=request.urgency,
            evidence=[firewall.sanitize(e).strip() for e in request.evidence],
            possible_offer=request.possible_offer,
            monetization_paths=request.monetization_paths,
            risk_flags=request.risk_flags,
            smallest_validation_action=request.smallest_validation_action,
            confidence=request.confidence,
        )
        session.add(packet)
        session.commit()
    get_ledger().record("opportunity_created", {
        "id": packet.id, "signal_type": packet.signal_type, "via": "api",
    })
    return {"success": True, "id": packet.id, "status": packet.status}


@app.get("/api/opportunities")
async def list_opportunities(status_filter: str = "", _: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        packets = (
            session.query(OpportunityPacket)
            .filter(lambda p: not status_filter or p.status == status_filter)
            .order_by(lambda p: p.created_at, descending=True)
            .all()
        )
        from services.venture_protocol import packet_to_wire
        return {"count": len(packets), "opportunities": [packet_to_wire(p) for p in packets]}


@app.post("/api/opportunities/{packet_id}/decision")
async def decide_opportunity(
    packet_id: str, request: DecisionRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Approve or reject an OpportunityPacket. Only approved packets may be
    sent for venture evaluation."""
    try:
        with get_db_session() as session:
            packet = session.query(OpportunityPacket).filter(lambda p: p.id == packet_id).first()
            if packet is None:
                raise HTTPException(status_code=404, detail="Opportunity not found")
            if packet.status != "pending":
                raise HTTPException(status_code=409, detail=f"Opportunity already {packet.status}")
            packet.status = "approved" if request.approve else "rejected"
            session.commit()
        get_ledger().record("opportunity_decision", {"id": packet_id, "decision": packet.status})
        return {"success": True, "status": packet.status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Opportunity decision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/opportunities/{packet_id}/send-to-wealthmachine")
async def send_to_wealthmachine(packet_id: str, _: RequestContext = Depends(require_role("admin"))):
    """Send an APPROVED packet for evaluation; store the assessment and
    convert it into reviewable drafts + an approval request."""
    try:
        with get_db_session() as session:
            packet = session.query(OpportunityPacket).filter(lambda p: p.id == packet_id).first()
            if packet is None:
                raise HTTPException(status_code=404, detail="Opportunity not found")
            if packet.status != "approved":
                raise HTTPException(
                    status_code=409,
                    detail=f"Opportunity is '{packet.status}' — approve it before sending",
                )
            client = get_wealthmachine_client()
            assessment = client.evaluate(packet)
            session.add(assessment)
            packet.status = "assessed"
            actions = client.assessment_to_actions(session, assessment, packet, get_operator_line())
        from services.venture_protocol import assessment_to_wire
        return {
            "assessment": assessment_to_wire(assessment),
            "mode": client.mode,
            "draft_ids": [actions[k].id for k in ("landing_page", "interview_script", "outreach_draft")],
            "approval_request_id": actions["approval_request"].id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WealthMachine send error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/wealthmachine/assessments/receive")
async def receive_assessment(
    payload: Dict[str, Any],
    _: RequestContext = Depends(require_any_role(["admin", "service"])),
):
    """Inbound VentureAssessment push (validated wire contract)."""
    try:
        validate_assessment_wire(payload)
        with get_db_session() as session:
            packet = session.query(OpportunityPacket).filter(
                lambda p: p.id == payload["opportunity_packet_id"]
            ).first()
            if packet is None:
                raise HTTPException(status_code=404, detail="Unknown opportunity_packet_id")
            assessment = VentureAssessment(
                opportunity_packet_id=payload["opportunity_packet_id"],
                go_no_go=payload["go_no_go"],
                opportunity_score=float(payload.get("opportunity_score") or 0.0),
                risk_level=str(payload.get("risk_level") or "medium"),
                legal_readiness=str(payload.get("legal_readiness") or "unreviewed"),
                pricing_hypothesis=str(payload.get("pricing_hypothesis") or ""),
                validation_plan=list(payload.get("validation_plan") or []),
                recommended_next_action=str(payload.get("recommended_next_action") or ""),
                requires_human_approval=True,
                reasons=list(payload.get("reasons") or []),
                cases=list(payload.get("cases") or []),
            )
            session.add(assessment)
            packet.status = "assessed"
            actions = get_wealthmachine_client().assessment_to_actions(
                session, assessment, packet, get_operator_line()
            )
        get_ledger().record("venture_assessment", {
            "packet_id": packet.id, "go_no_go": assessment.go_no_go, "mode": "push",
        })
        return {"success": True, "assessment_id": assessment.id,
                "approval_request_id": actions["approval_request"].id}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Assessment receive error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/assessments")
async def list_assessments(_: RequestContext = Depends(get_request_context)):
    """VentureAssessments stored so far (mock or real engine — same contract)."""
    with get_db_session() as session:
        assessments = (
            session.query(VentureAssessment)
            .order_by(lambda a: a.created_at, descending=True)
            .all()
        )
        from services.venture_protocol import assessment_to_wire
        return {"count": len(assessments),
                "assessments": [assessment_to_wire(a) for a in assessments]}


class WorkCheckRequest(BaseModel):
    category: str
    description: str = ""


@app.post("/api/policy/work-check")
async def check_work_policy(
    request: WorkCheckRequest, _: RequestContext = Depends(get_request_context)
):
    """The anti-cathedral rule, executable: may this work proceed given the
    state of the external-evidence window? Decisions are ledgered."""
    from services.evidence_policy import evaluate_work
    with get_db_session() as session:
        return evaluate_work(session, request.category, description=request.description)


@app.get("/api/metrics/institutional")
async def get_institutional_metrics(
    base_j: Optional[float] = None, _: RequestContext = Depends(get_request_context)
):
    """The numbers the institution grows by: constitutional health,
    evidence window, loop closure, negative-result retention, founder
    decision load — and Evidence-Weighted J when a base J is supplied."""
    from services.evidence_policy import institutional_metrics
    with get_db_session() as session:
        return institutional_metrics(session, base_j=base_j)


class CapabilityGrantRequest(BaseModel):
    approval_request_id: str
    action_type: str
    exact_action: str
    resource: str
    account_lane_id: str = ""
    named_targets: List[str] = []
    max_cost: float = 0.0
    maximum_uses: int = 1
    ttl_hours: Optional[int] = None
    evidence_refs: List[str] = []
    rollback_note: str = ""
    trace_id: str = ""

class GrantRevokeRequest(BaseModel):
    reason: str = ""


def _grant_to_dict(g: CapabilityGrant) -> Dict[str, Any]:
    return {
        "id": g.id, "approval_request_id": g.approval_request_id,
        "requester_identity": g.requester_identity,
        "approver_identity": g.approver_identity,
        "action_type": g.action_type, "exact_action": g.exact_action,
        "resource": g.resource, "account_lane_id": g.account_lane_id,
        "named_targets": g.named_targets, "max_cost": g.max_cost,
        "currency": g.currency, "maximum_uses": g.maximum_uses,
        "uses_consumed": g.uses_consumed,
        "issued_at": g.issued_at.isoformat(),
        "expires_at": g.expires_at.isoformat() if g.expires_at else None,
        "risk_tier": g.risk_tier, "rollback_note": g.rollback_note,
        "revocation_status": g.revocation_status,
        "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None,
        "revocation_reason": g.revocation_reason,
        "trace_id": g.trace_id,
    }


@app.post("/api/capability-grants")
async def create_capability_grant(
    request: CapabilityGrantRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Mint a single-purpose, expiring capability from an APPROVED request.
    Grants never widen standing autonomy: exact action, exact resource,
    bounded uses, bounded window. Everything is ledgered."""
    from services.capability import CapabilityError, get_capability_service
    try:
        with get_db_session() as session:
            grant = get_capability_service().mint_from_approval(
                session,
                request.approval_request_id,
                request.action_type,
                request.exact_action,
                request.resource,
                account_lane_id=request.account_lane_id,
                named_targets=request.named_targets,
                max_cost=request.max_cost,
                maximum_uses=request.maximum_uses,
                ttl_hours=request.ttl_hours,
                evidence_refs=request.evidence_refs,
                rollback_note=request.rollback_note,
                trace_id=request.trace_id,
            )
        return {"success": True, "grant": _grant_to_dict(grant)}
    except CapabilityError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/capability-grants")
async def list_capability_grants(_: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        grants = (
            session.query(CapabilityGrant)
            .order_by(lambda g: g.issued_at, descending=True)
            .all()
        )
        return {"count": len(grants), "grants": [_grant_to_dict(g) for g in grants]}


@app.get("/api/capability-grants/{grant_id}")
async def get_capability_grant(grant_id: str, _: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        grant = session.query(CapabilityGrant).filter(lambda g: g.id == grant_id).first()
        if grant is None:
            raise HTTPException(status_code=404, detail="Grant not found")
        return _grant_to_dict(grant)


@app.post("/api/capability-grants/{grant_id}/revoke")
async def revoke_capability_grant(
    grant_id: str,
    request: GrantRevokeRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Revocation is immediate. Revoked grants fail closed at execution."""
    from services.capability import CapabilityError, get_capability_service
    try:
        with get_db_session() as session:
            grant = get_capability_service().revoke(
                session, grant_id, reason=request.reason,
            )
        return {"success": True, "grant": _grant_to_dict(grant)}
    except CapabilityError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/validation-results")
async def record_validation_result(
    request: ValidationResultRequest,
    context: RequestContext = Depends(require_role("admin")),
):
    """Record what the world said. The terminal object of the loop: only
    externally observed outcomes become institutional truth, and they are
    ledgered before anything treats them as such. Negative results are
    first-class — zero response is a completed observation."""
    from services.prompt_firewall import get_firewall
    from services.venture_protocol import (
        ALLOWED_EVIDENCE_TIERS, ALLOWED_RESULT_CLASSIFICATIONS,
    )

    if request.result_classification not in ALLOWED_RESULT_CLASSIFICATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"result_classification must be one of {sorted(ALLOWED_RESULT_CLASSIFICATIONS)}",
        )
    if request.evidence_tier not in ALLOWED_EVIDENCE_TIERS:
        raise HTTPException(
            status_code=422,
            detail=f"evidence_tier must be one of {sorted(ALLOWED_EVIDENCE_TIERS)}",
        )
    if not (0.0 <= request.evidence_quality <= 1.0):
        raise HTTPException(status_code=422, detail="evidence_quality must be within [0, 1]")

    firewall = get_firewall()
    with get_db_session() as session:
        packet = session.query(OpportunityPacket).filter(
            lambda p: p.id == request.opportunity_packet_id
        ).first()
        if packet is None:
            raise HTTPException(status_code=422, detail="Unknown opportunity_packet_id")
        if request.venture_assessment_id:
            assessment = session.query(VentureAssessment).filter(
                lambda a: a.id == request.venture_assessment_id
            ).first()
            if assessment is None:
                raise HTTPException(status_code=422, detail="Unknown venture_assessment_id")

        result = ValidationResult(
            opportunity_packet_id=request.opportunity_packet_id,
            venture_assessment_id=request.venture_assessment_id,
            experiment_ref=request.experiment_ref,
            capability_grant_id=request.capability_grant_id,
            account_lane_id=request.account_lane_id,
            validation_type=request.validation_type,
            hypothesis=firewall.sanitize(request.hypothesis).strip(),
            intervention=firewall.sanitize(request.intervention).strip(),
            observation_window_start=request.observation_window_start,
            observation_window_end=request.observation_window_end,
            success_threshold=request.success_threshold,
            failure_threshold=request.failure_threshold,
            measured_outcomes=request.measured_outcomes,
            raw_evidence_refs=[firewall.sanitize(r).strip() for r in request.raw_evidence_refs],
            evidence_tier=request.evidence_tier,
            evidence_quality=request.evidence_quality,
            confounders=[firewall.sanitize(c).strip() for c in request.confounders],
            result_classification=request.result_classification,
            causal_note=firewall.sanitize(request.causal_note).strip(),
            economic_result=request.economic_result,
            trust_result=request.trust_result,
            next_decision=firewall.sanitize(request.next_decision).strip(),
            recorded_by=getattr(context, "subject", "") or "admin",
            trace_id=request.trace_id,
            metadata=request.metadata,
        )
        session.add(result)
        session.commit()
    # Ledgered before it is treated as institutional truth.
    get_ledger().record("validation_result_recorded", {
        "id": result.id,
        "opportunity_packet_id": result.opportunity_packet_id,
        "result_classification": result.result_classification,
        "evidence_tier": result.evidence_tier,
        "evidence_quality": result.evidence_quality,
    })
    return {"success": True, "id": result.id,
            "result_classification": result.result_classification}


def _validation_result_to_dict(r: ValidationResult) -> Dict[str, Any]:
    return {
        "id": r.id, "schema_version": r.schema_version,
        "opportunity_packet_id": r.opportunity_packet_id,
        "venture_assessment_id": r.venture_assessment_id,
        "experiment_ref": r.experiment_ref,
        "capability_grant_id": r.capability_grant_id,
        "account_lane_id": r.account_lane_id,
        "validation_type": r.validation_type,
        "hypothesis": r.hypothesis, "intervention": r.intervention,
        "observation_window_start": r.observation_window_start,
        "observation_window_end": r.observation_window_end,
        "success_threshold": r.success_threshold,
        "failure_threshold": r.failure_threshold,
        "measured_outcomes": r.measured_outcomes,
        "raw_evidence_refs": r.raw_evidence_refs,
        "evidence_tier": r.evidence_tier,
        "evidence_quality": r.evidence_quality,
        "confounders": r.confounders,
        "result_classification": r.result_classification,
        "causal_note": r.causal_note,
        "economic_result": r.economic_result,
        "trust_result": r.trust_result,
        "next_decision": r.next_decision,
        "recorded_by": r.recorded_by, "trace_id": r.trace_id,
        "created_at": r.created_at.isoformat(),
    }


@app.get("/api/validation-results")
async def list_validation_results(_: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        results = (
            session.query(ValidationResult)
            .order_by(lambda r: r.created_at, descending=True)
            .all()
        )
        return {"count": len(results),
                "results": [_validation_result_to_dict(r) for r in results]}


@app.get("/api/validation-results/{result_id}")
async def get_validation_result(result_id: str, _: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        result = session.query(ValidationResult).filter(lambda r: r.id == result_id).first()
        if result is None:
            raise HTTPException(status_code=404, detail="ValidationResult not found")
        return _validation_result_to_dict(result)


@app.get("/api/decision-episodes")
async def list_decision_episodes(_: RequestContext = Depends(get_request_context)):
    """The decision corpus, episode by episode. Killed, deferred, and
    negative-outcome episodes are included; missing stages are explicit."""
    from services.decision_episode import list_episodes
    with get_db_session() as session:
        episodes = list_episodes(session)
        closed = sum(1 for e in episodes if e["loop_closed"])
        return {
            "count": len(episodes), "closed": closed,
            "loop_closure_rate": (closed / len(episodes)) if episodes else 0.0,
            "episodes": episodes,
        }


@app.get("/api/decision-episodes/{episode_id}")
async def get_decision_episode(episode_id: str, _: RequestContext = Depends(get_request_context)):
    from services.decision_episode import build_episode
    with get_db_session() as session:
        episode = build_episode(session, episode_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        return episode


@app.get("/api/media/drafts")
async def list_media_drafts(status_filter: str = "pending", _: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        drafts = (
            session.query(MediaAssetDraft)
            .filter(lambda d: d.approval_status == status_filter)
            .order_by(lambda d: d.created_at, descending=True)
            .all()
        )
        return {"count": len(drafts), "drafts": [{
            "id": d.id, "format": d.format, "platform": d.platform,
            "language": d.language, "account_lane": d.account_lane,
            "cultural_context": d.cultural_context, "title": d.title,
            "draft_text": d.draft_text, "script": d.script, "hook": d.hook,
            "cta": d.cta, "disclosure_needed": d.disclosure_needed,
            "risk_level": d.risk_level, "approval_status": d.approval_status,
            "created_at": d.created_at.isoformat(),
        } for d in drafts]}


@app.post("/api/media/drafts/{draft_id}/decision")
async def decide_media_draft(
    draft_id: str, request: DecisionRequest,
    _: RequestContext = Depends(require_role("admin")),
):
    """Approve/reject a draft. Approval marks it publishable — actual
    publishing still runs through the existing gated pipelines."""
    try:
        with get_db_session() as session:
            draft = session.query(MediaAssetDraft).filter(lambda d: d.id == draft_id).first()
            if draft is None:
                raise HTTPException(status_code=404, detail="Draft not found")
            if draft.approval_status != "pending":
                raise HTTPException(status_code=409, detail=f"Draft already {draft.approval_status}")
            draft.approval_status = "approved" if request.approve else "rejected"
            session.commit()
        get_ledger().record("media_draft_decision", {"id": draft_id, "decision": draft.approval_status})
        return {"success": True, "status": draft.approval_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Media draft decision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/lanes")
async def list_lanes(_: RequestContext = Depends(get_request_context)):
    with get_db_session() as session:
        lanes = session.query(AccountLane).all()
        return {"count": len(lanes), "policy": list(LANE_POLICY), "lanes": [{
            "id": lane.id, "name": lane.name, "platform": lane.platform,
            "identity_type": lane.identity_type, "purpose": lane.purpose,
            "audience": lane.audience, "language": lane.language,
            "cultural_context": lane.cultural_context,
            "allowed_topics": lane.allowed_topics,
            "forbidden_topics": lane.forbidden_topics,
            "approval_required": lane.approval_required, "active": lane.active,
        } for lane in lanes]}


@app.post("/api/lanes")
async def create_lane(request: LaneRequest, _: RequestContext = Depends(require_role("admin"))):
    """Create an account lane. Fake people, impersonation, and engagement
    manipulation identities are rejected — hard, not configurably."""
    try:
        validate_identity_type(request.identity_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    with get_db_session() as session:
        lane = AccountLane(
            name=request.name, platform=request.platform,
            identity_type=request.identity_type, purpose=request.purpose,
            audience=request.audience, language=request.language,
            cultural_context=request.cultural_context,
            allowed_topics=request.allowed_topics,
            forbidden_topics=request.forbidden_topics,
        )
        session.add(lane)
        session.commit()
    get_ledger().record("lane_created", {
        "id": lane.id, "name": lane.name, "identity_type": lane.identity_type,
    })
    return {"success": True, "id": lane.id}


@app.get("/r/{redirect_id}")
async def handle_redirect(redirect_id: str):
    """Handle redirect and track clicks"""
    try:
        with get_db_session() as session:
            redirect = (
                session.query(Redirect)
                .filter(lambda r: r.id == redirect_id)
                .first()
            )
            if not redirect:
                raise HTTPException(status_code=404, detail="Redirect not found")

            # Increment clicks
            redirect.clicks = (redirect.clicks or 0) + 1
            session.commit()
            get_ledger().record("link_click", {
                "redirect_id": redirect.id,
                "clicks": redirect.clicks,
            })
            
            return RedirectResponse(url=str(redirect.target_url), status_code=302)
    except Exception as e:
        logger.error(f"Redirect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Unauthenticated liveness probe. Deliberately minimal: a public
    health endpoint must never become a confirmation oracle for arming
    state, crisis posture, or successful ledger tampering."""
    return {"ok": True, "timestamp": datetime.now(UTC).isoformat()}


@app.get("/api/health/safety")
async def health_safety(_: RequestContext = Depends(require_role("admin"))):
    """Authenticated safe-runtime status: is the agent armed, is crisis
    pause active, is the decision ledger chain intact. Reads only. If a
    state can't be read, report the uncertainty rather than a false
    all-clear."""
    config = get_config()
    try:
        crisis_paused = bool(runner.crisis_service.is_paused())
        crisis_reason = runner.crisis_service.reason
    except Exception:
        crisis_paused, crisis_reason = None, "unavailable"
    try:
        ledger_ok, broken_at = get_ledger().verify_chain()
    except Exception:
        ledger_ok, broken_at = None, None
    return {
        "ok": True,
        "timestamp": datetime.now(UTC).isoformat(),
        "live": bool(config.LIVE),
        "crisis_paused": crisis_paused,
        "crisis_reason": crisis_reason,
        "ledger_ok": ledger_ok,
        "ledger_broken_at": broken_at,
    }

# Reflection / learned-mind endpoints
@app.get("/api/reflections")
async def get_reflections(limit: int = 20, _: RequestContext = Depends(get_request_context)):
    """Return the agent's most recent learned lessons (its evolving 'mind')."""
    try:
        with get_db_session() as session:
            lessons = reflection_service.get_recent_lessons(session, limit=limit)
            return {"count": len(lessons), "lessons": lessons}
    except Exception as e:
        logger.error(f"Get reflections error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reflect")
async def trigger_reflection(_: RequestContext = Depends(require_role("admin"))):
    """Run a deep reflection now and return the freshly generated lesson."""
    try:
        with get_db_session() as session:
            lesson = await reflection_service.generate_reflection_async(session)
        await broadcast_update({"type": "reflection", "lesson": lesson})
        return {"success": True, "lesson": lesson}
    except Exception as e:
        logger.error(f"Trigger reflection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Persona management endpoints
@app.get("/api/persona")
async def get_persona():
    """Get current persona"""
    try:
        return persona_store.get_current_persona()
    except Exception as e:
        logger.error(f"Persona get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/persona/versions")
async def get_persona_versions():
    """Get persona version history"""
    try:
        with get_db_session() as session:
            versions = (
                session.query(PersonaVersion)
                .order_by(lambda v: v.version, descending=True)
                .all()
            )
            return [
                {
                    "version": v.version,
                    "hash": v.hash,
                    "actor": v.actor,
                    "created_at": v.created_at.isoformat()
                } for v in versions
            ]
    except Exception as e:
        logger.error(f"Persona versions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/persona/preview")
async def preview_persona(request: PersonaUpdateRequest, _: RequestContext = Depends(require_role("admin"))):
    """Preview persona changes"""
    try:
        validated = persona_store.validate_persona(request.payload)
        preview = persona_store.build_system_prompt()
        return {
            "valid": True,
            "persona": validated,
            "system_prompt_preview": preview[:500] + "..." if len(preview) > 500 else preview
        }
    except ValidationError as e:
        return {"valid": False, "errors": e.errors()}
    except Exception as e:
        logger.error(f"Persona preview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/persona")
async def update_persona(request: PersonaUpdateRequest, _: RequestContext = Depends(require_role("admin"))):
    """Update persona with validation and versioning"""
    try:
        # Apply rate limiting
        if not admin_limiter.allow_request():
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # Validate and update
        new_version = persona_store.update_persona(request.payload, actor="admin")
        
        # Update self-model
        await self_model_service.update_self_model()
        
        await broadcast_update({
            "type": "persona_updated",
            "version": new_version
        })
        
        return {"success": True, "version": new_version}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail={"errors": e.errors()})
    except Exception as e:
        logger.error(f"Persona update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/persona/rollback/{version}")
async def rollback_persona(version: int, _: RequestContext = Depends(require_role("admin"))):
    """Rollback to previous persona version"""
    try:
        if not admin_limiter.allow_request():
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        new_version = persona_store.rollback_to_version(version, actor="admin")
        
        await broadcast_update({
            "type": "persona_rolled_back",
            "version": new_version,
            "rolled_back_to": version
        })
        
        return {"success": True, "version": new_version}
    except Exception as e:
        logger.error(f"Persona rollback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics")
@app.get("/analytics")  # Support both routes
async def get_analytics(_: RequestContext = Depends(get_request_context)):
    """Get analytics data"""
    try:
        with get_db_session() as session:
            return analytics_service.get_analytics_summary(session)
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files in production
if os.getenv("NODE_ENV") == "production":
    app.mount("/", StaticFiles(directory="dist/public", html=True), name="static")

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    try:
        logger.info("Starting DaLeoBanks AI Agent...")

        # Initialize database
        init_db()

        # Verify the decision ledger before anything can act. A broken chain
        # means the audit trail was tampered with or corrupted: go quiet and
        # surface it rather than operating unaudited.
        ledger = get_ledger()
        chain_ok, bad_seq = ledger.verify_chain()
        if not chain_ok:
            logger.critical(f"Decision ledger chain broken at seq {bad_seq}; disarming live mode")
            get_kill_switch().set_armed(False, reason=f"ledger_chain_broken_at_{bad_seq}")
        ledger.record("startup", {"live": config.LIVE, "chain_ok": chain_ok})

        # Record the constitution hash: the fixed values this process runs
        # under. Runtime drift is checked nightly and disarms live mode.
        runner.constitution_guard.load_and_record()

        # Load persona and drives
        persona_store.load_persona()
        
        # Initialize self-model
        await self_model_service.ensure_self_model()
        
        # Start background runner
        await runner.start_scheduler()
        
        logger.info("DaLeoBanks AI Agent started successfully")
        
        # Initial activity if LIVE mode
        if config.LIVE and x_client:
            asyncio.create_task(runner.initial_activity())
            
    except Exception as e:
        logger.error(f"Startup error: {e}")
        traceback.print_exc()
        sys.exit(1)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down DaLeoBanks AI Agent...")
    await runner.stop_scheduler()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("NODE_ENV") == "development"
    )
