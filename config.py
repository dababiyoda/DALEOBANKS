"""
Configuration management for DaLeoBanks AI Agent
"""

import os
from typing import Dict, List, Tuple, Optional, Callable, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class Config:
    # Environment
    APP_ENV: str
    PORT: int
    TIMEZONE: str
    
    # API Keys
    OPENAI_API_KEY: str
    X_BEARER_TOKEN: Optional[str]
    X_API_KEY: Optional[str]
    X_API_SECRET: Optional[str]
    X_ACCESS_TOKEN: Optional[str]
    X_ACCESS_SECRET: Optional[str]
    ADMIN_TOKEN: str
    JWT_SECRET: str
    JWT_ISSUER: Optional[str]
    JWT_AUDIENCE: Optional[str]

    # Operation Mode
    GOAL_MODE: str
    LIVE: bool
    QUIET_HOURS_ET: Optional[List[int]]

    # Network safety
    ALLOWED_ORIGINS: List[str]
    ALLOWED_IPS: List[str]

    # Media settings
    MEDIA_CATEGORY: str

    # Request observability
    REQUEST_ID_HEADER: str

    # Rate limiting
    ROLE_RATE_LIMITS: Dict[str, int]
    ROLE_RATE_LIMIT_WINDOW: int
    
    # Schedules (in minutes)
    POST_TWEET_EVERY: Tuple[int, int]
    REPLY_MENTIONS_EVERY: Tuple[int, int]
    SEARCH_ENGAGE_EVERY: Tuple[int, int]
    ANALYTICS_PULL_EVERY: Tuple[int, int]
    KPI_ROLLUP_EVERY: Tuple[int, int]
    FOLLOWER_SNAPSHOT_DAILY_HOUR: int
    NIGHTLY_REFLECTION_HOUR: int
    WEEKLY_PLANNING_DAY_HOUR: str
    
    # Rate limiting and backoff
    MAX_BACKOFF_SECONDS: int
    CIRCUIT_BREAKER_FAILURES: int
    
    # Action toggles
    ENABLE_LIKES: bool
    ENABLE_REPOSTS: bool
    ENABLE_QUOTES: bool
    ENABLE_FOLLOWS: bool
    ENABLE_BOOKMARKS: bool
    ENABLE_DMS: bool
    ENABLE_MEDIA: bool
    ENABLE_LINKEDIN: bool
    ENABLE_MASTODON: bool

    # Social platform routing
    PLATFORM_MODE: str
    PLATFORM_WEIGHTS: Dict[str, float]

    # Intensity settings
    ADAPTIVE_INTENSITY: bool
    MIN_INTENSITY_LEVEL: int
    MAX_INTENSITY_LEVEL: int
    RAGEBAIT_GUARD: bool

    # Goal parameters
    IMPACT_WEEKLY_FLOOR: int
    WEIGHTS_IMPACT: Dict[str, float]
    WEIGHTS_REVENUE: Dict[str, float]
    WEIGHTS_AUTHORITY: Dict[str, float]
    WEIGHTS_FAME: Dict[str, float]
    GOAL_WEIGHTS: Dict[str, Dict[str, float]]


ConfigListener = Callable[["Config", Dict[str, Any]], None]

_CONFIG_INSTANCE: Optional[Config] = None
_CONFIG_LISTENERS: List[ConfigListener] = []


def _parse_weights(var: str, default: str) -> Dict[str, float]:
    raw = os.getenv(var, default)
    try:
        alpha, beta, gamma, lam = [float(x) for x in raw.split(",")]
        return {"alpha": alpha, "beta": beta, "gamma": gamma, "lambda": lam}
    except Exception:
        return {"alpha": 0.0, "beta": 0.0, "gamma": 0.0, "lambda": 0.0}


def _parse_platform_weights(raw: str) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for chunk in raw.split(","):
        if not chunk.strip():
            continue
        if ":" not in chunk:
            continue
        platform, weight = chunk.split(":", 1)
        try:
            weights[platform.strip().lower()] = float(weight.strip())
        except ValueError:
            continue
    return weights or {"x": 1.0}


