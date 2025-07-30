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
    
    # Goal weights
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
        GOAL_MODE=os.getenv("GOAL_MODE", "FAME"),
        LIVE=os.getenv("LIVE", "true").lower() == "true",
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
        
        # Goal weights
        GOAL_WEIGHTS={
            "FAME": {"alpha": 0.65, "beta": 0.15, "gamma": 0.25, "lambda": 0.20},
            "MONETIZE": {"alpha": 0.30, "beta": 0.55, "gamma": 0.25, "lambda": 0.25}
        }
    )
