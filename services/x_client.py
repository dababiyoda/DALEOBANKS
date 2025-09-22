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

from config import get_config, subscribe_to_updates
from services.logging_utils import get_logger
import random

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
        # Track idempotency keys to prevent duplicate writes
        # The key is a tuple of (endpoint, idempotency_key)
        self.idempotency_cache: Dict[tuple[str, str], bool] = {}
        # Maximum number of times to retry a write on rate‑limit failures
        self.max_write_attempts: int = 5
        self._initialize_client()
        self._unsubscribe = subscribe_to_updates(self._on_config_update)
        
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

    async def _execute_write(
        self,
        *,
        endpoint: str,
        enabled: bool,
        default_result: Any,
        func,
        idempotency_key: str | None = None,
        timeout: float = 15.0,
        require_live: bool = True,
        **kwargs,
    ) -> Any:
        """
        Internal helper to perform a write operation (tweet, like, DM, etc.)
        with exponential backoff and jitter, optional idempotency, and
        circuit breaker checks.

        Args:
            endpoint: Name of the API endpoint (used for circuit breakers).
            enabled: Feature toggle; if False, the call will be a dry run and
                     default_result is returned immediately.
            live_required: Whether LIVE mode must be True to perform the call.
            default_result: Value to return when in dry run or failure.
            func: Callable that performs the underlying API call. It should
                  accept **kwargs and return a result when successful.
            idempotency_key: Optional explicit idempotency key; if None,
                             one will be generated. If a call with the same
                             (endpoint, idempotency_key) has already
                             succeeded, the call is skipped and default_result
                             returned to avoid duplicates.
            timeout: Timeout in seconds for the underlying API call.
            **kwargs: Parameters forwarded to the underlying func.

        Returns:
            The result of func on success, default_result on dry run or failure.
        """
        # Dry run if feature disabled
        if not enabled:
            logger.info(
                f"DRY RUN - Would perform {endpoint} with args {kwargs}"
            )
            return default_result

        if require_live and not self.config.LIVE:
            logger.info(
                f"LIVE mode disabled - skipping {endpoint}"
            )
            return default_result

        # Ensure client is ready and circuit breaker is closed
        if not self.client or not self._check_circuit_breaker(endpoint):
            return default_result

        # Generate or check idempotency key
        if idempotency_key is None:
            # Use timestamp and random component to build a unique key
            idempotency_key = f"{endpoint}-{int(time.time()*1000)}-{random.randint(0, 999999)}"
        key_tuple = (endpoint, idempotency_key)
        if key_tuple in self.idempotency_cache:
            logger.info(
                f"Skipping duplicate call for {endpoint} with idempotency_key={idempotency_key}"
            )
            return default_result

        attempt = 0
        while attempt < self.max_write_attempts:
            try:
                if require_live and not self.config.LIVE:
                    logger.info(
                        f"LIVE mode disabled mid-flight - aborting {endpoint}"
                    )
                    return default_result
                # Execute the API call on a background thread with a timeout
                result = await asyncio.wait_for(
                    asyncio.to_thread(func, **kwargs),
                    timeout=timeout,
                )
                # Record success and mark idempotency key as used
                self._record_success(endpoint)
                self.idempotency_cache[key_tuple] = True
                return result
            except tweepy.TooManyRequests as e:
                # Rate limit error: exponential backoff with jitter
                attempt += 1
                self._record_failure(endpoint)
                # Compute backoff: base 2^attempt with random jitter between 0 and 1 seconds
                backoff_seconds = min(60.0, (2 ** attempt) + random.random())
                logger.warning(
                    f"Rate limited on {endpoint}: {e}. Retrying in {backoff_seconds:.2f}s (attempt {attempt})"
                )
                await asyncio.sleep(backoff_seconds)
            except Exception as e:
                # Any other failure: log and abort
                logger.error(f"Failed to perform {endpoint}: {e}")
                self._record_failure(endpoint)
                return default_result
        # Exceeded retries
        logger.error(f"Exceeded max retries for {endpoint}")
        return default_result
    
    async def create_tweet(
        self,
        text: str,
        quote_tweet_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        media_ids: Optional[List[str]] = None,
        *,
        idempotency_key: str | None = None,
    ) -> Optional[str]:
        """Create a tweet with exponential backoff, jitter and idempotency.

        When LIVE mode is disabled, the method logs a dry run and returns a
        dummy tweet ID. Otherwise, the underlying Tweepy client is invoked
        through the internal `_execute_write` helper which handles retries
        and circuit breakers.

        Args:
            text: Tweet text (max 280 chars).
            quote_tweet_id: Optional tweet ID to quote.
            in_reply_to: Optional tweet ID to reply to.
            media_ids: Optional list of media IDs to attach.
            idempotency_key: Optional idempotency key; if provided and
                previously used, the call will be skipped.

        Returns:
            The tweet ID on success, ``"dry_run_tweet_id"`` when not live,
            or ``None`` on failure.
        """
        endpoint = "create_tweet"
        # Build kwargs for the API call
        api_kwargs: Dict[str, Any] = {"text": text}
        if quote_tweet_id:
            api_kwargs["quote_tweet_id"] = quote_tweet_id
        if in_reply_to:
            api_kwargs["in_reply_to_tweet_id"] = in_reply_to
        if media_ids:
            api_kwargs["media_ids"] = media_ids

        def _call():
            response = self.client.create_tweet(**api_kwargs)
            return response.data["id"]

        result = await self._execute_write(
            endpoint=endpoint,
            enabled=True,
            default_result="dry_run_tweet_id",
            func=_call,
            idempotency_key=idempotency_key,
        )
        # If dry run or failure, result may be a dummy ID or None; ensure type
        return result  # type: ignore[return-value]
    
    async def like(self, tweet_id: str) -> bool:
        """Like a tweet"""
        endpoint = "like"
        
        def _call():
            return self.client.like(tweet_id)

        result = await self._execute_write(
            endpoint=endpoint,
            enabled=self.config.ENABLE_LIKES,
            default_result=True,
            func=_call,
        )
        return bool(result)

    async def send_dm(self, user_id: str, text: str) -> bool:
        """Send a direct message (DM) to a user.

        This helper wraps the Twitter/X DM endpoint and respects the
        configuration toggles. When LIVE mode is disabled or DMs are
        explicitly disabled via the configuration, the method logs a dry
        run and returns immediately. Circuit breakers are used to avoid
        hammering the API on repeated failures.

        Args:
            user_id: The target user's numerical ID.
            text: The message to send.

        Returns:
            True if the DM was sent (or would have been sent in dry run),
            False otherwise.
        """
        endpoint = "send_dm"

        # Compose a function to send the DM using whatever API is available
        def _call():
            if hasattr(self.client, "send_direct_message"):
                return self.client.send_direct_message(recipient_id=user_id, text=text)
            elif hasattr(self.client, "create_direct_message"):
                return self.client.create_direct_message(recipient_id=user_id, text=text)
            else:
                raise RuntimeError("DM API not available on Tweepy client")

        result = await self._execute_write(
            endpoint=endpoint,
            enabled=self.config.ENABLE_DMS,
            default_result=True,
            func=_call,
        )
        return bool(result)

    async def upload_media(self, media_path: str, media_type: str = "image") -> Optional[str]:
        """Upload an image or video to X and return the media ID.

        Media uploads are performed synchronously on a background thread via
        Tweepy. The media type determines the media_category passed to the
        endpoint. When LIVE mode or media uploads are disabled, a dummy
        media ID is returned so that the rest of the application can
        proceed without hitting the API.

        Args:
            media_path: The local filesystem path to the media file.
            media_type: Either ``"image"`` or ``"video"``.

        Returns:
            The string media ID on success, or ``None`` on failure.
        """
        endpoint = "upload_media"
        # Determine media_category based on type
        media_category = "tweet_image"
        if media_type.lower() == "video":
            media_category = "tweet_video"

        # Compose function to perform the upload
        def _call():
            # Use Tweepy v1.1 upload if available
            if hasattr(self.client, "media_upload"):
                media = self.client.media_upload(
                    filename=media_path, media_category=media_category
                )
                return getattr(media, "media_id_string", None) or getattr(media, "media_id", None)
            # Attempt to use v2 upload via create_media_upload if available
            if hasattr(self.client, "create_media_upload"):
                media = self.client.create_media_upload(
                    media_path, media_category=media_category
                )
                return media.media_id
            # Neither API available
            raise RuntimeError("Media upload API not available on Tweepy client")

        result = await self._execute_write(
            endpoint=endpoint,
            enabled=self.config.ENABLE_MEDIA,
            default_result="dry_run_media_id",
            func=_call,
        )
        if result is None or result == "dry_run_media_id":
            return result  # type: ignore[return-value]
        return str(result)
    
    async def unlike(self, tweet_id: str) -> bool:
        """Unlike a tweet"""
        endpoint = "unlike"
        # Compose function to perform the unlike
        def _call():
            return self.client.unlike(tweet_id)

        result = await self._execute_write(
            endpoint=endpoint,
            enabled=True,
            default_result=True,
            func=_call,
        )
        return bool(result)
    
    async def repost(self, tweet_id: str) -> bool:
        """Repost (retweet) a tweet"""
        endpoint = "repost"
        # Compose function to perform the retweet
        def _call():
            return self.client.retweet(tweet_id)

        result = await self._execute_write(
            endpoint=endpoint,
            enabled=self.config.ENABLE_REPOSTS,
            default_result=True,
            func=_call,
        )
        return bool(result)
    
    async def follow(self, user_id: str) -> bool:
        """Follow a user"""
        endpoint = "follow"
        # Compose function to perform the follow
        def _call():
            return self.client.follow_user(user_id)

        result = await self._execute_write(
            endpoint=endpoint,
            enabled=self.config.ENABLE_FOLLOWS,
            default_result=True,
            func=_call,
        )
        return bool(result)

    def _on_config_update(self, cfg, changes: Dict[str, Any]) -> None:
        if "LIVE" in changes and not cfg.LIVE:
            # Clear idempotency cache to avoid stale entries on resume
            self.idempotency_cache.clear()
            logger.info("XClient observed LIVE toggle -> paused writes")

    def __del__(self):  # pragma: no cover - defensive cleanup
        unsubscribe = getattr(self, "_unsubscribe", None)
        if callable(unsubscribe):
            try:
                unsubscribe()
            except Exception:
                pass
    
    async def search_recent(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search recent tweets"""
        endpoint = "search"
        
        if not self.client or not self._check_circuit_breaker(endpoint):
            return []
        
        try:
            def _search():
                return list(
                    tweepy.Paginator(
                        self.client.search_recent_tweets,
                        query=query,
                        max_results=max_results,
                        tweet_fields=["public_metrics", "created_at", "author_id"],
                    ).flatten(limit=max_results)
                )

            tweets = await asyncio.to_thread(_search)

            results = []
            for tweet in tweets:
                results.append(
                    {
                        "id": tweet.id,
                        "text": tweet.text,
                        "author_id": tweet.author_id,
                        "created_at": tweet.created_at,
                        "public_metrics": tweet.public_metrics,
                    }
                )
            
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
            
            mentions = await asyncio.to_thread(self.client.get_mentions, **kwargs)
            
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
            tweets = await asyncio.to_thread(
                self.client.get_tweets,
                ids=tweet_ids,
                tweet_fields=["public_metrics"],
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
