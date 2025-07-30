"""
Weekly planning and OKR management
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from services.llm_adapter import LLMAdapter
from services.memory import MemoryService
from services.analytics import AnalyticsService
from services.kpi import KPIService
from services.persona_store import PersonaStore
from services.logging_utils import get_logger
from db.models import Note

logger = get_logger(__name__)

class PlannerService:
    """Weekly planning and strategic OKR management"""
    
    def __init__(self):
        self.memory = MemoryService()
        self.analytics = AnalyticsService()
        self.kpi_service = KPIService()
        
        # Default OKR template
        self.default_okr = {
            "objective": "Execute 1 pilot mechanism within 30 days",
            "key_results": [
                "Generate 6 high-quality proposal posts",
                "Conduct 3 coalition-building calls",
                "Publish 2 concrete artifacts (frameworks/tools)"
            ],
            "period_days": 30
        }
    
    async def create_weekly_plan(self, session: Session) -> Dict[str, Any]:
        """Create comprehensive weekly plan with OKRs and tactics"""
        try:
            # Analyze current performance
            performance_analysis = await self._analyze_recent_performance(session)
            
            # Generate strategic plan
            strategic_plan = await self._generate_strategic_plan(session, performance_analysis)
            
            # Create tactical tasks
            tactical_tasks = await self._generate_tactical_tasks(session, strategic_plan)
            
            # Update OKRs
            updated_okrs = await self._update_okrs(session, performance_analysis)
            
            # Store planning note
            plan_summary = f"Weekly plan: {strategic_plan.get('focus', 'general')} focus, {len(tactical_tasks)} tasks, OKR progress: {updated_okrs.get('progress', 0)}%"
            self.memory.add_improvement_note(session, plan_summary)
            
            plan = {
                "created_at": datetime.utcnow().isoformat(),
                "performance_analysis": performance_analysis,
                "strategic_plan": strategic_plan,
                "tactical_tasks": tactical_tasks,
                "updated_okrs": updated_okrs,
                "plan_summary": plan_summary
            }
            
            logger.info("Weekly plan created successfully")
            return plan
            
        except Exception as e:
            logger.error(f"Weekly planning failed: {e}")
            return {"error": str(e), "fallback_plan": self._create_fallback_plan()}
    
    async def _analyze_recent_performance(self, session: Session) -> Dict[str, Any]:
        """Analyze performance over the last week"""
        try:
            # Get KPI trends
            kpi_summary = self.kpi_service.get_kpi_summary(session)
            
            # Get weekly analytics
            weekly_trends = await asyncio.get_event_loop().run_in_executor(
                None, self.analytics.calculate_fame_score, session, 7
            )
            
            # Analyze content performance
            content_analysis = await self._analyze_content_performance(session)
            
            # Identify strengths and weaknesses
            strengths = []
            weaknesses = []
            
            # Analyze growth rates
            growth_rates = kpi_summary.get("growth_rates", {})
            for kpi, rate in growth_rates.items():
                if rate > 10:
                    strengths.append(f"{kpi} growing strongly (+{rate}%)")
                elif rate < -10:
                    weaknesses.append(f"{kpi} declining (-{abs(rate)}%)")
            
            # Analyze engagement patterns
            if content_analysis.get("avg_engagement", 0) > 50:
                strengths.append("High audience engagement")
            else:
                weaknesses.append("Low audience engagement")
            
            return {
                "kpi_summary": kpi_summary,
                "weekly_trends": weekly_trends,
                "content_analysis": content_analysis,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "overall_trajectory": "positive" if len(strengths) > len(weaknesses) else "needs_improvement"
            }
            
        except Exception as e:
            logger.error(f"Performance analysis failed: {e}")
            return {"error": str(e)}
    
    async def _analyze_content_performance(self, session: Session) -> Dict[str, Any]:
        """Analyze content performance patterns"""
        from db.models import Tweet
        
        # Get recent tweets
        cutoff = datetime.utcnow() - timedelta(days=7)
        recent_tweets = session.query(Tweet).filter(
            Tweet.created_at >= cutoff
        ).all()
        
        if not recent_tweets:
            return {"total_tweets": 0}
        
        # Calculate metrics
        total_engagement = sum(
            (tweet.likes or 0) + (tweet.rts or 0) + (tweet.replies or 0) + (tweet.quotes or 0)
            for tweet in recent_tweets
        )
        
        avg_engagement = total_engagement / len(recent_tweets)
        
        # Top performing tweets
        top_tweets = sorted(recent_tweets, key=lambda t: t.j_score or 0, reverse=True)[:3]
        
        # Topic analysis
        topic_performance = {}
        for tweet in recent_tweets:
            topic = tweet.topic or "general"
            if topic not in topic_performance:
                topic_performance[topic] = []
            topic_performance[topic].append(tweet.j_score or 0)
        
        best_topics = [
            (topic, sum(scores)/len(scores))
            for topic, scores in topic_performance.items()
        ]
        best_topics.sort(key=lambda x: x[1], reverse=True)
        
        return {
            "total_tweets": len(recent_tweets),
            "avg_engagement": avg_engagement,
            "total_engagement": total_engagement,
            "top_performing": [
                {"text": t.text[:100], "j_score": t.j_score, "topic": t.topic}
                for t in top_tweets
            ],
            "best_topics": best_topics[:3]
        }
    
    async def _generate_strategic_plan(self, session: Session, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate strategic focus and priorities"""
        try:
            # Determine strategic focus based on analysis
            strengths = analysis.get("strengths", [])
            weaknesses = analysis.get("weaknesses", [])
            trajectory = analysis.get("overall_trajectory", "stable")
            
            # Strategic focus areas
            if trajectory == "positive":
                focus = "scale_success"
                priorities = ["Double down on working strategies", "Expand successful content types", "Build on momentum"]
            else:
                focus = "course_correct"
                priorities = ["Address performance gaps", "Experiment with new approaches", "Rebuild engagement"]
            
            # Specific tactics based on content analysis
            content_analysis = analysis.get("content_analysis", {})
            best_topics = content_analysis.get("best_topics", [])
            
            if best_topics:
                top_topic = best_topics[0][0]
                priorities.append(f"Focus more on {top_topic} content")
            
            # Time allocation
            time_allocation = {
                "content_creation": 40,  # 40% of time
                "engagement": 30,        # 30% of time
                "analysis": 20,          # 20% of time
                "experimentation": 10    # 10% of time
            }
            
            if focus == "course_correct":
                # Increase experimentation when course correcting
                time_allocation["experimentation"] = 20
                time_allocation["content_creation"] = 30
            
            return {
                "focus": focus,
                "priorities": priorities,
                "time_allocation": time_allocation,
                "strategic_theme": "Deploy mechanisms that coordinate human energy toward Type-1 civilization",
                "success_metrics": ["J-score improvement", "Community engagement", "Mechanism adoption"]
            }
            
        except Exception as e:
            logger.error(f"Strategic planning failed: {e}")
            return {"focus": "maintain", "priorities": ["Continue current approach"]}
    
    async def _generate_tactical_tasks(self, session: Session, strategic_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate specific tactical tasks for the week"""
        try:
            focus = strategic_plan.get("focus", "maintain")
            priorities = strategic_plan.get("priorities", [])
            
            tasks = []
            
            # Content tasks
            if focus == "scale_success":
                tasks.extend([
                    {
                        "category": "content",
                        "task": "Create 3 proposals building on successful topics",
                        "priority": "high",
                        "estimated_hours": 4
                    },
                    {
                        "category": "content",
                        "task": "Develop thread series expanding best-performing ideas",
                        "priority": "medium",
                        "estimated_hours": 3
                    }
                ])
            else:
                tasks.extend([
                    {
                        "category": "content",
                        "task": "Experiment with 2 new content formats",
                        "priority": "high",
                        "estimated_hours": 3
                    },
                    {
                        "category": "content",
                        "task": "Research emerging topics in coordination space",
                        "priority": "medium",
                        "estimated_hours": 2
                    }
                ])
            
            # Engagement tasks
            tasks.extend([
                {
                    "category": "engagement",
                    "task": "Initiate 5 meaningful conversations with domain experts",
                    "priority": "high",
                    "estimated_hours": 2
                },
                {
                    "category": "engagement",
                    "task": "Reply thoughtfully to 20+ mentions and comments",
                    "priority": "medium",
                    "estimated_hours": 3
                }
            ])
            
            # Analysis tasks
            tasks.extend([
                {
                    "category": "analysis",
                    "task": "Review and optimize posting schedule based on engagement patterns",
                    "priority": "medium",
                    "estimated_hours": 1
                },
                {
                    "category": "analysis",
                    "task": "Analyze competitor strategies and successful mechanisms",
                    "priority": "low",
                    "estimated_hours": 2
                }
            ])
            
            # Mechanism building tasks (core mission)
            tasks.extend([
                {
                    "category": "mechanism",
                    "task": "Draft one concrete pilot proposal with implementation timeline",
                    "priority": "high",
                    "estimated_hours": 4
                },
                {
                    "category": "mechanism",
                    "task": "Identify 3 potential collaboration partners for mechanism deployment",
                    "priority": "medium",
                    "estimated_hours": 2
                }
            ])
            
            return tasks
            
        except Exception as e:
            logger.error(f"Tactical planning failed: {e}")
            return self._get_default_tasks()
    
    async def _update_okrs(self, session: Session, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Update OKRs based on recent performance"""
        try:
            content_analysis = analysis.get("content_analysis", {})
            total_tweets = content_analysis.get("total_tweets", 0)
            
            # Calculate progress on default OKRs
            progress = {
                "proposals_generated": min(total_tweets, 6),
                "coalition_calls": 0,  # Would track separately
                "artifacts_published": 0  # Would track separately
            }
            
            # Calculate overall progress percentage
            total_progress = (
                (progress["proposals_generated"] / 6 * 100) +
                (progress["coalition_calls"] / 3 * 100) +
                (progress["artifacts_published"] / 2 * 100)
            ) / 3
            
            # Adjust OKRs if needed
            current_okr = self.default_okr.copy()
            
            if total_progress > 80:
                # Increase ambition
                current_okr["key_results"][0] = "Generate 8 high-quality proposal posts"
            elif total_progress < 30:
                # Reduce scope to ensure achievability
                current_okr["key_results"][0] = "Generate 4 high-quality proposal posts"
            
            return {
                "current_okr": current_okr,
                "progress": total_progress,
                "progress_details": progress,
                "next_milestone": self._get_next_milestone(progress),
                "risk_factors": self._identify_risk_factors(analysis)
            }
            
        except Exception as e:
            logger.error(f"OKR update failed: {e}")
            return {"current_okr": self.default_okr, "progress": 0}
    
    def _get_next_milestone(self, progress: Dict[str, Any]) -> str:
        """Identify next important milestone"""
        if progress["proposals_generated"] < 6:
            remaining = 6 - progress["proposals_generated"]
            return f"Generate {remaining} more proposal posts"
        elif progress["coalition_calls"] < 3:
            return "Schedule first coalition-building call"
        elif progress["artifacts_published"] < 2:
            return "Publish first concrete artifact"
        else:
            return "All key results achieved - set new ambitious goals"
    
    def _identify_risk_factors(self, analysis: Dict[str, Any]) -> List[str]:
        """Identify factors that might prevent OKR achievement"""
        risks = []
        
        weaknesses = analysis.get("weaknesses", [])
        if weaknesses:
            risks.extend([f"Performance issue: {w}" for w in weaknesses])
        
        content_analysis = analysis.get("content_analysis", {})
        if content_analysis.get("avg_engagement", 0) < 20:
            risks.append("Low engagement may limit coalition building")
        
        if content_analysis.get("total_tweets", 0) < 5:
            risks.append("Low content volume may miss proposal targets")
        
        return risks
    
    def _create_fallback_plan(self) -> Dict[str, Any]:
        """Create simple fallback plan when AI planning fails"""
        return {
            "focus": "maintain",
            "priorities": [
                "Maintain consistent posting schedule",
                "Engage with community",
                "Continue mechanism development"
            ],
            "tasks": self._get_default_tasks(),
            "okr": self.default_okr
        }
    
    def _get_default_tasks(self) -> List[Dict[str, Any]]:
        """Get default task list"""
        return [
            {
                "category": "content",
                "task": "Create 2 proposal posts this week",
                "priority": "high",
                "estimated_hours": 3
            },
            {
                "category": "engagement",
                "task": "Respond to all mentions and comments",
                "priority": "high", 
                "estimated_hours": 2
            },
            {
                "category": "mechanism",
                "task": "Work on pilot mechanism design",
                "priority": "medium",
                "estimated_hours": 3
            }
        ]

