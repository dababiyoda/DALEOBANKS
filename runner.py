"""
Background job scheduler for DaLeoBanks AI Agent
Orchestrates 24/7 autonomous operation
"""

import asyncio
import random
from datetime import datetime, timedelta, UTC
from typing import Dict, Any, Optional
import traceback

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import get_config, subscribe_to_updates
from db.session import get_db_session, init_db
from db.models import Action
from services.multiplexer import SocialMultiplexer
from services.x_client import XClient
from services.llm_adapter import LLMAdapter
from services.generator import Generator
from services.selector import Selector
from services.analytics import AnalyticsService
from services.kpi import KPIService
from services.planner import PlannerService
from services.persona_store import PersonaStore
from services.self_model import SelfModelService
from services.optimizer import Optimizer
from services.reflection import ReflectionService
from services.logging_utils import get_logger
from services.crisis import CrisisService
from services.perception import PerceptionService

logger = get_logger(__name__)

# Global scheduler
scheduler: Optional[AsyncIOScheduler] = None
start_time = datetime.now(UTC)

# Services
config = get_config()
persona_store = PersonaStore()
x_client = XClient()
multiplexer = SocialMultiplexer(config=config, x_client=x_client)
llm_adapter = LLMAdapter()
generator = Generator(persona_store, llm_adapter)
selector = Selector(persona_store)
analytics_service = AnalyticsService()
kpi_service = KPIService()
reflection_service = ReflectionService()
planner_service = PlannerService()
self_model_service = SelfModelService(persona_store)
optimizer = Optimizer()
perception_service = PerceptionService()
crisis_service = CrisisService()

# Track pagination cursors for perception ingest to avoid refetching.
_perception_state: Dict[str, Any] = {}


def _on_config_update(cfg, changes: Dict[str, Any]) -> None:
    if "LIVE" in changes:
        logger.info("Runner observed LIVE toggle -> %s", "on" if cfg.LIVE else "off")


_unsubscribe = subscribe_to_updates(_on_config_update)

async def start_scheduler():
    """Start the background scheduler"""
    global scheduler
    
    if scheduler and scheduler.running:
        return
    
    scheduler = AsyncIOScheduler()
    
    # Add jobs with random jitter
    await _add_jobs()
    
    scheduler.start()
    logger.info("Background scheduler started")

async def stop_scheduler():
    """Stop the background scheduler"""
    global scheduler
    
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped")

async def _add_jobs():
    """Add all scheduled jobs"""
    
    # Proposal posting job
    scheduler.add_job(
        post_proposal_job,
        IntervalTrigger(
            minutes=random.randint(*config.POST_TWEET_EVERY),
            jitter=300  # 5 minute jitter
        ),
        id='post_proposal',
        max_instances=1
    )
    
    # Reply to mentions job
    scheduler.add_job(
        reply_mentions_job,
        IntervalTrigger(
            minutes=random.randint(*config.REPLY_MENTIONS_EVERY),
            jitter=120  # 2 minute jitter
        ),
        id='reply_mentions',
        max_instances=1
    )
    
    # Search and engage job
    scheduler.add_job(
        search_and_engage_job,
        IntervalTrigger(
            minutes=random.randint(*config.SEARCH_ENGAGE_EVERY),
            jitter=180  # 3 minute jitter
        ),
        id='search_engage',
        max_instances=1
    )

    # Perception ingest job
    scheduler.add_job(
        perception_job,
        IntervalTrigger(minutes=15, jitter=60),
        id='perception_ingest',
        max_instances=1
    )

    # Crisis monitoring job
    scheduler.add_job(
        crisis_watch_job,
        IntervalTrigger(minutes=5, jitter=30),
        id='crisis_watch',
        max_instances=1
    )
    
    # Analytics pull job
    scheduler.add_job(
        analytics_pull_job,
        IntervalTrigger(
            minutes=random.randint(*config.ANALYTICS_PULL_EVERY),
            jitter=300
        ),
        id='analytics_pull',
        max_instances=1
    )
    
    # KPI rollup job
    scheduler.add_job(
        kpi_rollup_job,
        IntervalTrigger(
            minutes=random.randint(*config.KPI_ROLLUP_EVERY),
            jitter=600
        ),
        id='kpi_rollup',
        max_instances=1
    )
    
    # Daily follower snapshot
    scheduler.add_job(
        follower_snapshot_job,
        CronTrigger(hour=config.FOLLOWER_SNAPSHOT_DAILY_HOUR),
        id='follower_snapshot',
        max_instances=1
    )
    
    # Nightly reflection
    scheduler.add_job(
        nightly_reflection_job,
        CronTrigger(hour=config.NIGHTLY_REFLECTION_HOUR),
        id='nightly_reflection',
        max_instances=1
    )
    
    # Weekly planning
    scheduler.add_job(
        weekly_planning_job,
        CronTrigger(day_of_week='sun', hour=5),  # Sunday at 5 AM
        id='weekly_planning',
        max_instances=1
    )

