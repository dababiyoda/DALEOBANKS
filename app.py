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
    """Health check endpoint"""
    return {"ok": True, "timestamp": datetime.now(UTC).isoformat()}

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
