"""
Memory management for episodic, semantic, procedural, and social memory
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, UTC

from db.models import Note, Action, Tweet, Relationship
from db.session import get_db_session
from services.logging_utils import get_logger
from services.semantic_index import get_semantic_index
from services.sentiment import SentimentService

logger = get_logger(__name__)

class MemoryService:
    """Manages different types of memory for the AI agent"""

    def __init__(self):
        self.max_improvement_notes = 100
        self.prompt_notes_limit = 30
        self.max_relationship_topics = 10
        self.semantic_index = get_semantic_index()
        self.sentiment = SentimentService()
    
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
    
    def record_interaction(
        self,
        session: Any,
        *,
        user_id: str,
        handle: Optional[str] = None,
        kind: str = "mention",
        topic: Optional[str] = None,
        text: Optional[str] = None,
    ) -> Relationship:
        """Upsert a relationship record for an account we interacted with."""
        user_id = str(user_id)
        rel = (
            session.query(Relationship)
            .filter(lambda r: r.id == user_id)
            .first()
        )
        if rel is None:
            rel = Relationship(id=user_id, handle=handle)
            session.add(rel)

        rel.interaction_count += 1
        rel.last_interaction_at = datetime.now(UTC)
        if handle:
            rel.handle = handle
        rel.kinds[kind] = rel.kinds.get(kind, 0) + 1
        if topic and topic not in rel.topics:
            rel.topics.append(topic)
            rel.topics = rel.topics[-self.max_relationship_topics:]
        if text:
            score = self.sentiment.analyze_sentiment(text).get("score", 0.0)
            count = rel.interaction_count
            rel.sentiment_score = round(
                (rel.sentiment_score * (count - 1) + score) / count, 3
            )
        session.commit()

        # Associative copy so "what do I know about this person" is recallable.
        try:
            summary = f"{rel.handle or user_id} {kind}"
            if topic:
                summary += f" about {topic}"
            if text:
                summary += f": {text[:120]}"
            self.semantic_index.add(summary, meta={"kind": "social", "user_id": user_id})
        except Exception as exc:
            logger.error(f"Failed to index interaction: {exc}")

        return rel

    def get_relationship(self, session: Any, user_id: str) -> Optional[Relationship]:
        """Fetch the relationship record for a single account, if any."""
        user_id = str(user_id)
        return (
            session.query(Relationship)
            .filter(lambda r: r.id == user_id)
            .first()
        )

    def get_social_memory(self, session: Any) -> Dict[str, Any]:
        """Get social context and relationships"""
        relationships = (
            session.query(Relationship)
            .order_by(lambda r: r.last_interaction_at, descending=True)
            .limit(100)
            .all()
        )

        influential = sorted(
            relationships, key=lambda r: r.interaction_count, reverse=True
        )[:10]

        allies = [r for r in relationships if r.sentiment_score > 0.2 and r.interaction_count >= 2]
        critics = [r for r in relationships if r.sentiment_score < -0.2 and r.interaction_count >= 2]
        new_contacts = [r for r in relationships if r.interaction_count == 1]

        topic_communities: Dict[str, List[str]] = {}
        for rel in relationships:
            label = rel.handle or rel.id
            for topic in rel.topics:
                topic_communities.setdefault(topic, []).append(label)

        def _summarize(rels: List[Relationship]) -> List[Dict[str, Any]]:
            return [
                {
                    "id": r.id,
                    "handle": r.handle,
                    "interactions": r.interaction_count,
                    "sentiment": r.sentiment_score,
                    "topics": list(r.topics),
                }
                for r in rels
            ]

        return {
            "influential_interactions": _summarize(influential),
            "follower_segments": {
                "allies": _summarize(allies[:10]),
                "critics": _summarize(critics[:10]),
                "new_contacts": _summarize(new_contacts[:10]),
            },
            "topic_communities": topic_communities,
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

        # Durable associative copy: the DB prunes old notes, the semantic
        # index keeps every lesson recallable by similarity.
        try:
            self.semantic_index.add(text, meta={"kind": "improvement_note"})
        except Exception as exc:
            logger.error(f"Failed to index improvement note: {exc}")

        logger.info(f"Added improvement note: {text[:100]}...")
        return note.id

    def search_similar_lessons(self, query: str, k: int = 5) -> List[str]:
        """Recall past lessons associatively related to ``query``."""
        try:
            return [r["text"] for r in self.semantic_index.search(query, k=k)]
        except Exception as exc:
            logger.error(f"Semantic lesson search failed: {exc}")
            return []
    
    def get_recent_improvement_notes(self, session: Any) -> List[str]:
        """Get recent improvement notes for prompting"""
        notes = (
            session.query(Note)
            .order_by(lambda note: note.created_at, descending=True)
            .limit(self.prompt_notes_limit)
            .all()
        )
        
        return [note.text for note in notes]
    
    def get_context_for_generation(self, session: Any, topic: Optional[str] = None) -> Dict[str, Any]:
        """Get relevant context for content generation"""
        context = {
            "recent_actions": self.get_episodic_memory(session, hours=12),
            "learned_patterns": self.get_semantic_memory(session),
            "procedures": self.get_procedural_memory(),
            "social_context": self.get_social_memory(session),
            "improvement_notes": self.get_recent_improvement_notes(session)
        }
        if topic:
            context["associative_lessons"] = self.search_similar_lessons(topic, k=3)
            try:
                from services.world_model import get_world_model
                context["world_context"] = [
                    r["text"] for r in get_world_model().recall(topic, k=3)
                ]
            except Exception as exc:
                logger.error(f"World model recall failed: {exc}")
                context["world_context"] = []
        return context
