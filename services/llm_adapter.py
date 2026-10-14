"""
Local-first LLM adapter with retry logic, budgets and optional hosted fallbacks.

The primary model comes from ``services.model_settings``; explicitly listed
hosted fallbacks (``LLM_FALLBACKS``, see ``services.llm_providers``) are tried
only after it fails, then the template fallback.
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
from services.model_settings import model_settings
from services.llm_providers import ProviderConfig, resolve_fallbacks
import httpx
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
    """Local-first adapter with explicit provider selection and budget management."""
    
    def __init__(self, fallbacks: Optional[List[ProviderConfig]] = None):
        self.config = get_config()
        self.settings = model_settings()
        self.model = self.settings.model
        self.client = None if self.settings.provider == "template" else openai.AsyncOpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
            timeout=120.0,
            max_retries=0,
            http_client=httpx.AsyncClient(trust_env=False, follow_redirects=False),
        )
        # Offline template mode makes no calls at all, fallbacks included.
        if self.client is None:
            fallbacks = []
        elif fallbacks is None:
            fallbacks, skipped = resolve_fallbacks(primary=self.settings.provider)
            for reason in skipped:
                logger.warning(f"LLM fallback skipped: {reason}")
        self.fallbacks = list(fallbacks)
        # Hosted endpoints keep the environment's proxy settings; redirects stay off.
        self.fallback_clients = {
            p.name: openai.AsyncOpenAI(
                api_key=p.api_key,
                base_url=p.base_url,
                timeout=120.0,
                max_retries=0,
                http_client=httpx.AsyncClient(follow_redirects=False),
            )
            for p in self.fallbacks
        }
        self.last_provider: Optional[str] = None
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
        # No provider call is made in explicitly offline template mode.
        if self.client is None:
            self.last_provider = "template"
            return self._template_fallback(system, messages)
        # Check budget
        if not self._check_budget():
            if self.template_fallback_enabled:
                logger.info("Budget exceeded, falling back to template-only generation")
                self.last_provider = "template"
                return self._template_fallback(system, messages)
            else:
                raise Exception("LLM budget exceeded and template fallback disabled")
        
        try:
            # Prepare messages
            chat_messages = [{"role": "system", "content": system}]
            chat_messages.extend(messages)
            
            # Make API call
            start_time = time.time()
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=chat_messages,
                    temperature=temperature,
                    max_tokens=max_tokens or self.budget.max_tokens_per_call
                )
            except Exception as primary_error:
                if not self.fallbacks:
                    raise
                logger.warning(f"Primary {self.settings.provider} failed, trying fallbacks: {primary_error}")
                reply = await self._try_fallbacks(chat_messages, temperature, max_tokens)
                if reply is None:
                    raise
                return reply
            
            # Log metrics
            duration = time.time() - start_time
            usage = response.usage
            logger.info(f"LLM call completed in {duration:.2f}s, tokens: {usage.total_tokens}")
            
            # Increment budget
            self._increment_budget()
            self.last_provider = self.settings.provider
            
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
                self.last_provider = "template"
                return self._template_fallback(system, messages)
            raise
    
    async def _try_fallbacks(
        self,
        chat_messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> Optional[str]:
        """Try each listed hosted fallback once; None if all of them fail."""
        for provider in self.fallbacks:
            try:
                response = await self.fallback_clients[provider.name].chat.completions.create(
                    model=provider.model,
                    messages=chat_messages,
                    temperature=temperature,
                    max_tokens=max_tokens or self.budget.max_tokens_per_call,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("empty completion")
            except Exception as e:
                logger.warning(f"LLM fallback {provider.name} failed: {e}")
                continue
            logger.info(f"LLM call served by fallback {provider.name}/{provider.model}")
            self._increment_budget()
            self.last_provider = provider.name
            return content
        return None

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
            "template_fallback": self.template_fallback_enabled,
            "primary": {"provider": self.settings.provider, "model": self.model},
            "fallbacks": [
                {"name": p.name, "model": p.model, "open_weights": p.open_weights, "paid": p.paid}
                for p in self.fallbacks
            ],
            "last_provider": self.last_provider,
        }
