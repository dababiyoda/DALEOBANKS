"""
LLM adapter with retry logic, budgets and an ordered provider chain.

Any OpenAI-compatible endpoint works (local Ollama/llama.cpp/vLLM, Groq,
OpenRouter, Gemini, OpenAI); see ``services.llm_providers`` for the env
variables. Providers are tried in order, then the template fallback.
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
from services.llm_providers import ProviderConfig, resolve_provider_chain
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
    """Provider-chain adapter with retry logic and budget management"""
    
    def __init__(self, providers: Optional[List[ProviderConfig]] = None):
        self.config = get_config()
        if providers is None:
            providers, skipped = resolve_provider_chain()
            for reason in skipped:
                logger.warning(f"LLM provider skipped: {reason}")
        self.providers = list(providers)
        self.clients = {
            p.name: openai.AsyncOpenAI(api_key=p.api_key, base_url=p.base_url)
            for p in self.providers
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
    async def _call_provider(
        self,
        provider: ProviderConfig,
        chat_messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        start_time = time.time()
        response = await self.clients[provider.name].chat.completions.create(
            model=provider.model,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        duration = time.time() - start_time
        usage = getattr(response, "usage", None)
        tokens = getattr(usage, "total_tokens", "?") if usage else "?"
        logger.info(
            f"LLM call via {provider.name}/{provider.model} completed in {duration:.2f}s, tokens: {tokens}"
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError(f"{provider.name} returned an empty completion")
        return content

    async def chat(
        self, 
        system: str, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Chat completion across the provider chain with budget management.

        Each provider gets its own retries on rate limits/timeouts; any
        remaining failure moves to the next provider, then to templates.
        """
        if not self._check_budget():
            if self.template_fallback_enabled:
                logger.info("Budget exceeded, falling back to template-only generation")
                self.last_provider = "template"
                return self._template_fallback(system, messages)
            raise Exception("LLM budget exceeded and template fallback disabled")

        chat_messages = [{"role": "system", "content": system}]
        chat_messages.extend(messages)
        limit = max_tokens or self.budget.max_tokens_per_call

        last_error: Optional[Exception] = None
        for provider in self.providers:
            try:
                reply = await self._call_provider(provider, chat_messages, temperature, limit)
            except Exception as e:
                last_error = e
                logger.warning(f"LLM provider {provider.name} failed, trying next: {e}")
                continue
            self._increment_budget()
            self.last_provider = provider.name
            return reply

        if self.template_fallback_enabled:
            self.last_provider = "template"
            return self._template_fallback(system, messages)
        if last_error is not None:
            raise last_error
        raise Exception("no LLM provider configured and template fallback disabled")
    
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
            "providers": [
                {"name": p.name, "model": p.model, "open_weights": p.open_weights}
                for p in self.providers
            ],
            "last_provider": self.last_provider,
        }
