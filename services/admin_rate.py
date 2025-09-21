"""
Admin authentication and rate limiting for write operations
"""

import time
from typing import Dict, List, Optional
from collections import defaultdict, deque
from datetime import datetime, timedelta, UTC

from config import get_config
from services.logging_utils import get_logger

logger = get_logger(__name__)

class AdminRateLimiter:
    """Rate limiter for admin write operations"""
    
    def __init__(self):
        self.config = get_config()
        
        # Rate limit: 10 writes per 60 seconds
        self.max_requests = 10
        self.window_seconds = 60
        
        # Sliding window implementation
        self.request_timestamps: deque = deque()
        
        # Track requests by IP/token for more granular limiting
        self.client_requests: Dict[str, deque] = defaultdict(lambda: deque())
        
        # Blocked clients (temporary)
        self.blocked_until: Dict[str, datetime] = {}
    
    def is_valid_admin_token(self, token: Optional[str]) -> bool:
        """Validate admin token"""
        if not token:
            return False
        
        return token == self.config.ADMIN_TOKEN
    
    def allow_request(self, client_id: str = "default") -> bool:
        """Check if request is allowed under rate limits"""
        now = datetime.now(UTC)
        
        # Check if client is temporarily blocked
        if client_id in self.blocked_until:
            if now < self.blocked_until[client_id]:
                logger.warning(f"Request blocked - client {client_id} is temporarily banned")
                return False
            else:
                # Unblock client
                del self.blocked_until[client_id]
        
        # Clean up old timestamps
        cutoff = now - timedelta(seconds=self.window_seconds)
        
        # Global rate limiting
        while self.request_timestamps and self.request_timestamps[0] < cutoff:
            self.request_timestamps.popleft()
        
        # Client-specific rate limiting
        client_queue = self.client_requests[client_id]
        while client_queue and client_queue[0] < cutoff:
            client_queue.popleft()
        
        # Check limits
        global_requests = len(self.request_timestamps)
        client_requests = len(client_queue)
        
        if global_requests >= self.max_requests:
            logger.warning(f"Global rate limit exceeded: {global_requests}/{self.max_requests}")
            return False
        
        if client_requests >= self.max_requests:
            logger.warning(f"Client rate limit exceeded for {client_id}: {client_requests}/{self.max_requests}")
            # Temporarily block aggressive clients
            self._block_client(client_id, minutes=5)
            return False
        
        # Record the request
        self.request_timestamps.append(now)
        self.client_requests[client_id].append(now)
        
        return True
    
    def _block_client(self, client_id: str, minutes: int = 5):
        """Temporarily block a client"""
        block_until = datetime.now(UTC) + timedelta(minutes=minutes)
        self.blocked_until[client_id] = block_until
        
        logger.warning(f"Blocked client {client_id} until {block_until}")
    
    def get_rate_limit_status(self, client_id: str = "default") -> Dict[str, any]:
        """Get current rate limit status"""
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self.window_seconds)
        
        # Clean up old timestamps
        while self.request_timestamps and self.request_timestamps[0] < cutoff:
            self.request_timestamps.popleft()
        
        client_queue = self.client_requests[client_id]
        while client_queue and client_queue[0] < cutoff:
            client_queue.popleft()
        
        global_remaining = max(0, self.max_requests - len(self.request_timestamps))
        client_remaining = max(0, self.max_requests - len(client_queue))
        
        # Check if blocked
        is_blocked = client_id in self.blocked_until and now < self.blocked_until[client_id]
        blocked_until = self.blocked_until.get(client_id)
        
        return {
            "global_remaining": global_remaining,
            "client_remaining": client_remaining,
            "window_seconds": self.window_seconds,
            "is_blocked": is_blocked,
            "blocked_until": blocked_until.isoformat() if blocked_until else None,
            "reset_time": (now + timedelta(seconds=self.window_seconds)).isoformat()
        }
    
    def authenticate_and_rate_limit(self, token: Optional[str], client_id: str = "default") -> bool:
        """Combined authentication and rate limiting check"""
        # First check authentication
        if not self.is_valid_admin_token(token):
            logger.warning(f"Invalid admin token from client {client_id}")
            return False
        
        # Then check rate limits
        if not self.allow_request(client_id):
            logger.warning(f"Rate limit exceeded for authenticated client {client_id}")
            return False
        
        return True
    
    def get_global_stats(self) -> Dict[str, any]:
        """Get global rate limiting statistics"""
        now = datetime.now(UTC)
        
        # Active clients
        active_clients = len([
            client_id for client_id, queue in self.client_requests.items()
            if queue and queue[-1] > now - timedelta(minutes=5)
        ])
        
        # Blocked clients
        blocked_clients = len([
            client_id for client_id, block_time in self.blocked_until.items()
            if now < block_time
        ])
        
        # Recent request rate
        recent_cutoff = now - timedelta(minutes=1)
        recent_requests = len([
            ts for ts in self.request_timestamps
            if ts > recent_cutoff
        ])
        
        return {
            "total_requests_last_hour": len(self.request_timestamps),
            "recent_requests_per_minute": recent_requests,
            "active_clients": active_clients,
            "blocked_clients": blocked_clients,
            "rate_limit_config": {
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds
            }
        }
    
    def reset_client_limits(self, client_id: str):
        """Reset rate limits for a specific client (admin function)"""
        if client_id in self.client_requests:
            self.client_requests[client_id].clear()
        
        if client_id in self.blocked_until:
            del self.blocked_until[client_id]
        
        logger.info(f"Reset rate limits for client {client_id}")
    
    def extend_block(self, client_id: str, additional_minutes: int = 10):
        """Extend block time for problematic clients"""
        current_block = self.blocked_until.get(client_id, datetime.now(UTC))
        new_block_time = max(current_block, datetime.now(UTC)) + timedelta(minutes=additional_minutes)
        
        self.blocked_until[client_id] = new_block_time
        logger.warning(f"Extended block for client {client_id} until {new_block_time}")
    
    def cleanup_old_data(self):
        """Clean up old tracking data"""
        now = datetime.now(UTC)
        cleanup_cutoff = now - timedelta(hours=1)
        
        # Clean up global timestamps
        while self.request_timestamps and self.request_timestamps[0] < cleanup_cutoff:
            self.request_timestamps.popleft()
        
        # Clean up client requests
        for client_id, queue in list(self.client_requests.items()):
            while queue and queue[0] < cleanup_cutoff:
                queue.popleft()
            
            # Remove empty queues
            if not queue:
                del self.client_requests[client_id]
        
        # Clean up expired blocks
        expired_blocks = [
            client_id for client_id, block_time in self.blocked_until.items()
            if now >= block_time
        ]
        
        for client_id in expired_blocks:
            del self.blocked_until[client_id]
        
        if expired_blocks:
            logger.info(f"Cleaned up {len(expired_blocks)} expired client blocks")

