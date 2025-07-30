"""
Twitter/X API Client wrapper using Tweepy v2
"""

import asyncio
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import tweepy
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import get_config
from services.logging_utils import get_logger

logger = get_logger(__name__)

@dataclass
class CircuitBreaker:
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    failure_threshold: int = 5
    reset_timeout: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    
    def is_open(self) -> bool:
        if self.failure_count < self.failure_threshold:
            return False
        if self.last_failure_time and datetime.now() - self.last_failure_time > self.reset_timeout:
            self.failure_count = 0
            return False
        return True
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
    
    def record_success(self):
        self.failure_count = 0
        self.last_failure_time = None

class XClient:
    """Twitter/X API wrapper with rate limiting and circuit breakers"""
    
    def __init__(self):
        self.config = get_config()
        self.client = None
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._initialize_client()
        
    def _initialize_client(self):
        """Initialize Tweepy client with credentials"""
        try:
            if not all([
                self.config.X_API_KEY,
                self.config.X_API_SECRET,
                self.config.X_ACCESS_TOKEN,
                self.config.X_ACCESS_SECRET
            ]):
                logger.warning("X API credentials incomplete, running in dry-run mode")
                return
                
            self.client = tweepy.Client(
                bearer_token=self.config.X_BEARER_TOKEN,
                consumer_key=self.config.X_API_KEY,
                consumer_secret=self.config.X_API_SECRET,
                access_token=self.config.X_ACCESS_TOKEN,
                access_token_secret=self.config.X_ACCESS_SECRET,
                wait_on_rate_limit=True
            )
            
            # Test connection
            self.client.get_me()
            logger.info("X API client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize X client: {e}")
            self.client = None
    
    def is_healthy(self) -> bool:
        """Check if client is healthy"""
        return self.client is not None
    
    def _check_circuit_breaker(self, endpoint: str) -> bool:
        """Check if circuit breaker allows requests"""
        if endpoint not in self.circuit_breakers:
            self.circuit_breakers[endpoint] = CircuitBreaker()
        
        breaker = self.circuit_breakers[endpoint]
        if breaker.is_open():
            logger.warning(f"Circuit breaker open for {endpoint}")
            return False
        return True
    
    def _record_success(self, endpoint: str):
        """Record successful API call"""
        if endpoint in self.circuit_breakers:
            self.circuit_breakers[endpoint].record_success()
    
    def _record_failure(self, endpoint: str):
        """Record failed API call"""
        if endpoint not in self.circuit_breakers:
            self.circuit_breakers[endpoint] = CircuitBreaker()
        self.circuit_breakers[endpoint].record_failure()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((tweepy.TooManyRequests, tweepy.TwitterServerError))
    )
    async def create_tweet(
        self, 
        text: str, 
        quote_tweet_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        media_ids: Optional[List[str]] = None
    ) -> Optional[str]:
        """Create a tweet"""
        endpoint = "create_tweet"
        
        if not self.config.LIVE:
            logger.info(f"DRY RUN - Would post tweet: {text[:100]}...")
            return "dry_run_tweet_id"
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return None
        
        try:
            kwargs = {"text": text}
            
            if quote_tweet_id:
                kwargs["quote_tweet_id"] = quote_tweet_id
            if in_reply_to:
                kwargs["in_reply_to_tweet_id"] = in_reply_to
            if media_ids:
                kwargs["media_ids"] = media_ids
            
            response = self.client.create_tweet(**kwargs)
            tweet_id = response.data["id"]
            
            self._record_success(endpoint)
            logger.info(f"Tweet created: {tweet_id}")
            return tweet_id
            
        except tweepy.TooManyRequests as e:
            logger.warning(f"Rate limited on {endpoint}: {e}")
            self._record_failure(endpoint)
            raise
        except Exception as e:
            logger.error(f"Failed to create tweet: {e}")
            self._record_failure(endpoint)
            return None
    
    async def like(self, tweet_id: str) -> bool:
        """Like a tweet"""
        endpoint = "like"
        
        if not self.config.ENABLE_LIKES or not self.config.LIVE:
            logger.info(f"DRY RUN - Would like tweet: {tweet_id}")
            return True
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return False
        
        try:
            self.client.like(tweet_id)
            self._record_success(endpoint)
            logger.info(f"Liked tweet: {tweet_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to like tweet {tweet_id}: {e}")
            self._record_failure(endpoint)
            return False
    
    async def unlike(self, tweet_id: str) -> bool:
        """Unlike a tweet"""
        endpoint = "unlike"
        
        if not self.config.LIVE:
            logger.info(f"DRY RUN - Would unlike tweet: {tweet_id}")
            return True
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return False
        
        try:
            self.client.unlike(tweet_id)
            self._record_success(endpoint)
            return True
        except Exception as e:
            logger.error(f"Failed to unlike tweet {tweet_id}: {e}")
            self._record_failure(endpoint)
            return False
    
    async def repost(self, tweet_id: str) -> bool:
        """Repost (retweet) a tweet"""
        endpoint = "repost"
        
        if not self.config.ENABLE_REPOSTS or not self.config.LIVE:
            logger.info(f"DRY RUN - Would repost tweet: {tweet_id}")
            return True
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return False
        
        try:
            self.client.retweet(tweet_id)
            self._record_success(endpoint)
            logger.info(f"Retweeted: {tweet_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to retweet {tweet_id}: {e}")
            self._record_failure(endpoint)
            return False
    
    async def follow(self, user_id: str) -> bool:
        """Follow a user"""
        endpoint = "follow"
        
        if not self.config.ENABLE_FOLLOWS or not self.config.LIVE:
            logger.info(f"DRY RUN - Would follow user: {user_id}")
            return True
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return False
        
        try:
            self.client.follow_user(user_id)
            self._record_success(endpoint)
            logger.info(f"Followed user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to follow user {user_id}: {e}")
            self._record_failure(endpoint)
            return False
    
    async def search_recent(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search recent tweets"""
        endpoint = "search"
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return []
        
        try:
            tweets = tweepy.Paginator(
                self.client.search_recent_tweets,
                query=query,
                max_results=max_results,
                tweet_fields=["public_metrics", "created_at", "author_id"]
            ).flatten(limit=max_results)
            
            results = []
            for tweet in tweets:
                results.append({
                    "id": tweet.id,
                    "text": tweet.text,
                    "author_id": tweet.author_id,
                    "created_at": tweet.created_at,
                    "public_metrics": tweet.public_metrics
                })
            
            self._record_success(endpoint)
            return results
            
        except Exception as e:
            logger.error(f"Failed to search tweets: {e}")
            self._record_failure(endpoint)
            return []
    
    async def get_mentions(self, since_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get mentions of the authenticated user"""
        endpoint = "mentions"
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return []
        
        try:
            kwargs = {"tweet_fields": ["public_metrics", "created_at", "author_id"]}
            if since_id:
                kwargs["since_id"] = since_id
            
            mentions = self.client.get_mentions(**kwargs)
            
            results = []
            if mentions.data:
                for tweet in mentions.data:
                    results.append({
                        "id": tweet.id,
                        "text": tweet.text,
                        "author_id": tweet.author_id,
                        "created_at": tweet.created_at,
                        "public_metrics": tweet.public_metrics
                    })
            
            self._record_success(endpoint)
            return results
            
        except Exception as e:
            logger.error(f"Failed to get mentions: {e}")
            self._record_failure(endpoint)
            return []
    
    async def metrics_for(self, tweet_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """Get metrics for specific tweets"""
        endpoint = "metrics"
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return {}
        
        try:
            tweets = self.client.get_tweets(
                ids=tweet_ids,
                tweet_fields=["public_metrics"]
            )
            
            metrics = {}
            if tweets.data:
                for tweet in tweets.data:
                    metrics[tweet.id] = tweet.public_metrics
            
            self._record_success(endpoint)
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            self._record_failure(endpoint)
            return {}