async def post_proposal_job():
    """Generate and post a proposal tweet"""
    try:
        if not crisis_service.guard(action="post_proposal"):
            return

        # Get next action from selector
        action = await selector.decide_next_action()

        if action.get("type") != "POST_PROPOSAL":
            logger.info("Selector chose different action, skipping proposal")
            return

        # Generate proposal
        topic = action.get("topic", "general")
        intensity = action.get("intensity", config.MIN_INTENSITY_LEVEL)
        result = await generator.make_proposal(topic, intensity)

        if "error" in result:
            logger.error(f"Proposal generation failed: {result['error']}")
            return

        publish_result = await multiplexer.publish(
            result["content"],
            kind="post",
            intensity=intensity,
            metadata={"topic": topic},
        )

        x_result = publish_result.get("x")

        if x_result and not x_result.dry_run:
            # Store in database
            with get_db_session() as session:
                from db.models import Tweet

                tweet = Tweet(
                    id=x_result.post_id,
                    text=result["content"],
                    kind="proposal",
                    topic=topic,
                    hour_bin=action.get("hour_bin"),
                    cta_variant=action.get("cta_variant"),
                    intensity=action.get("intensity"),
                )
                session.add(tweet)
                session.commit()

                arm_metadata = action.get("arm_metadata") or {}
                optimizer.experiments.log_arm_selection(
                    session,
                    tweet_id=x_result.post_id,
                    post_type=arm_metadata.get("post_type", "proposal"),
                    topic=topic,
                    hour_bin=action.get("hour_bin", datetime.now().hour),
                    cta_variant=action.get("cta_variant", "learn_more"),
                    intensity=action.get("intensity"),
                    sampled_prob=arm_metadata.get("sampled_prob", 0.5),
                )

            # Log action
            await _log_action("proposal_posted", {
                "tweet_id": x_result.post_id,
                "topic": topic,
                "character_count": len(result["content"])
            })

            logger.info(f"Posted proposal: {x_result.post_id}")
        else:
            logger.info("DRY RUN - Proposal would be posted", extra={"topic": topic})

    except Exception as e:
        logger.error(f"Proposal job failed: {e}")
        traceback.print_exc()

async def reply_mentions_job():
    """Reply to recent mentions"""
    try:
        if not config.LIVE or not x_client:
            logger.info("X client not available")
            return

        if not crisis_service.guard(action="reply_mentions"):
            return

        action = await selector.decide_next_action()
        if action.get("type") != "REPLY_MENTIONS":
            logger.info("Selector chose different action, skipping replies")
            return

        # Get recent mentions
        mentions = await x_client.get_mentions()
        
        if not mentions:
            logger.info("No new mentions to reply to")
            return
        
        # Process up to 3 mentions
        max_mentions = action.get("max_mentions", 3)

        for mention in mentions[:max_mentions]:
            try:
                # Generate reply
                context = {
                    "original_tweet": mention["text"],
                    "author_info": {"username": mention.get("username", "unknown")},
                    "topic": "reply"
                }
                
                intensity = action.get("intensity", config.MIN_INTENSITY_LEVEL)
                result = await generator.make_reply(context, intensity)
                
                if "error" in result:
                    logger.warning(f"Reply generation failed: {result['error']}")
                    continue
                
                publish_result = await multiplexer.publish(
                    result["content"],
                    kind="reply",
                    in_reply_to=mention["id"],
                    intensity=intensity,
                )

                reply_result = publish_result.get("x")

                if reply_result and not reply_result.dry_run:
                    # Store in database
                    with get_db_session() as session:
                        from db.models import Tweet
                        tweet = Tweet(
                            id=reply_result.post_id,
                            text=result["content"],
                            kind="reply",
                            ref_tweet_id=mention["id"],
                            intensity=intensity,
                        )
                        session.add(tweet)
                        session.commit()

                    await _log_action("mention_replied", {
                        "reply_id": reply_result.post_id,
                        "original_id": mention["id"]
                    })

                    logger.info(f"Replied to mention: {reply_result.post_id}")
                else:
                    logger.info(f"DRY RUN - Would reply: {result['content'][:100]}...")

            except Exception as e:
                logger.error(f"Failed to reply to mention {mention['id']}: {e}")
        
    except Exception as e:
        logger.error(f"Reply mentions job failed: {e}")

