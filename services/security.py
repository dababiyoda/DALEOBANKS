"""Security utilities: JWT auth, allowlists, and per-role rate limiting."""
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, status

from config import get_config
from services.logging_utils import get_logger

logger = get_logger(__name__)


def _parse_roles(claims: Dict[str, object]) -> List[str]:
    roles: List[str] = []
    raw_roles = claims.get("roles") or claims.get("role")
    if isinstance(raw_roles, list):
        roles = [str(r).lower() for r in raw_roles]
    elif isinstance(raw_roles, str):
        roles = [raw_roles.lower()]
    return roles or ["user"]


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@dataclass
class RequestContext:
    request_id: str
    subject: str
    roles: List[str]
    client_ip: str


class RoleRateLimiter:
    """Simple in-memory per-role limiter using sliding window."""

    def __init__(self, limits: Dict[str, int], window_seconds: int = 60):
        self.limits = limits
        self.window_seconds = window_seconds
        self.history: Dict[str, List[datetime]] = {}

    def allow(self, role: str, key: str) -> bool:
        limit = self.limits.get(role, self.limits.get("default"))
        if not limit:
            return True

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=self.window_seconds)
        bucket = self.history.setdefault(key, [])
        # drop stale
        self.history[key] = [ts for ts in bucket if ts > window_start]
        if len(self.history[key]) >= limit:
            return False
        self.history[key].append(now)
        return True


_config = get_config()
role_limiter = RoleRateLimiter(_config.ROLE_RATE_LIMITS, window_seconds=_config.ROLE_RATE_LIMIT_WINDOW)


def get_request_context(request: Request) -> RequestContext:
    config = get_config()
    req_id = request.headers.get(config.REQUEST_ID_HEADER, str(uuid4()))
    client_ip = _client_ip(request)

    if config.ALLOWED_IPS and client_ip not in config.ALLOWED_IPS:
        logger.warning("Blocked request from disallowed IP", extra_data={"client_ip": client_ip, "path": request.url.path})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not allowed")

    auth_header = request.headers.get("authorization")
    subject = "anonymous"
    roles: List[str] = ["anonymous"]

    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            claims = jwt.decode(
                token,
                config.JWT_SECRET,
                algorithms=["HS256"],
                audience=config.JWT_AUDIENCE,
                issuer=config.JWT_ISSUER or None,
                options={"verify_aud": bool(config.JWT_AUDIENCE)},
            )
            subject = str(claims.get("sub", subject))
            roles = _parse_roles(claims)
        except Exception as exc:
            logger.warning("JWT validation failed", extra_data={"error": str(exc)})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    context = RequestContext(request_id=req_id, subject=subject, roles=roles, client_ip=client_ip)
    request.state.request_context = context
    return context


def require_role(required_role: str):
    async def dependency(context: RequestContext = Depends(get_request_context)) -> RequestContext:
        if required_role not in context.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

        limiter_key = f"{required_role}:{context.client_ip or context.subject}"
        if not role_limiter.allow(required_role, limiter_key):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded for role")
        return context

    return dependency


def require_any_role(roles: List[str]):
    async def dependency(context: RequestContext = Depends(get_request_context)) -> RequestContext:
        if not any(role in context.roles for role in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

        limiter_key = f"{','.join(sorted(context.roles))}:{context.client_ip or context.subject}"
        dominant_role = next((role for role in roles if role in context.roles), roles[0])
        if not role_limiter.allow(dominant_role, limiter_key):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded for role")
        return context

    return dependency
