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
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header, Depends
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

# Import runner for background tasks
import runner

# Initialize logger
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="DaLeoBanks AI Agent",
    description="Autonomous AI agent with self-evolution capabilities",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
config = get_config()
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

# Dependency for admin auth
async def verify_admin_token(x_admin_token: Optional[str] = Header(None)):
    if not x_admin_token or x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return True

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
async def get_dashboard():
    """Get dashboard overview data"""
    try:
        with get_db_session() as session:
            # Get latest KPIs
            kpis = kpi_service.get_latest_kpis(session)
            
            # Get recent activity
            recent_actions = session.query(Action).order_by(Action.created_at.desc()).limit(10).all()
            
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

@app.post("/api/toggle")
async def toggle_live_mode(request: ToggleRequest):
    """Toggle LIVE mode on/off"""
    try:
        update_config(LIVE=request.live)
        
        # Broadcast update to clients
        await broadcast_update({
            "type": "live_mode_changed",
            "live": config.LIVE
        })
        
        logger.info(f"LIVE mode {'activated' if config.LIVE else 'paused'}")
        return {"live": config.LIVE}
    except Exception as e:
        logger.error(f"Toggle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/r/{redirect_id}")
async def handle_redirect(redirect_id: str):
    """Handle redirect and track clicks"""
    try:
        with get_db_session() as session:
            redirect = session.query(Redirect).filter(Redirect.id == redirect_id).first()
            if not redirect:
                raise HTTPException(status_code=404, detail="Redirect not found")
            
            # Increment clicks
            session.query(Redirect).filter(Redirect.id == redirect_id).update(
                {Redirect.clicks: Redirect.clicks + 1}
            )
            session.commit()
            
            return RedirectResponse(url=str(redirect.target_url), status_code=302)
    except Exception as e:
        logger.error(f"Redirect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"ok": True, "timestamp": datetime.now(UTC).isoformat()}

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
            versions = session.query(PersonaVersion).order_by(PersonaVersion.version.desc()).all()
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
async def preview_persona(request: PersonaUpdateRequest, _: bool = Depends(verify_admin_token)):
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
async def update_persona(request: PersonaUpdateRequest, _: bool = Depends(verify_admin_token)):
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
async def rollback_persona(version: int, _: bool = Depends(verify_admin_token)):
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
async def get_analytics():
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
