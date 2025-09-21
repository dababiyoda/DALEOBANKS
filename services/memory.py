"""
Memory management for episodic, semantic, procedural, and social memory
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, UTC

from db.models import Note, Action, Tweet
from db.session import get_db_session
from services.logging_utils import get_logger

logger = get_logger(__name__)

class MemoryService:
    """Manages different types of memory for the AI agent"""
    
    def __init__(self):
        self.max_improvement_notes = 100
        self.prompt_notes_limit = 30
    
    def get_episodic_memory(self, session: Any, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent episodic memories (actions and events)"""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        
        actions = (
            session.query(Action)
            .filter(lambda action: action.created_at >= cutoff)
            .order_by(lambda action: action.created_at, descending=True)
            .all()
        )
        
        memories = []
        for action in actions:
            memories.append({
                "type": "action",
                "kind": action.kind,
                "timestamp": action.created_at,
                "details": action.meta_json
            })
        
        return memories
    
    def get_semantic_memory(self, session: Any) -> Dict[str, Any]:
        """Get semantic knowledge (facts, beliefs, patterns)"""
        # Get recent high-performing tweets for pattern analysis
        recent_tweets = (
            session.query(Tweet)
            .filter(lambda tweet: tweet.created_at >= datetime.now(UTC) - timedelta(days=7))
            .order_by(lambda tweet: tweet.j_score if tweet.j_score is not None else 0, descending=True)
            .limit(10)
            .all()
        )
        
        patterns = {
            "high_performing_topics": [],
            "effective_cta_variants": [],
            "optimal_posting_hours": []
        }
        
        for tweet in recent_tweets:
            if tweet.topic:
                patterns["high_performing_topics"].append(tweet.topic)
            if tweet.cta_variant:
                patterns["effective_cta_variants"].append(tweet.cta_variant)
            if tweet.hour_bin:
                patterns["optimal_posting_hours"].append(tweet.hour_bin)
        
        return patterns
    
    def get_procedural_memory(self) -> Dict[str, Any]:
        """Get procedural knowledge (how-to knowledge)"""
        return {
            "proposal_structure": "Problem → Mechanism → Pilot → KPIs → Risks → CTA",
            "reply_structure": "Illuminate gap → Concrete mechanism → One next step",
            "engagement_strategies": [
                "Ask concrete questions",
                "Provide actionable next steps",
                "Include uncertainty quantification",
                "End with clear CTA"
            ]
        }
    
    def get_social_memory(self, session: Any) -> Dict[str, Any]:
        """Get social context and relationships"""
        # This would track follower interactions, influential accounts, etc.
        # For now, return basic structure
        return {
            "influential_interactions": [],
            "follower_segments": [],
            "topic_communities": []
        }
    
    def add_improvement_note(self, session: Any, text: str) -> str:
        """Add an improvement note and manage the collection size"""
        # Add new note
        note = Note(text=text)
        session.add(note)
        
        # Clean up old notes if we exceed the limit
        total_notes = session.query(Note).count()
        if total_notes >= self.max_improvement_notes:
            # Keep only the most recent notes
            old_notes = (
                session.query(Note)
                .order_by(lambda note: note.created_at)
                .limit(total_notes - self.max_improvement_notes + 1)
                .all()
            )
            
            for old_note in old_notes:
                session.delete(old_note)
        
        session.commit()
        logger.info(f"Added improvement note: {text[:100]}...")
        return note.id
    
    def get_recent_improvement_notes(self, session: Any) -> List[str]:
        """Get recent improvement notes for prompting"""
        notes = (
            session.query(Note)
            .order_by(lambda note: note.created_at, descending=True)
            .limit(self.prompt_notes_limit)
            .all()
        )
        
        return [note.text for note in notes]
    
    def get_context_for_generation(self, session: Any) -> Dict[str, Any]:
        """Get relevant context for content generation"""
        return {
            "recent_actions": self.get_episodic_memory(session, hours=12),
            "learned_patterns": self.get_semantic_memory(session),
            "procedures": self.get_procedural_memory(),
            "social_context": self.get_social_memory(session),
            "improvement_notes": self.get_recent_improvement_notes(session)
        }