async def search_and_engage_job():
    """Search for relevant content and engage"""
    try:
        if not config.LIVE or not x_client:
            logger.info("X client not available")
            return

        if not crisis_service.guard(action="search_engage"):
            return

        action = await selector.decide_next_action()
        if action.get("type") != "SEARCH_ENGAGE":
            logger.info("Selector chose different action, skipping search")
            return

        search_terms = action.get("search_terms", ["mechanisms", "coordination"])
        intensity = action.get("intensity", config.MIN_INTENSITY_LEVEL)

        for term in search_terms:
            try:
                tweets = await x_client.search_recent(f"{term} -is:retweet", max_results=5)

                for tweet in tweets:
                    relevance = _calculate_relevance(tweet["text"], term)

                    if relevance >= 4:
                        if config.ENABLE_LIKES and random.random() < 0.8:
                            await x_client.like(tweet["id"])
                            await _log_action("tweet_liked", {"tweet_id": tweet["id"], "term": term})

                        if config.ENABLE_REPOSTS and random.random() < 0.3:
                            await x_client.repost(tweet["id"])
                            await _log_action("tweet_retweeted", {"tweet_id": tweet["id"], "term": term})

                        if config.ENABLE_QUOTES and random.random() < 0.2:
                            context = {"original_tweet": tweet["text"], "topic": term}
                            result = await generator.make_quote(context, intensity)

                            if "error" not in result:
                                publish_result = await multiplexer.publish(
                                    result["content"],
                                    kind="quote",
                                    quote_to=tweet["id"],
                                    intensity=intensity,
                                )
                                quote_result = publish_result.get("x")
                                if quote_result and not quote_result.dry_run:
                                    await _log_action(
                                        "quote_tweeted",
                                        {"quote_id": quote_result.post_id, "original_id": tweet["id"]},
                                    )

            except Exception as e:
                logger.error(f"Search engagement failed for term '{term}': {e}")

    except Exception as e:
        logger.error(f"Search and engage job failed: {e}")


async def perception_job():
    """Run the perception ingest loop."""
    global _perception_state

    try:
        with get_db_session() as session:
            total = await perception_service.ingest(
                session,
                x_client=x_client if x_client and x_client.is_healthy() else None,
                since_id=_perception_state.get("x_mentions_since_id"),
                timeline_token=_perception_state.get("x_timeline_token"),
            )
            _perception_state = perception_service.last_state
        payload = perception_service.last_payload
        counts = perception_service.last_counts
        mentions = payload.get("x", {}).get("mentions", []) if isinstance(payload, dict) else []
        mention_velocity = counts.get("x_mentions") if isinstance(counts, dict) else None
        if mentions or mention_velocity:
            await crisis_service.evaluate_mentions(
                mentions,
                multiplexer=multiplexer,
                velocity=mention_velocity,
            )
        logger.info(
            "perception_job_completed",
            extra={"total": total, "state": _perception_state},
        )
        return total
    except Exception as e:
        logger.error(f"Perception job failed: {e}")
        return 0


async def crisis_watch_job():
    """Monitor crisis status and log current mode."""
    if crisis_service.is_paused():
        logger.info("crisis_watch status=PAUSED reason=%s", crisis_service.reason)
    else:
        logger.info("crisis_watch status=NORMAL")

async def analytics_pull_job():
    """Pull analytics and update metrics"""
    try:
        result: Dict[str, Any] | None = None
        with get_db_session() as session:
            result = await analytics_service.pull_and_update_metrics(session, x_client)
            optimizer.experiments.update_arm_rewards(session)
            selector.record_outcome(result)
            await _log_action("analytics_updated", result)
            logger.info(f"Analytics updated: {result}")

        if result is not None:
            await crisis_service.update_metrics(
                source="analytics",
                multiplexer=multiplexer,
                authority=result.get("authority"),
                velocity=result.get("updated_count"),
                metadata={"j_score": result.get("j_score")},
            )

    except Exception as e:
        logger.error(f"Analytics pull job failed: {e}")

