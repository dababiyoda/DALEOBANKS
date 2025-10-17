"""
Content completeness and quality critic
"""

import re
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass

from services.logging_utils import get_logger

logger = get_logger(__name__)

@dataclass
class CriticResult:
    is_complete: bool
    missing_elements: List[str]
    quality_score: float
    suggestions: List[str]
    blocking_issues: List[str]

class Critic:
    """Ensures content meets completeness and quality standards"""
    
    def __init__(self):
        # Required elements for proposals (P→M→P→K→R→CTA pattern)
        self.proposal_elements = {
            "problem": {
                "keywords": [r'\bproblem\b', r'\bissue\b', r'\bchallenge\b', r'\bgap\b', r'\bfailing\b'],
                "description": "Problem identification"
            },
            "mechanism": {
                "keywords": [r'\bmechanism\b', r'\bsolution\b', r'\bapproach\b', r'\bframework\b', r'\bsystem\b', r'\bmethod\b'],
                "description": "Proposed mechanism or solution"
            },
            "pilot": {
                "keywords": [r'\bpilot\b', r'\btest\b', r'\btrial\b', r'\bexperiment\b', r'\b30.day\b', r'\b90.day\b'],
                "description": "Pilot implementation plan"
            },
            "kpis": {
                "keywords": [r'\bkpi\b', r'\bkpis\b', r'\bmetric\b', r'\bmeasure\b', r'\bindicator\b', r'\bsuccess\b', r'\btrack\b'],
                "description": "Success metrics and KPIs"
            },
            "risks": {
                "keywords": [r'\brisk\b', r'\brisks\b', r'\bdanger\b', r'\bconcern\b', r'\blimitation\b', r'\bfail\b', r'\bchallenge\b'],
                "description": "Risk assessment"
            },
            "cta": {
                "keywords": [r'\bjoin\b', r'\bsign.up\b', r'\blearn.more\b', r'\bcontact\b', r'\bapply\b', r'\bparticipate\b', r'\blink\b'],
                "description": "Call to action"
            }
        }
        
        # Quality indicators
        self.quality_indicators = {
            "specific_numbers": r'\b\d+\s*(?:days?|weeks?|months?|%|dollars?|\$)',
            "concrete_actions": r'\b(?:implement|deploy|create|build|establish|launch|start)\b',
            "measurable_outcomes": r'(?:>\s*\d+%|\b(?:increase|decrease|improve|reduce|achieve|reach)\s+(?:by\s+)?\d+)',
            "time_bounds": r'\b(?:within|in|by)\s+\d+\s*(?:days?|weeks?|months?)',
            "stakeholder_mentions": r'\b(?:users?|customers?|teams?|organizations?|communities?)\b'
        }
        
        # Blocking quality issues
        self.blocking_issues = {
            "too_vague": [r'\bmight\s+help\b', r'\bcould\s+work\b', r'\bmaybe\b', r'\bperhaps\b'],
            "no_specifics": [r'\bsomehow\b', r'\bsomething\b', r'\bstuff\b', r'\bthings\b'],
            "unrealistic": [r'\b100%\s+(?:success|guarantee)\b', r'\bno\s+risk\b', r'\bperfect\s+solution\b'],
            "too_generic": [r'\bmake\s+things\s+better\b', r'\bsolve\s+everything\b', r'\bfix\s+all\b']
        }

    def split_sentences(self, text: str) -> List[str]:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    def has_periodic_cadence(self, text: str, max_sentences: int = 2) -> bool:
        """Check whether text satisfies the current cadence requirements for replies."""

        sentences = self.split_sentences(text)
        if not sentences:
            return False
        return len(sentences) <= max_sentences
    
    def check_completeness(self, text: str, content_type: str = "proposal") -> Tuple[bool, List[str]]:
        """
        Check if content contains all required elements
        
        Returns:
            Tuple of (is_complete, missing_elements)
        """
        if content_type != "proposal":
            return True, []  # Only proposals need full P→M→P→K→R→CTA structure
        
        text_lower = text.lower()
        missing_elements = []
        
        for element, config in self.proposal_elements.items():
            found = any(re.search(pattern, text_lower) for pattern in config["keywords"])
            if not found:
                missing_elements.append(element)
        
        is_complete = len(missing_elements) == 0
        return is_complete, missing_elements
    
    def analyze_quality(self, text: str, content_type: str = "proposal") -> CriticResult:
        """
        Comprehensive quality analysis of content
        
        Returns:
            CriticResult with completeness, quality score, and suggestions
        """
        text_lower = text.lower()
        
        # Check completeness
        is_complete, missing_elements = self.check_completeness(text, content_type)
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(text)
        
        # Check for blocking issues
        blocking_issues = self._find_blocking_issues(text)
        
        # Generate suggestions
        suggestions = self._generate_suggestions(text, missing_elements, quality_score)
        
        return CriticResult(
            is_complete=is_complete,
            missing_elements=missing_elements,
            quality_score=quality_score,
            suggestions=suggestions,
            blocking_issues=blocking_issues
        )
    
    def _calculate_quality_score(self, text: str) -> float:
        """Calculate quality score (0-100) based on various indicators"""
        text_lower = text.lower()
        score = 0.0
        max_score = 100.0
        
        # Length check (substantial content)
        if len(text) > 100:
            score += 15
        elif len(text) > 50:
            score += 10
        else:
            score += 5
        
        # Specific numbers and metrics
        if re.search(self.quality_indicators["specific_numbers"], text_lower):
            score += 20
        
        # Concrete actions
        if re.search(self.quality_indicators["concrete_actions"], text_lower):
            score += 15
        
        # Measurable outcomes
        if re.search(self.quality_indicators["measurable_outcomes"], text_lower):
            score += 20
        
        # Time bounds
        if re.search(self.quality_indicators["time_bounds"], text_lower):
            score += 15
        
        # Stakeholder mentions
        if re.search(self.quality_indicators["stakeholder_mentions"], text_lower):
            score += 10

        # Question marks (engagement)
        if "?" in text:
            score += 5

        # Explicit references to KPIs and risk management boost quality.
        if "kpi" in text_lower or "kpis" in text_lower:
            score += 10

        if "risk" in text_lower or "risks" in text_lower:
            score += 5

        # Normalize to 0-100
        return min(score, max_score)
    
    def _find_blocking_issues(self, text: str) -> List[str]:
        """Find issues that should block publication"""
        text_lower = text.lower()
        issues = []
        
        for issue_type, patterns in self.blocking_issues.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    issues.append(f"{issue_type}: contains '{pattern}'")
        
        # Check for missing critical elements in proposals
        if self._looks_like_proposal(text):
            is_complete, missing = self.check_completeness(text, "proposal")
            if not is_complete and len(missing) > 3:
                issues.append(f"missing_too_many_elements: {', '.join(missing)}")
        
        return issues
    
    def _generate_suggestions(self, text: str, missing_elements: List[str], quality_score: float) -> List[str]:
        """Generate actionable suggestions for improvement"""
        suggestions = []
        
        # Suggestions for missing elements
        element_suggestions = {
            "problem": "Start with a clear problem statement: 'The main issue is...'",
            "mechanism": "Propose a specific mechanism: 'Implement X system that...'",
            "pilot": "Include pilot details: '30-day trial with Y participants...'",
            "kpis": "Add 3 measurable KPIs: '1) Adoption rate >20%, 2) Error rate <5%...'",
            "risks": "Acknowledge risks: 'Main risks include X and Y...'",
            "cta": "End with clear call to action: 'Join the pilot at...' or 'Learn more at...'"
        }
        
        for element in missing_elements:
            if element in element_suggestions:
                suggestions.append(element_suggestions[element])
        
        # Quality-based suggestions
        if quality_score < 30:
            suggestions.append("Add specific numbers, timelines, and metrics to increase concreteness")
        
        if quality_score < 50:
            suggestions.append("Include more concrete actions and measurable outcomes")
        
        if not re.search(self.quality_indicators["time_bounds"], text.lower()):
            suggestions.append("Add time boundaries: 'within 30 days' or 'by end of quarter'")
        
        if not re.search(self.quality_indicators["stakeholder_mentions"], text.lower()):
            suggestions.append("Specify who this affects: users, teams, organizations, etc.")
        
        # Length suggestions
        if len(text) < 100:
            suggestions.append("Expand with more detail - aim for 150-250 characters")
        elif len(text) > 270:
            suggestions.append("Trim to fit Twitter's 280 character limit")
        
        return suggestions
    
    def _looks_like_proposal(self, text: str) -> bool:
        """Heuristic to determine if text is intended as a proposal"""
        proposal_indicators = [
            r'\bproposal\b', r'\bpropose\b', r'\bsolution\b', r'\bimplement\b',
            r'\bmechanism\b', r'\bpilot\b', r'\bframework\b'
        ]
        
        text_lower = text.lower()
        return any(re.search(indicator, text_lower) for indicator in proposal_indicators)
    
    def get_template_compliance(self, text: str, template: str) -> Dict[str, Any]:
        """Check how well content follows a specific template"""
        if template == "Problem → Mechanism → 30–90d Pilot → 3 KPIs → Risks → CTA":
            return self._check_pmpr_template(text)
        elif template == "Illuminate gap → Concrete mechanism → One next step":
            return self._check_reply_template(text)
        else:
            return {"compliance": 0.5, "notes": "Unknown template"}
    
    def _check_pmpr_template(self, text: str) -> Dict[str, Any]:
        """Check Problem→Mechanism→Pilot→KPIs→Risks→CTA template compliance"""
        is_complete, missing = self.check_completeness(text, "proposal")
        
        compliance_score = (6 - len(missing)) / 6  # 6 required elements
        
        return {
            "compliance": compliance_score,
            "template": "P→M→P→K→R→CTA",
            "completed_elements": 6 - len(missing),
            "missing_elements": missing,
            "notes": f"Template compliance: {compliance_score*100:.0f}%"
        }
    
    def _check_reply_template(self, text: str) -> Dict[str, Any]:
        """Check reply template compliance"""
        text_lower = text.lower()
        
        has_gap = any(re.search(pattern, text_lower) for pattern in [
            r'\bgap\b', r'\bmissing\b', r'\bneeds?\b', r'\blacks?\b', r'\bwithout\b'
        ])
        
        has_mechanism = any(re.search(pattern, text_lower) for pattern in [
            r'\bmechanism\b', r'\bsolution\b', r'\bapproach\b', r'\bmethod\b', r'\bway\b'
        ])
        
        has_next_step = any(re.search(pattern, text_lower) for pattern in [
            r'\bnext\b', r'\bstep\b', r'\bstart\b', r'\bbegin\b', r'\btry\b', r'\bconsider\b'
        ])
        
        elements_present = sum([has_gap, has_mechanism, has_next_step])
        compliance = elements_present / 3
        
        missing = []
        if not has_gap:
            missing.append("gap_identification")
        if not has_mechanism:
            missing.append("concrete_mechanism")
        if not has_next_step:
            missing.append("next_step")
        
        return {
            "compliance": compliance,
            "template": "Gap→Mechanism→NextStep",
            "completed_elements": elements_present,
            "missing_elements": missing,
            "notes": f"Reply template compliance: {compliance*100:.0f}%"
        }
    
    def batch_analyze(self, texts: List[str], content_type: str = "proposal") -> List[CriticResult]:
        """Analyze multiple texts in batch"""
        return [self.analyze_quality(text, content_type) for text in texts]
    
    def get_critic_stats(self, session) -> Dict[str, Any]:
        """Get statistics about content quality over time"""
        # This would analyze historical content quality
        # For now, return placeholder stats
        return {
            "avg_quality_score": 75.0,
            "completion_rate": 0.85,
            "most_common_missing": ["kpis", "risks"],
            "quality_trend": "improving",
            "total_analyzed": 0  # Would count from database
        }

