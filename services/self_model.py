"""
Self-Model Card generation and identity management
"""

import hashlib
import os
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from services.persona_store import PersonaStore
from services.logging_utils import get_logger
from db.session import get_db_session

logger = get_logger(__name__)

class SelfModelService:
    """Manages self-model card and identity hash"""
    
    def __init__(self, persona_store: PersonaStore):
        self.persona_store = persona_store
        self.model_card_path = "self_model_card.md"
        self.current_identity_hash: Optional[str] = None
    
    async def ensure_self_model(self):
        """Ensure self-model exists and is current"""
        try:
            # Check if model card exists
            if not os.path.exists(self.model_card_path):
                logger.info("Self-model card not found, creating...")
                await self.create_self_model()
            
            # Verify identity hash
            identity_hash = self._calculate_identity_hash()
            
            if self.current_identity_hash != identity_hash:
                logger.info("Identity hash mismatch, updating self-model...")
                await self.update_self_model()
            
            self.current_identity_hash = identity_hash
            
        except Exception as e:
            logger.error(f"Failed to ensure self-model: {e}")
            raise
    
    async def create_self_model(self):
        """Create initial self-model card"""
        try:
            persona = self.persona_store.get_current_persona()
            identity_hash = self._calculate_identity_hash()
            
            model_card = self._generate_model_card(persona, identity_hash)
            
            with open(self.model_card_path, "w") as f:
                f.write(model_card)
            
            self.current_identity_hash = identity_hash
            logger.info(f"Created self-model card with identity hash: {identity_hash}")
            
        except Exception as e:
            logger.error(f"Failed to create self-model: {e}")
            raise
    
    async def update_self_model(self):
        """Update self-model card when persona changes"""
        try:
            persona = self.persona_store.get_current_persona()
            identity_hash = self._calculate_identity_hash()
            
            model_card = self._generate_model_card(persona, identity_hash)
            
            # Backup old model card
            if os.path.exists(self.model_card_path):
                backup_path = f"{self.model_card_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.rename(self.model_card_path, backup_path)
            
            with open(self.model_card_path, "w") as f:
                f.write(model_card)
            
            self.current_identity_hash = identity_hash
            logger.info(f"Updated self-model card with identity hash: {identity_hash}")
            
        except Exception as e:
            logger.error(f"Failed to update self-model: {e}")
            raise
    
    def _calculate_identity_hash(self) -> str:
        """Calculate identity hash from current persona"""
        try:
            persona = self.persona_store.get_current_persona()
            
            # Create a canonical representation for hashing
            identity_components = {
                "handle": persona.get("handle"),
                "mission": persona.get("mission"),
                "beliefs": persona.get("beliefs"),
                "doctrine": persona.get("doctrine"),
                "tone_rules": persona.get("tone_rules"),
                "guardrails": persona.get("guardrails")
            }
            
            # Sort for consistency
            import json
            canonical_str = json.dumps(identity_components, sort_keys=True, separators=(',', ':'))
            
            # Generate SHA256 hash
            hash_obj = hashlib.sha256(canonical_str.encode('utf-8'))
            return hash_obj.hexdigest()[:16]  # First 16 characters
            
        except Exception as e:
            logger.error(f"Failed to calculate identity hash: {e}")
            return "unknown"
    
    def _generate_model_card(self, persona: Dict[str, Any], identity_hash: str) -> str:
        """Generate markdown model card"""
        
        card_template = f"""# Self-Model Card: {persona.get('handle', 'DaLeoBanks')}

**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Identity Hash:** `{identity_hash}`  
**Version:** {persona.get('version', 1)}

## Core Identity

### Mission
{persona.get('mission', 'Not specified')}

### Handle
@{persona.get('handle', 'DaLeoBanks')}

### Doctrine
{' → '.join(persona.get('doctrine', []))}

## Beliefs & Values

{self._format_beliefs(persona.get('beliefs', []))}

## Behavioral Framework

### Tone Rules
{self._format_tone_rules(persona.get('tone_rules', {}))}

### Content Strategy
{self._format_content_mix(persona.get('content_mix', {}))}

### Templates
{self._format_templates(persona.get('templates', {}))}

## Safety & Ethics

### Guardrails
{self._format_guardrails(persona.get('guardrails', []))}

## Operational Metadata

- **Configuration File:** `persona.json`
- **Last Modified:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
- **Verification Hash:** `{identity_hash}`

## Change Log

This model card is automatically updated when the persona configuration changes. 
The identity hash serves as a verification mechanism to ensure consistency between 
the declared identity and actual operational parameters.

### Version History
- v{persona.get('version', 1)}: {datetime.utcnow().strftime('%Y-%m-%d')} - Current version

## Compliance Notes

This AI agent operates under the following principles:
- **Transparency:** All behavioral parameters are documented and auditable
- **Accountability:** Actions are logged and can be traced to specific configurations
- **Safety:** Multiple guardrails prevent harmful or deceptive behavior
- **Adaptability:** The system can evolve while maintaining core ethical constraints

## Technical Implementation

- **Architecture:** FastAPI + APScheduler for 24/7 operation
- **Platform:** Twitter/X via official API v2 (Tweepy)
- **Optimization:** Thompson sampling multi-armed bandit
- **Memory:** Episodic, semantic, procedural, and social memory systems
- **Ethics:** Real-time guardrails with uncertainty quantification

---

*This self-model card is generated automatically and represents the current 
operational configuration of the AI agent. Any discrepancies between this 
documentation and actual behavior should be investigated immediately.*
"""
        return card_template
    
    def _format_beliefs(self, beliefs: list) -> str:
        """Format beliefs as markdown list"""
        if not beliefs:
            return "- No specific beliefs configured"
        
        return "\n".join(f"- {belief}" for belief in beliefs)
    
    def _format_tone_rules(self, tone_rules: dict) -> str:
        """Format tone rules as markdown"""
        if not tone_rules:
            return "- No specific tone rules configured"
        
        formatted = []
        for context, rule in tone_rules.items():
            formatted.append(f"- **{context.title()}:** {rule}")
        
        return "\n".join(formatted)
    
    def _format_content_mix(self, content_mix: dict) -> str:
        """Format content mix as markdown"""
        if not content_mix:
            return "- Default content mix"
        
        formatted = []
        for content_type, percentage in content_mix.items():
            formatted.append(f"- **{content_type.title()}:** {percentage*100:.0f}%")
        
        return "\n".join(formatted)
    
    def _format_templates(self, templates: dict) -> str:
        """Format templates as markdown"""
        if not templates:
            return "- No templates configured"
        
        formatted = []
        for template_type, template in templates.items():
            if isinstance(template, list):
                template_str = " → ".join(template)
            else:
                template_str = template
            formatted.append(f"- **{template_type.title()}:** {template_str}")
        
        return "\n".join(formatted)
    
    def _format_guardrails(self, guardrails: list) -> str:
        """Format guardrails as markdown list"""
        if not guardrails:
            return "- No specific guardrails configured"
        
        return "\n".join(f"- `{guardrail}`" for guardrail in guardrails)
    
    def get_identity_hash(self) -> Optional[str]:
        """Get current identity hash"""
        return self.current_identity_hash
    
    def verify_identity(self) -> bool:
        """Verify that current identity matches stored hash"""
        current_hash = self._calculate_identity_hash()
        return current_hash == self.current_identity_hash
    
    def get_model_card_path(self) -> str:
        """Get path to model card file"""
        return self.model_card_path
    
    def get_model_card_content(self) -> Optional[str]:
        """Get current model card content"""
        try:
            if os.path.exists(self.model_card_path):
                with open(self.model_card_path, "r") as f:
                    return f.read()
            return None
        except Exception as e:
            logger.error(f"Failed to read model card: {e}")
            return None
    
    def get_identity_status(self) -> Dict[str, Any]:
        """Get identity verification status"""
        return {
            "identity_hash": self.current_identity_hash,
            "model_card_exists": os.path.exists(self.model_card_path),
            "identity_verified": self.verify_identity(),
            "last_updated": datetime.fromtimestamp(
                os.path.getmtime(self.model_card_path)
            ).isoformat() if os.path.exists(self.model_card_path) else None
        }