def _parse_role_limits(raw: str) -> Dict[str, int]:
    limits: Dict[str, int] = {}
    for chunk in raw.split(","):
        if not chunk.strip():
            continue
        if ":" not in chunk:
            continue
        role, limit = chunk.split(":", 1)
        try:
            limits[role.strip().lower()] = int(limit.strip())
        except ValueError:
            continue
    return limits


def _build_config() -> Config:
    """Create a new ``Config`` instance from environment variables."""

    quiet_hours = None
    if os.getenv("QUIET_HOURS_ET"):
        try:
            quiet_hours = [int(x) for x in os.getenv("QUIET_HOURS_ET", "").split(",")]
        except Exception:
            quiet_hours = None

    weights_impact = _parse_weights("WEIGHTS_IMPACT", "0.40,0.30,0.20,0.10")
    weights_revenue = _parse_weights("WEIGHTS_REVENUE", "0.30,0.55,0.25,0.25")
    weights_authority = _parse_weights("WEIGHTS_AUTHORITY", "0.45,0.20,0.25,0.10")
    weights_fame = _parse_weights("WEIGHTS_FAME", "0.65,0.15,0.25,0.20")
    platform_weights = _parse_platform_weights(os.getenv("PLATFORM_WEIGHTS", "x:1.0"))

    return Config(
        # Environment
        APP_ENV=os.getenv("APP_ENV", "prod"),
        PORT=int(os.getenv("PORT", 8000)),
        TIMEZONE=os.getenv("TIMEZONE", "America/New_York"),

        # API Keys
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        X_BEARER_TOKEN=os.getenv("X_BEARER_TOKEN"),
        X_API_KEY=os.getenv("X_API_KEY"),
        X_API_SECRET=os.getenv("X_API_SECRET"),
        X_ACCESS_TOKEN=os.getenv("X_ACCESS_TOKEN"),
        X_ACCESS_SECRET=os.getenv("X_ACCESS_SECRET"),
        ADMIN_TOKEN=os.getenv("ADMIN_TOKEN", "choose-a-long-random-string"),
        JWT_SECRET=os.getenv("JWT_SECRET", "change-me-please"),
        JWT_ISSUER=os.getenv("JWT_ISSUER", None),
        JWT_AUDIENCE=os.getenv("JWT_AUDIENCE", None),

        # Operation Mode
        GOAL_MODE=os.getenv("GOAL_MODE", "IMPACT"),
        LIVE=os.getenv("LIVE", "false").lower() == "true",
        QUIET_HOURS_ET=quiet_hours,

        # Network safety
        ALLOWED_ORIGINS=[origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()],
        ALLOWED_IPS=[ip.strip() for ip in os.getenv("ALLOWED_IPS", "").split(",") if ip.strip()],

        # Media settings
        MEDIA_CATEGORY=os.getenv("MEDIA_CATEGORY", "tweet_image"),

        # Request observability
        REQUEST_ID_HEADER=os.getenv("REQUEST_ID_HEADER", "X-Request-ID"),

        # Rate limiting
        ROLE_RATE_LIMITS={
            **{"default": 120, "admin": 30, "service": 300},
            **_parse_role_limits(os.getenv("ROLE_RATE_LIMITS", ""))
        },
        ROLE_RATE_LIMIT_WINDOW=int(os.getenv("ROLE_RATE_LIMIT_WINDOW", 60)),

        # Schedules
        POST_TWEET_EVERY=(45, 90),
        REPLY_MENTIONS_EVERY=(12, 25),
        SEARCH_ENGAGE_EVERY=(25, 45),
        ANALYTICS_PULL_EVERY=(35, 60),
        KPI_ROLLUP_EVERY=(60, 90),
        FOLLOWER_SNAPSHOT_DAILY_HOUR=3,
        NIGHTLY_REFLECTION_HOUR=4,
        WEEKLY_PLANNING_DAY_HOUR="Sun@5",

        # Rate limiting and backoff
        MAX_BACKOFF_SECONDS=120,
        CIRCUIT_BREAKER_FAILURES=5,

        # Action toggles
        ENABLE_LIKES=os.getenv("ENABLE_LIKES", "true").lower() == "true",
        ENABLE_REPOSTS=os.getenv("ENABLE_REPOSTS", "true").lower() == "true",
        ENABLE_QUOTES=os.getenv("ENABLE_QUOTES", "true").lower() == "true",
        ENABLE_FOLLOWS=os.getenv("ENABLE_FOLLOWS", "true").lower() == "true",
        ENABLE_BOOKMARKS=os.getenv("ENABLE_BOOKMARKS", "true").lower() == "true",
        ENABLE_DMS=os.getenv("ENABLE_DMS", "true").lower() == "true",
        ENABLE_MEDIA=os.getenv("ENABLE_MEDIA", "true").lower() == "true",
        ENABLE_LINKEDIN=os.getenv("ENABLE_LINKEDIN", "false").lower() == "true",
        ENABLE_MASTODON=os.getenv("ENABLE_MASTODON", "false").lower() == "true",

        # Social platform routing
        PLATFORM_MODE=os.getenv("PLATFORM_MODE", "broadcast").lower(),
        PLATFORM_WEIGHTS=platform_weights,

        # Intensity settings
        ADAPTIVE_INTENSITY=os.getenv("ADAPTIVE_INTENSITY", "false").lower() == "true",
        MIN_INTENSITY_LEVEL=int(os.getenv("MIN_LEVEL", 1)),
        MAX_INTENSITY_LEVEL=int(os.getenv("MAX_LEVEL", 4)),
        RAGEBAIT_GUARD=os.getenv("RAGEBAIT_GUARD", "on").lower() in ("on", "true", "1"),

        # Goal parameters
        IMPACT_WEEKLY_FLOOR=int(os.getenv("IMPACT_WEEKLY_FLOOR", 10)),
        WEIGHTS_IMPACT=weights_impact,
        WEIGHTS_REVENUE=weights_revenue,
        WEIGHTS_AUTHORITY=weights_authority,
        WEIGHTS_FAME=weights_fame,
        GOAL_WEIGHTS={
            "IMPACT": weights_impact,
            "REVENUE": weights_revenue,
            "AUTHORITY": weights_authority,
            "FAME": weights_fame,
            "MONETIZE": weights_revenue,
        }
    )