async def kpi_rollup_job():
    """Calculate and store KPIs"""
    try:
        with get_db_session() as session:
            # Calculate KPIs for the last hour
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=1)
            
            kpi_service.calculate_and_store_kpis(session, start_time, end_time)
            await _log_action("kpis_calculated", {"period": "1h"})
            logger.info("KPIs calculated and stored")
            
    except Exception as e:
        logger.error(f"KPI rollup job failed: {e}")

async def follower_snapshot_job():
    """Take daily follower count snapshot"""
    try:
        if not x_client:
            logger.info("X client not available for follower snapshot")
            return
        
        # Get current user info to get follower count
        # This would require additional API call in real implementation
        # For now, we'll estimate or use a placeholder
        follower_count = 1000  # Placeholder
        
        with get_db_session() as session:
            analytics_service.create_follower_snapshot(session, follower_count)
            await _log_action("follower_snapshot", {"count": follower_count})
            logger.info(f"Follower snapshot created: {follower_count}")
            
    except Exception as e:
        logger.error(f"Follower snapshot job failed: {e}")

async def nightly_reflection_job():
    """Perform nightly reflection and generate improvement note"""
    try:
        with get_db_session() as session:
            improvement_note = reflection_service.generate_reflection(session)
            await _log_action("nightly_reflection", {"note": improvement_note})
            logger.info(f"Nightly reflection completed: {improvement_note}")

    except Exception as e:
        logger.error(f"Nightly reflection job failed: {e}")

async def weekly_planning_job():
    """Perform weekly planning and update OKRs"""
    try:
        with get_db_session() as session:
            plan = await planner_service.create_weekly_plan(session)
            await _log_action("weekly_planning", plan)
            logger.info("Weekly planning completed")
            
            # Update self-model
            await self_model_service.update_self_model()
            
    except Exception as e:
        logger.error(f"Weekly planning job failed: {e}")

async def initial_activity():
    """Perform initial activity when starting in LIVE mode"""
    try:
        if not config.LIVE or not x_client:
            return
        
        logger.info("Performing initial activity...")
        
        # Post one proposal within 5 minutes
        await asyncio.sleep(random.randint(60, 300))  # 1-5 minutes
        await post_proposal_job()
        
        # Reply to 2 mentions
        await asyncio.sleep(random.randint(30, 120))  # 30s-2min
        await reply_mentions_job()
        
        logger.info("Initial activity completed")
        
    except Exception as e:
        logger.error(f"Initial activity failed: {e}")

def _calculate_relevance(text: str, term: str) -> int:
    """Calculate relevance score (1-10) for a tweet"""
    text_lower = text.lower()
    term_lower = term.lower()
    
    score = 0
    
    # Direct term match
    if term_lower in text_lower:
        score += 3
    
    # Related keywords
    related_keywords = {
        "mechanisms": ["system", "process", "framework", "structure"],
        "coordination": ["collaborate", "organize", "align", "sync"],
        "energy": ["power", "fuel", "renewable", "efficiency"],
        "policy": ["regulation", "law", "governance", "rule"]
    }
    
    keywords = related_keywords.get(term_lower, [])
    for keyword in keywords:
        if keyword in text_lower:
            score += 1
    
    # Question marks (indicates discussion potential)
    if "?" in text:
        score += 1
    
    # Length check (substantial content)
    if len(text) > 100:
        score += 1
    
    return min(score, 10)

async def _log_action(kind: str, meta: Dict[str, Any]):
    """Log an action to the database"""
    try:
        with get_db_session() as session:
            action = Action(kind=kind, meta_json=meta)
            session.add(action)
            session.commit()
    except Exception as e:
        logger.error(f"Failed to log action {kind}: {e}")

def get_uptime() -> str:
    """Get system uptime"""
    uptime = datetime.now(UTC) - start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    return f"{hours}h {minutes}m"

def get_scheduler_status() -> Dict[str, Any]:
    """Get scheduler status"""
    if not scheduler:
        return {"running": False}
    
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "next_run": next_run.isoformat() if next_run else None
        })
    
    return {
        "running": scheduler.running,
        "jobs": jobs,
        "uptime": get_uptime()
    }
