"""
Content generation with persona integration and duplicate prevention
"""

import hashlib
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio


from services.persona_store import PersonaStore
from services.llm_adapter import LLMAdapter
from services.ethics_guard import EthicsGuard
from services.critic import Critic
from services.memory import MemoryService
from services.logging_utils import get_logger
from db.session import get_db_session
from db.models import Tweet
from config import get_config

logger = get_logger(__name__)


def levenshtein_distance(a: str, b: str) -> int:
    """Compute the Levenshtein distance between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i]
        for j, char_b in enumerate(b, start=1):
            insert_cost = current_row[j - 1] + 1
            delete_cost = previous_row[j] + 1
            replace_cost = previous_row[j - 1] + (char_a != char_b)
            current_row.append(min(insert_cost, delete_cost, replace_cost))
        previous_row = current_row

    return previous_row[-1]


class Generator:
    """Content generation with persona-driven prompting"""
    
    def __init__(self, persona_store: PersonaStore, llm_adapter: LLMAdapter):
        self.persona_store = persona_store
        self.llm_adapter = llm_adapter
        self.ethics_guard = EthicsGuard()
        self.critic = Critic()
        self.memory = MemoryService()
        self.config = get_config()

        # Duplicate detection settings
        self.duplicate_check_days = 30
        self.similarity_threshold = 0.8
        self.max_mutation_attempts = 3
    
    async def make_proposal(self, topic: str = "general", intensity: int = 1) -> Dict[str, Any]:
        """Generate a proposal tweet"""
        try:
            with get_db_session() as session:
                # Get context from memory
                context = self.memory.get_context_for_generation(session)
                
                # Build system prompt
                system_prompt = self.persona_store.build_system_prompt(
                    context["improvement_notes"]
                )
                
                # Prepare user message
                user_message = self._build_proposal_prompt(topic, context, intensity)
                
                # Generate content
                content = await self.llm_adapter.chat(
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    temperature=0.7
                )
                
                # Validate and refine
                return await self._validate_and_refine(content, "proposal", topic, session, intensity)
                
        except Exception as e:
            logger.error(f"Proposal generation failed: {e}")
            return {"error": str(e)}
    
    async def make_reply(self, context: Dict[str, Any], intensity: int = 1) -> Dict[str, Any]:
        """Generate a reply to a mention or tweet"""
        try:
            with get_db_session() as session:
                # Get memory context
                memory_context = self.memory.get_context_for_generation(session)
                
                # Build system prompt
                system_prompt = self.persona_store.build_system_prompt(
                    memory_context["improvement_notes"]
                )
                
                # Prepare user message
                user_message = self._build_reply_prompt(context, memory_context, intensity)
                
                # Generate content
                content = await self.llm_adapter.chat(
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    temperature=0.6
                )
                
                # Validate and refine
                return await self._validate_and_refine(content, "reply", context.get("topic", "general"), session, intensity)
                
        except Exception as e:
            logger.error(f"Reply generation failed: {e}")
            return {"error": str(e)}
    
    async def make_quote(self, context: Dict[str, Any], intensity: int = 1) -> Dict[str, Any]:
        """Generate a quote tweet"""
        try:
            with get_db_session() as session:
                # Get memory context
                memory_context = self.memory.get_context_for_generation(session)
                
                # Build system prompt
                system_prompt = self.persona_store.build_system_prompt(
                    memory_context["improvement_notes"]
                )
                
                # Prepare user message
                user_message = self._build_quote_prompt(context, memory_context, intensity)
                
                # Generate content
                content = await self.llm_adapter.chat(
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    temperature=0.6
                )
                
                # Validate and refine
                return await self._validate_and_refine(content, "quote", context.get("topic", "general"), session, intensity)
                
        except Exception as e:
            logger.error(f"Quote generation failed: {e}")
            return {"error": str(e)}
    
    def _build_proposal_prompt(self, topic: str, context: Dict[str, Any], intensity: int) -> str:
        """Build prompt for proposal generation"""
        persona = self.persona_store.get_current_persona()
        template = persona.get("templates", {}).get("tweet", "")
        
        prompt = f"""Generate a proposal tweet about {topic}.

Template to follow: {template}

Recent patterns that worked well:
{json.dumps(context.get("learned_patterns", {}), indent=2)}

Requirements:
- Must contain: Problem, Mechanism, Pilot, KPIs, Risks, CTA
- Maximum 280 characters
- Include uncertainty and rollback plan
- End with actionable CTA
- Be specific and concrete
- Intensity level: {intensity} on scale 0-5

Topic focus: {topic}"""
        
        return prompt
    
    def _build_reply_prompt(self, context: Dict[str, Any], memory_context: Dict[str, Any], intensity: int) -> str:
        """Build prompt for reply generation"""
        persona = self.persona_store.get_current_persona()
        template = persona.get("templates", {}).get("reply", "")
        
        original_tweet = context.get("original_tweet", "")
        author_info = context.get("author_info", {})
        
        prompt = f"""Generate a reply to this tweet:

