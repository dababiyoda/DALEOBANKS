"""
Ethics guardrails with uncertainty quantification and rollback enforcement
"""

import re
from typing import Tuple, List, Dict, Any
from dataclasses import dataclass

from services.logging_utils import get_logger

logger = get_logger(__name__)

@dataclass
class EthicsResult:
    approved: bool
    reasons: List[str]
    uncertainty_score: float
    rollback_plan: str

class EthicsGuard:
    """Ethical guardrails for content validation"""
    
    def __init__(self):
        self.harmful_patterns = [
            r'\b(hate|violence|harm|attack|destroy|eliminate)\b',
            r'\b(scam|fraud|deceive|manipulate|exploit)\b',
            r'\b(illegal|criminal|unlawful)\b'
        ]
        
        self.required_proposal_elements = [
            "problem", "mechanism", "pilot", "kpi", "risk", "cta"
        ]
        
        self.uncertainty_keywords = [
            "uncertain", "unclear", "unknown", "might", "could", "possibly",
            "likely", "probably", "estimate", "approximate"
        ]
        
        self.rollback_keywords = [
            "rollback", "revert", "undo", "cancel", "abort", "stop",
            "fail-safe", "backup plan", "exit strategy"
        ]

    def has_receipt(self, text: str) -> bool:
        """Check if text includes a citation/link"""
        return bool(re.search(r"https?://\S+", text))

    def has_constructive_step(self, text: str) -> bool:
        """Simple heuristic for constructive next steps"""
        keywords = [
            "try", "pilot", "test", "fix", "rollback", "next step", "cta", "call to action"
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)
    
    def validate_text(self, text: str) -> EthicsResult:
        """
        Validate text against ethical guidelines
        
        Returns:
            EthicsResult with approval status and details
        """
        text_lower = text.lower()
        reasons = []
        
        # Check for harmful content
        for pattern in self.harmful_patterns:
            if re.search(pattern, text_lower):
                reasons.append(f"Contains potentially harmful language: {pattern}")
        
        # Check for deceptive content
        if self._contains_deception(text):
            reasons.append("Contains potentially deceptive content")
        
        # Calculate uncertainty score
        uncertainty_score = self._calculate_uncertainty_score(text)
        
        # Extract rollback plan
        rollback_plan = self._extract_rollback_plan(text)
        
        # Determine approval
        approved = len(reasons) == 0
        
        return EthicsResult(
            approved=approved,
            reasons=reasons,
            uncertainty_score=uncertainty_score,
            rollback_plan=rollback_plan
        )
    
    def enforce_addendum(self, text: str, content_type: str = "proposal") -> str:
        """
        Ensure uncertainty and rollback lines are present for proposals
        """
        if content_type != "proposal":
            return text
        
        text_lower = text.lower()
        
        # Check if uncertainty is already mentioned
        has_uncertainty = any(keyword in text_lower for keyword in self.uncertainty_keywords)
        
        # Check if rollback plan is already mentioned
        has_rollback = any(keyword in text_lower for keyword in self.rollback_keywords)
        
        addendum = []
        
        if not has_uncertainty:
            addendum.append("Uncertainty: Metrics may wobble; review weekly before scaling.")

        if not has_rollback:
            addendum.append("Rollback: Revert to the prior system if KPIs miss for two weeks.")
        
        if addendum:
            # Add addendum to the text
            return text + "\n\n" + " ".join(addendum)
        
        return text
    
    def _contains_deception(self, text: str) -> bool:
        """Check for potentially deceptive content"""
        deception_patterns = [
            r'\bguaranteed?\b',
            r'\b100%\s+(?:success|profit|return)\b',
            r'\bno\s+risk\b',
            r'\bsecret\s+(?:method|formula|system)\b'
        ]
        
        text_lower = text.lower()
        for pattern in deception_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _calculate_uncertainty_score(self, text: str) -> float:
        """
        Calculate uncertainty score based on language used
        Higher score = more uncertainty expressed (good)
        """
        text_lower = text.lower()
        uncertainty_count = sum(1 for keyword in self.uncertainty_keywords if keyword in text_lower)
        
        # Normalize to 0-1 range
        max_expected = 5
        return min(uncertainty_count / max_expected, 1.0)
    
    def _extract_rollback_plan(self, text: str) -> str:
        """Extract rollback plan from text"""
        lines = text.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in self.rollback_keywords):
                return line.strip()
        
        return "No explicit rollback plan found"
    
    def validate_proposal_completeness(self, text: str) -> Tuple[bool, List[str]]:
        """
        Validate that a proposal contains all required elements
        """
        text_lower = text.lower()
        missing_elements = []
        
        element_patterns = {
            "problem": [r'\bproblem\b', r'\bissue\b', r'\bchallenge\b'],
            "mechanism": [r'\bmechanism\b', r'\bsolution\b', r'\bapproach\b'],
            "pilot": [r'\bpilot\b', r'\btest\b', r'\btrial\b', r'\bexperiment\b'],
            "kpi": [r'\bkpi\b', r'\bmetric\b', r'\bmeasure\b', r'\bindicator\b'],
            "risk": [r'\brisk\b', r'\bdanger\b', r'\bconcern\b', r'\blimitation\b'],
            "cta": [r'\bcta\b', r'\bcall.to.action\b', r'\bjoin\b', r'\bsign.up\b', r'\blearn.more\b']
        }
        
        for element, patterns in element_patterns.items():
            found = any(re.search(pattern, text_lower) for pattern in patterns)
            if not found:
                missing_elements.append(element)
        
        is_complete = len(missing_elements) == 0
        return is_complete, missing_elements
    
    def get_safety_report(self) -> Dict[str, Any]:
        """Get safety and ethics status report"""
        return {
            "guardrails_active": True,
            "harm_prevention": "active",
            "deception_detection": "active",
            "uncertainty_enforcement": "active",
            "rollback_requirement": "active",
            "last_violation": None,  # Would track in real implementation
            "total_blocks": 0  # Would track in real implementation
        }