def _notify_listeners(changes: Dict[str, Any]) -> None:
    """Notify registered listeners of configuration changes."""

    if not changes:
        return

    cfg = get_config()
    for listener in list(_CONFIG_LISTENERS):
        try:
            listener(cfg, changes)
        except Exception:
            # Listeners should not break config updates; ignore failures.
            continue


def get_config() -> Config:
    """Return the shared configuration object."""

    global _CONFIG_INSTANCE
    if _CONFIG_INSTANCE is None:
        _CONFIG_INSTANCE = _build_config()
    return _CONFIG_INSTANCE


def update_config(**updates: Any) -> Config:
    """Mutate the shared config in place and notify listeners."""

    cfg = get_config()
    applied: Dict[str, Any] = {}

    for key, value in updates.items():
        if not hasattr(cfg, key):
            raise AttributeError(f"Config has no attribute '{key}'")
        current = getattr(cfg, key)
        if current == value:
            continue
        setattr(cfg, key, value)
        applied[key] = value

    if applied:
        _notify_listeners(applied)
    return cfg


def subscribe_to_updates(listener: ConfigListener) -> Callable[[], None]:
    """Register a callback invoked when the configuration changes."""

    if listener not in _CONFIG_LISTENERS:
        _CONFIG_LISTENERS.append(listener)

    def _unsubscribe() -> None:
        try:
            _CONFIG_LISTENERS.remove(listener)
        except ValueError:
            pass

    return _unsubscribe


def reset_config() -> Config:
    """Reload configuration from the environment and notify listeners."""

    global _CONFIG_INSTANCE
    _CONFIG_INSTANCE = _build_config()
    _notify_listeners({"__reset__": True})
    return _CONFIG_INSTANCE
