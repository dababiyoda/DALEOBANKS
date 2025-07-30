"""
OpenAI LLM Adapter with retry logic and budgets
"""

import asyncio
import json
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import get_config
from services.logging_utils import get_logger

logger = get_logger(__name__)

@dataclass
class LLMBudget:
    max_calls_per_hour: int = 100
    max_calls_per_day: int = 1000
    max_tokens_per_call: int = 4000
    current_hour_calls: int = 0
    current_day_calls: int = 0
    hour_reset_time: datetime = field(default_factory=datetime.now)
    day_reset_time: datetime = field(default_factory=datetime.now)

class LLMAdapter:
    """OpenAI adapter with retry logic and budget management"""
    
    def __init__(self):
        self.config = get_config()
        self.client = openai.AsyncOpenAI(api_key=self.config.OPENAI_API_KEY)
        self.budget = LLMBudget()
        self.template_fallback_enabled = True
        
    def _check_budget(self) -> bool:
        """Check if we're within budget limits"""
        now = datetime.now()
        
        # Reset hourly counter
        if now > self.budget.hour_reset_time + timedelta(hours=1):
            self.budget.current_hour_calls = 0
            self.budget.hour_reset_time = now
            
        # Reset daily counter
        if now > self.budget.day_reset_time + timedelta(days=1):
            self.budget.current_day_calls = 0
            self.budget.day_reset_time = now
            
        # Check limits
        if self.budget.current_hour_calls >= self.budget.max_calls_per_hour:
            logger.warning("Hourly LLM budget exceeded")
            return False
            
        if self.budget.current_day_calls >= self.budget.max_calls_per_day:
            logger.warning("Daily LLM budget exceeded")
            return False
            
        return True
    
    def _increment_budget(self):
        """Increment budget counters"""
        self.budget.current_hour_calls += 1
        self.budget.current_day_calls += 1
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError))
    )
    async def chat(
        self, 
        system: str, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Chat completion with retry logic and budget management
        
        Args:
            system: System prompt
            messages: Conversation messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text response
        """
        # Check budget
        if not self._check_budget():
            if self.template_fallback_enabled:
                logger.info("Budget exceeded, falling back to template-only generation")
                return self._template_fallback(system, messages)
            else:
                raise Exception("LLM budget exceeded and template fallback disabled")
        
        try:
            # Prepare messages
            chat_messages = [{"role": "system", "content": system}]
            chat_messages.extend(messages)
            
            # Make API call
            start_time = time.time()
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=chat_messages,
                temperature=temperature,
                max_tokens=max_tokens or self.budget.max_tokens_per_call
            )
            
            # Log metrics
            duration = time.time() - start_time
            usage = response.usage
            logger.info(f"LLM call completed in {duration:.2f}s, tokens: {usage.total_tokens}")
            
            # Increment budget
            self._increment_budget()
            
            return response.choices[0].message.content
            
        except openai.RateLimitError as e:
            logger.error(f"Rate limit error: {e}")
            raise
        except openai.APITimeoutError as e:
            logger.error(f"Timeout error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected LLM error: {e}")
            if self.template_fallback_enabled:
                return self._template_fallback(system, messages)
            raise
    
    def _template_fallback(self, system: str, messages: List[Dict[str, str]]) -> str:
        """
        Template-based fallback when LLM is unavailable
        """
        logger.info("Using template fallback")
        
        # Simple template-based response
        if "proposal" in system.lower():
            return """Problem: Current system lacks mechanism for X.
Mechanism: Implement Y with Z constraints.
Pilot: 30-day trial with 3 cohorts.
KPIs: 1) Adoption rate >20%, 2) Error rate <5%, 3) User satisfaction >4/5
Risks: Implementation complexity, user resistance
Rollback: Revert to previous system if KPIs not met
CTA: Join beta at link.bio"""
        elif "reply" in system.lower():
            return "Interesting point. Consider implementing X mechanism to address Y gap. Next step: prototype and measure."
        else:
            return "Thank you for the thoughtful input. Let me research this further and respond with a concrete mechanism."
    
    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status"""
        return {
            "hourly_usage": f"{self.budget.current_hour_calls}/{self.budget.max_calls_per_hour}",
            "daily_usage": f"{self.budget.current_day_calls}/{self.budget.max_calls_per_day}",
            "template_fallback": self.template_fallback_enabled
        }