Original tweet: "{original_tweet}"
Author: {author_info.get("username", "unknown")} (followers: {author_info.get("followers", 0)})

Template to follow: {template}

Tone rules:
- {persona.get("tone_rules", {}).get("people", "Be respectful")}

Requirements:
- Maximum 280 characters
- Illuminate gap, suggest mechanism, provide next step
- Be constructive and helpful
- No self-promotion unless directly relevant
- Intensity level: {intensity} on scale 0-5"""
        
        return prompt
    
    def _build_quote_prompt(self, context: Dict[str, Any], memory_context: Dict[str, Any], intensity: int) -> str:
        """Build prompt for quote tweet generation"""
        original_tweet = context.get("original_tweet", "")
        
        prompt = f"""Generate a quote tweet commenting on:

Original tweet: "{original_tweet}"

Requirements:
- Maximum 200 characters (leaving room for quoted tweet)
- Add valuable perspective or mechanism
- Build on the original idea constructively
- Include actionable insight
- Intensity level: {intensity} on scale 0-5"""
        
        return prompt
    
    async def _validate_and_refine(self, content: str, content_type: str, topic: str, session, intensity: int) -> Dict[str, Any]:
        """Validate content and refine if needed"""
        # Ethics check
        ethics_result = self.ethics_guard.validate_text(content)
        if not ethics_result.approved:
            logger.warning(f"Content failed ethics check: {ethics_result.reasons}")
            return {"error": "Content failed ethics validation", "reasons": ethics_result.reasons}
        
        # Enforce uncertainty/rollback addendum for proposals
        if content_type == "proposal":
            content = self.ethics_guard.enforce_addendum(content, content_type)
        
        # Critic completeness check for proposals
        if content_type == "proposal":
            is_complete, missing = self.critic.check_completeness(content)
            if not is_complete:
                logger.warning(f"Proposal missing elements: {missing}")
                return {"error": "Proposal incomplete", "missing_elements": missing}
        
        # Character limit check (280 chars, accounting for t.co links as 23 chars)
        if len(content) > 280:
            logger.warning(f"Content too long: {len(content)} chars")
            content = content.strip()
            if len(content) > 280:
                content = content[:277].rstrip() + "..."

        # Duplicate check
        is_duplicate, similar_tweet = self._check_for_duplicates(content, session)
        if is_duplicate:
            logger.info("Duplicate detected, attempting mutation")
            content = await self._mutate_content(content, similar_tweet)
            
            # Re-check after mutation
            is_duplicate, _ = self._check_for_duplicates(content, session)
            if is_duplicate:
                return {"error": "Unable to generate unique content after mutation"}

        if intensity >= 3 and self.config.RAGEBAIT_GUARD:
            if not (self.ethics_guard.has_receipt(content) and self.ethics_guard.has_constructive_step(content)):
                return {"error": "High-intensity content requires a citation and constructive next step"}

        return {
            "content": content,
            "content_type": content_type,
            "topic": topic,
            "intensity": intensity,
            "character_count": len(content),
            "ethics_score": ethics_result.uncertainty_score,
            "hash": hashlib.sha256(content.encode()).hexdigest()[:16]
        }
    
    def _check_for_duplicates(self, content: str, session) -> tuple[bool, Optional[str]]:
        """Check for duplicate content in recent tweets"""
        # Get recent tweets for comparison
        cutoff = datetime.utcnow() - timedelta(days=self.duplicate_check_days)
        recent_tweets = (
            session.query(Tweet)
            .filter(lambda tweet: tweet.created_at >= cutoff)
            .all()
        )
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        for tweet in recent_tweets:
            # Exact hash match
            tweet_hash = hashlib.sha256(tweet.text.encode()).hexdigest()
            if content_hash == tweet_hash:
                return True, tweet.text
            
            # Similarity check using Levenshtein distance
            similarity = 1 - (levenshtein_distance(content, tweet.text) / max(len(content), len(tweet.text)))
            if similarity > self.similarity_threshold:
                return True, tweet.text
        
        return False, None
    
    async def _mutate_content(self, content: str, similar_content: str) -> str:
        """Mutate content to make it unique while preserving meaning"""
        mutation_prompt = f"""The following content is too similar to existing content. Please rephrase it to be unique while preserving the core message and structure:

Original: {content}

Similar existing content: {similar_content}

Requirements:
- Keep the same core message and structure
- Change wording and phrasing significantly
- Maintain the same character limit
- Preserve any KPIs, mechanisms, and CTAs"""
        
        try:
            mutated = await self.llm_adapter.chat(
                system="You are an expert at rephrasing content while preserving meaning.",
                messages=[{"role": "user", "content": mutation_prompt}],
                temperature=0.8
            )
            return mutated.strip()
        except Exception as e:
            logger.error(f"Content mutation failed: {e}")
            # Simple word substitution fallback
            return content.replace("implement", "deploy").replace("mechanism", "system").replace("solution", "approach")
