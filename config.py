"""
Configuration management for DaLeoBanks AI Agent
"""

import os
from typing import Dict, List, Tuple, Optional
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
    
    # Operation Mode
    GOAL_MODE: str
    LIVE: bool
    QUIET_HOURS_ET: Optional[List[int]]
    
    # Media settings
    MEDIA_CATEGORY: str
    
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

def get_config() -> Config:
    """Get configuration from environment variables"""

    # Parse quiet hours
    quiet_hours = None
    if os.getenv("QUIET_HOURS_ET"):
        try:
            quiet_hours = [int(x) for x in os.getenv("QUIET_HOURS_ET", "").split(",")]
        except:
            quiet_hours = None
    
    def _parse_weights(var: str, default: str) -> Dict[str, float]:
        raw = os.getenv(var, default)
        try:
            alpha, beta, gamma, lam = [float(x) for x in raw.split(",")]
            return {"alpha": alpha, "beta": beta, "gamma": gamma, "lambda": lam}
        except Exception:
            return {"alpha": 0.0, "beta": 0.0, "gamma": 0.0, "lambda": 0.0}

    weights_impact = _parse_weights("WEIGHTS_IMPACT", "0.40,0.30,0.20,0.10")
    weights_revenue = _parse_weights("WEIGHTS_REVENUE", "0.30,0.55,0.25,0.25")
    weights_authority = _parse_weights("WEIGHTS_AUTHORITY", "0.45,0.20,0.25,0.10")
    weights_fame = _parse_weights("WEIGHTS_FAME", "0.65,0.15,0.25,0.20")

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
        
        # Operation Mode
        GOAL_MODE=os.getenv("GOAL_MODE", "IMPACT"),
        LIVE=os.getenv("LIVE", "false").lower() == "true",
        QUIET_HOURS_ET=quiet_hours,
        
        # Media settings
        MEDIA_CATEGORY=os.getenv("MEDIA_CATEGORY", "tweet_image"),
        
        # Schedules
        POST_TWEET_EVERY=(45, 90),
        REPLY_MENTIONS_EVERY=(12, 25),
        SEARCH_ENGAGE_EVERY=(25, 45),
        ANALYTICS_PULL_EVERY=(35, 60),
        KPI_ROLLUP_EVERY=(60, 90),
        FOLLOWER_SNAPSHOT_DAILY_HOUR=3,
        NIGHTLY_REFLECTION_HOUR=4,
        WEEKLY_PLANNING_DAY_HOUR="Sun@5",
        
        # Rate limiting
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
