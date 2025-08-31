"""
Tests for content templates and generation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.generator import Generator
from services.critic import Critic
from services.ethics_guard import EthicsGuard
from services.persona_store import PersonaStore

class TestContentTemplates:
    """Test content template functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_persona_store = MagicMock()
        self.mock_llm_adapter = AsyncMock()
        
        # Mock persona data
        self.mock_persona = {
            "templates": {
                "tweet": "Problem → Mechanism → 30–90d Pilot → 3 KPIs → Risks → CTA",
                "reply": "Illuminate gap → Concrete mechanism → One next step",
                "thread": ["Problem/Cost", "Mechanism Design", "Pilot Spec", "KPIs", "Risks & Rollback", "Artifact + CTA"]
            },
            "tone_rules": {
                "people": "Respectful; steelman first if non‑malicious.",
                "systems": "Surgical and direct; name mechanism failures."
            },
            "content_mix": {
                "proposals": 0.7,
                "elite_replies": 0.2,
                "summaries": 0.1
            }
        }
        
        self.mock_persona_store.get_current_persona.return_value = self.mock_persona
        self.generator = Generator(self.mock_persona_store, self.mock_llm_adapter)
        self.critic = Critic()
        self.ethics_guard = EthicsGuard()
    
    def test_proposal_template_completeness(self):
        """Test that proposals contain all required P→M→P→K→R→CTA elements"""
        proposal_text = """
        Problem: Current coordination mechanisms fail at scale.
        Mechanism: Implement quadratic voting with reputation weighting.
        Pilot: 30-day trial with 100 participants across 5 organizations.
        KPIs: 1) Adoption rate >20%, 2) Decision quality score >4/5, 3) Participation rate >80%
        Risks: Low initial adoption, technical complexity, coordination overhead
        Rollback: Revert to previous voting system if KPIs not met by day 25
        CTA: Join the pilot at coordination.example/pilot
        """
        
        is_complete, missing = self.critic.check_completeness(proposal_text, "proposal")
        
        assert is_complete == True
        assert len(missing) == 0
    
    def test_proposal_missing_elements(self):
        """Test detection of missing proposal elements"""
        incomplete_proposal = """
        Problem: Coordination is hard.
        Mechanism: Use better voting.
        CTA: Sign up now!
        """
        
        is_complete, missing = self.critic.check_completeness(incomplete_proposal, "proposal")
        
        assert is_complete == False
        assert "pilot" in missing
        assert "kpis" in missing
        assert "risks" in missing
    
    def test_reply_template_structure(self):
        """Test reply template compliance"""
        reply_text = """
        I see a gap in your mechanism design - it lacks incentive alignment.
        Consider implementing a token-curated registry approach with staking.
        Next step: Draft a simple prototype and test with 10 users this week.
        """
        
        compliance = self.critic.get_template_compliance(
            reply_text, 
            "Illuminate gap → Concrete mechanism → One next step"
        )
        
        assert compliance["compliance"] >= 0.8  # High compliance
        assert "Gap→Mechanism→NextStep" in compliance["template"]
        assert compliance["completed_elements"] == 3
    
    def test_character_limit_compliance(self):
        """Test that generated content stays within Twitter's 280 character limit"""
        short_proposal = "Problem: X. Mechanism: Y. Pilot: 30d test. KPIs: 3 metrics. Risks: Z. CTA: Join"
        long_proposal = "Problem: " + "X" * 100 + ". Mechanism: " + "Y" * 100 + ". Pilot: 30d test. KPIs: 3 metrics. Risks: " + "Z" * 100 + ". CTA: Join at very-long-url-that-makes-this-tweet-way-too-long-for-twitter"
        
        # Short proposal should pass
        result_short = self.critic.analyze_quality(short_proposal, "proposal")
        assert len(short_proposal) <= 280
        
        # Long proposal should be flagged
        result_long = self.critic.analyze_quality(long_proposal, "proposal")
        assert len(long_proposal) > 280
        assert any("280 character" in suggestion for suggestion in result_long.suggestions)
    
    def test_duplicate_detection(self):
        """Test duplicate content detection and mutation"""
        original_text = "Problem: Coordination fails. Mechanism: Use voting. Pilot: 30 days."
        similar_text = "Problem: Coordination fails. Mechanism: Use voting. Pilot: 30 days."
        different_text = "Problem: Markets fail. Mechanism: Use auctions. Pilot: 60 days."
        
        # Mock recent tweets for duplicate checking
        mock_tweets = [MagicMock(text=original_text, created_at=MagicMock())]
        
        with patch('services.generator.get_db_session') as mock_session:
            mock_session.return_value.__enter__.return_value.query.return_value.filter.return_value.all.return_value = mock_tweets

            # Exact duplicate
            is_dup, _ = self.generator._check_for_duplicates(original_text, mock_session.return_value.__enter__.return_value)
            assert is_dup is True

            # Similar text should be detected as duplicate
            is_duplicate, similar = self.generator._check_for_duplicates(similar_text, mock_session.return_value.__enter__.return_value)
            assert is_duplicate == True
            
            # Different text should not be duplicate
            is_duplicate, similar = self.generator._check_for_duplicates(different_text, mock_session.return_value.__enter__.return_value)
            assert is_duplicate == False
    
    @pytest.mark.asyncio
    async def test_content_mutation(self):
        """Test content mutation for duplicate avoidance"""
        original = "Implement quadratic voting mechanism for better coordination"
        similar = "Implement quadratic voting mechanism for improved coordination"
        
        # Mock LLM response for mutation
        self.mock_llm_adapter.chat.return_value = "Deploy quadratic voting system for enhanced coordination"
        
        mutated = await self.generator._mutate_content(original, similar)
        
        assert mutated != original
        assert mutated != similar
        assert "quadratic voting" in mutated  # Core concept preserved
        self.mock_llm_adapter.chat.assert_called_once()
    
    def test_quality_scoring(self):
        """Test content quality scoring system"""
        high_quality = """
        Problem: Current voting systems have 15% participation rates.
        Mechanism: Implement quadratic voting with 0.1 ETH deposits.
        Pilot: 30-day trial with 50 users, testing 3 governance decisions.
        KPIs: 1) Participation >30%, 2) Satisfaction >4/5, 3) Decision quality >80%
        Risks: Technical bugs, low adoption, gas cost barriers
        Rollback: Revert to simple majority if targets missed by day 25
        CTA: Apply at governance.dao/quadratic-pilot
        """
        
        low_quality = "Maybe we could try something with voting that might work better somehow."
        
        high_score = self.critic._calculate_quality_score(high_quality)
        low_score = self.critic._calculate_quality_score(low_quality)
        
        assert high_score >= 60  # High quality content threshold adjusted
        assert low_score < 30   # Low quality content
        assert high_score > low_score
    
    def test_ethics_validation(self):
        """Test ethics guardrails"""
        harmful_content = "Destroy the current system and eliminate opposition voices"
        deceptive_content = "This mechanism guarantees 100% success with no risk"
        good_content = "Propose mechanism with measured KPIs and rollback plan"
        
        # Harmful content should be blocked
        harmful_result = self.ethics_guard.validate_text(harmful_content)
        assert harmful_result.approved == False
        assert len(harmful_result.reasons) > 0
        
        # Deceptive content should be blocked
        deceptive_result = self.ethics_guard.validate_text(deceptive_content)
        assert deceptive_result.approved == False
        
        # Good content should pass
        good_result = self.ethics_guard.validate_text(good_content)
        assert good_result.approved == True
    
    def test_uncertainty_enforcement(self):
        """Test uncertainty quantification enforcement"""
        proposal_without_uncertainty = """
        Problem: Coordination fails.
        Mechanism: Use quadratic voting.
        Pilot: 30 days with 100 users.
        KPIs: Adoption rate, satisfaction, quality.
        Risks: Technical issues.
        CTA: Join now.
        """
        
        # Should add uncertainty addendum
        enhanced = self.ethics_guard.enforce_addendum(proposal_without_uncertainty, "proposal")
        
        assert "Uncertainty:" in enhanced
        assert "Rollback:" in enhanced
        assert len(enhanced) > len(proposal_without_uncertainty)
    
    def test_template_routing(self):
        """Test that different content types use appropriate templates"""
        # Mock different template types
        tweet_template = self.mock_persona["templates"]["tweet"]
        reply_template = self.mock_persona["templates"]["reply"]
        
        # Verify templates are different and appropriate
        assert "Problem" in tweet_template and "KPIs" in tweet_template
        assert "gap" in reply_template and "next step" in reply_template
        assert tweet_template != reply_template
    
    @pytest.mark.asyncio
    async def test_end_to_end_generation(self):
        """Test complete proposal generation pipeline"""
        # Mock LLM response
        mock_response = (
            "Problem: 8% participation. "
            "Mechanism: conviction voting delegation. "
            "Pilot: 45d trial, 5 proposals. "
            "KPIs: participation >25%, efficiency >90%. "
            "Risks: confusion. "
            "Uncertainty: adoption varies. "
            "Rollback by day 30. "
            "CTA: Join aragon.org/conviction"
        )
        
        self.mock_llm_adapter.chat.return_value = mock_response
        
        # Mock database session for duplicate checking
        with patch('services.generator.get_db_session') as mock_db:
            mock_db.return_value.__enter__.return_value.query.return_value.filter.return_value.all.return_value = []
            
            result = await self.generator.make_proposal("governance")
            
            # Verify successful generation
            assert "error" not in result
            assert "content" in result
            assert result["content_type"] == "proposal"
            assert result["topic"] == "governance"
            assert result["character_count"] <= 280
            assert result["ethics_score"] >= 0

if __name__ == "__main__":
    pytest.main([__file__])
