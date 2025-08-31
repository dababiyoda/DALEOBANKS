"""
Runtime persona management with validation, versioning, and hot-reload
"""

import json
import hashlib
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, ValidationError, validator
from sqlalchemy.orm import Session

from services.logging_utils import get_logger
from db.session import get_db_session
from db.models import PersonaVersion

logger = get_logger(__name__)

class PersonaSchema(BaseModel):
    """Pydantic schema for persona validation"""
    version: int
    handle: str
    mission: str
    beliefs: List[str]
    doctrine: List[str]
    tone_rules: Dict[str, str]
    content_mix: Dict[str, float]
    guardrails: List[str]
    templates: Dict[str, Any]
    prompt_overrides: Optional[Dict[str, str]] = None
    intensity_settings: Optional[Dict[str, Any]] = None
    
    @validator('content_mix')
    def validate_content_mix(cls, v):
        """Ensure content mix sums to approximately 1.0"""
        total = sum(v.values())
        if not (0.95 <= total <= 1.05):
            raise ValueError(f"Content mix must sum to ~1.0, got {total}")
        return v
    
    @validator('beliefs')
    def validate_beliefs(cls, v):
        """Ensure beliefs are non-empty strings"""
        if not v or any(not belief.strip() for belief in v):
            raise ValueError("Beliefs cannot be empty")
        return v
    
    @validator('handle')
    def validate_handle(cls, v):
        """Validate Twitter handle format"""
        if not v or len(v) > 15 or not v.isalnum():
            raise ValueError("Handle must be alphanumeric and ≤15 characters")
        return v

class PersonaStore:
    """Manages persona with validation, versioning, and hot-reload"""
    
    def __init__(self, persona_file: str = "persona.json", base_persona_file: str = "prompts/base_persona.txt"):
        self.persona_file = persona_file
        self.base_persona_file = base_persona_file
        self.current_persona: Optional[Dict[str, Any]] = None
        self.current_version: int = 1
        self.file_watch_enabled = True
        self._last_modified = 0
        self._current_hash = ""
        
        # Load initial persona
        self.load_persona()
    
    def load_persona(self) -> Dict[str, Any]:
        """Load persona from file with validation"""
        try:
            if not os.path.exists(self.persona_file):
                raise FileNotFoundError(f"Persona file not found: {self.persona_file}")
            
            with open(self.persona_file, 'r') as f:
                persona_data = json.load(f)
            
            # Validate against schema
            validated_persona = self.validate_persona(persona_data)
            
            self.current_persona = validated_persona
            self.current_version = validated_persona.get('version', 1)
            self._last_modified = os.path.getmtime(self.persona_file)
            self._current_hash = self._calculate_hash(validated_persona)
            
            logger.info(f"Loaded persona v{self.current_version}: {validated_persona['handle']}")
            return validated_persona
            
        except Exception as e:
            logger.error(f"Failed to load persona: {e}")
            # Fall back to default persona if available
            if self.current_persona:
                logger.warning("Using cached persona due to load failure")
                return self.current_persona
            raise
    
    def validate_persona(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate persona data against schema"""
        try:
            persona_schema = PersonaSchema(**persona_data)
            return persona_schema.dict()
        except ValidationError as e:
            logger.error(f"Persona validation failed: {e}")
            raise ValueError(f"Invalid persona format: {e}")

    def preview_persona(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate persona and build preview prompt without saving"""
        validated = self.validate_persona(persona_data)
        prompt = self.build_system_prompt()
        return {"validated": validated, "system_preview": prompt[:500]}
    
    def get_current_persona(self) -> Dict[str, Any]:
        """Get current persona, checking for file changes"""
        if self.file_watch_enabled and self._has_file_changed():
            logger.info("Persona file changed, reloading...")
            self.load_persona()
        
        if not self.current_persona:
            raise RuntimeError("No persona loaded")
        
        return self.current_persona.copy()
    
    def update_persona(self, new_persona_data: Dict[str, Any], actor: str = "system") -> int:
        """Update persona with validation and versioning"""
        try:
            # Validate new persona
            validated_persona = self.validate_persona(new_persona_data)
            
            # Increment version
            new_version = validated_persona.get('version', self.current_version) + 1
            validated_persona['version'] = new_version
            
            # Calculate hash
            persona_hash = self._calculate_hash(validated_persona)
            
            # Store version in database
            with get_db_session() as session:
                persona_version = PersonaVersion(
                    version=new_version,
                    hash=persona_hash,
                    actor=actor,
                    payload=validated_persona
                )
                session.add(persona_version)
                session.commit()
            
            # Write to file atomically
            temp_file = f"{self.persona_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(validated_persona, f, indent=2)
            
            os.replace(temp_file, self.persona_file)

            # Update internal state
            self.current_persona = validated_persona
            self.current_version = new_version
            self._last_modified = os.path.getmtime(self.persona_file)
            self._current_hash = persona_hash

            logger.info(f"Updated persona to v{new_version} by {actor}")
            return new_version
            
        except Exception as e:
            logger.error(f"Persona update failed: {e}")
            raise
    
    def rollback_to_version(self, version: int, actor: str = "system") -> int:
        """Rollback to a previous persona version"""
        try:
            with get_db_session() as session:
                # Get the specified version
                persona_version = session.query(PersonaVersion).filter(
                    PersonaVersion.version == version
                ).first()
                
                if not persona_version:
                    raise ValueError(f"Version {version} not found")
                
                # Create new version based on old one
                rollback_data = persona_version.payload.copy()
                rollback_data['version'] = self.current_version

                # Save as new version (will increment inside update_persona)
                return self.update_persona(rollback_data, actor=f"{actor}_rollback_to_v{version}")
                
        except Exception as e:
            logger.error(f"Persona rollback failed: {e}")
            raise
    
    def build_system_prompt(self, recent_notes: List[str] = None) -> str:
        """Build complete system prompt from persona + base + notes"""
        try:
            # Load base persona directive
            base_directive = ""
            if os.path.exists(self.base_persona_file):
                with open(self.base_persona_file, 'r') as f:
                    base_directive = f.read().strip()
            
            persona = self.get_current_persona()
            
            # Build comprehensive prompt
            prompt_parts = [
                base_directive,
                "",
                f"PERSONA IDENTITY:",
                f"Handle: @{persona['handle']}",
                f"Mission: {persona['mission']}",
                "",
                "CORE BELIEFS:",
            ]
            
            for belief in persona['beliefs']:
                prompt_parts.append(f"- {belief}")
            
            prompt_parts.extend([
                "",
                f"DOCTRINE: {' → '.join(persona['doctrine'])}",
                "",
                "TONE RULES:",
            ])
            
            for context, rule in persona['tone_rules'].items():
                prompt_parts.append(f"- {context}: {rule}")
            
            prompt_parts.extend([
                "",
                "CONTENT TEMPLATES:",
            ])
            
            for template_type, template in persona['templates'].items():
                if isinstance(template, list):
                    template_str = " → ".join(template)
                else:
                    template_str = template
                prompt_parts.append(f"- {template_type}: {template_str}")
            
            prompt_parts.extend([
                "",
                "GUARDRAILS:",
            ])
            
            for guardrail in persona['guardrails']:
                prompt_parts.append(f"- {guardrail}")
            
            # Add recent improvement notes
            if recent_notes:
                prompt_parts.extend([
                    "",
                    "RECENT LEARNINGS:",
                ])
                for note in recent_notes[-5:]:  # Last 5 notes
                    prompt_parts.append(f"- {note}")
            
            # Add content mix preferences
            content_mix = persona['content_mix']
            prompt_parts.extend([
                "",
                "CONTENT MIX PREFERENCES:",
                f"- Proposals: {content_mix.get('proposals', 0.7)*100:.0f}%",
                f"- Elite Replies: {content_mix.get('elite_replies', 0.2)*100:.0f}%",
                f"- Summaries: {content_mix.get('summaries', 0.1)*100:.0f}%",
            ])
            
            return "\n".join(prompt_parts)
            
        except Exception as e:
            logger.error(f"System prompt building failed: {e}")
            # Return minimal fallback prompt
            return "You are DaLeoBanks, an AI agent focused on deploying mechanisms for coordination and progress."
    
    def get_persona_versions(self) -> List[Dict[str, Any]]:
        """Get all persona versions from database"""
        try:
            with get_db_session() as session:
                versions = session.query(PersonaVersion).order_by(
                    PersonaVersion.version.desc()
                ).all()
                
                return [
                    {
                        "version": v.version,
                        "hash": v.hash,
                        "actor": v.actor,
                        "created_at": v.created_at.isoformat(),
                        "summary": self._get_version_summary(v.payload)
                    }
                    for v in versions
                ]
                
        except Exception as e:
            logger.error(f"Failed to get persona versions: {e}")
            return []
    
    def get_version_diff(self, version1: int, version2: int) -> Dict[str, Any]:
        """Get diff between two persona versions"""
        try:
            with get_db_session() as session:
                v1 = session.query(PersonaVersion).filter(PersonaVersion.version == version1).first()
                v2 = session.query(PersonaVersion).filter(PersonaVersion.version == version2).first()
                
                if not v1 or not v2:
                    raise ValueError("One or both versions not found")
                
                # Simple diff implementation
                diff = {
                    "version1": version1,
                    "version2": version2,
                    "changes": self._calculate_diff(v1.payload, v2.payload)
                }
                
                return diff
                
        except Exception as e:
            logger.error(f"Version diff failed: {e}")
            return {"error": str(e)}
    
    def _has_file_changed(self) -> bool:
        """Check if persona file has been modified"""
        try:
            if not os.path.exists(self.persona_file):
                return False
            
            current_modified = os.path.getmtime(self.persona_file)
            if current_modified > self._last_modified:
                return True

            # Hash-based fallback
            with open(self.persona_file, 'r') as f:
                data = json.load(f)
            current_hash = self._calculate_hash(data)
            return current_hash != self._current_hash
            
        except Exception as e:
            logger.error(f"File change check failed: {e}")
            return False
    
    def _calculate_hash(self, persona: Dict[str, Any]) -> str:
        """Calculate SHA256 hash of persona"""
        # Create canonical JSON string for hashing
        canonical_str = json.dumps(persona, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_str.encode()).hexdigest()
    
    def _get_version_summary(self, payload: Dict[str, Any]) -> str:
        """Get a brief summary of a persona version"""
        mission = payload.get('mission', '')[:50]
        handle = payload.get('handle', 'unknown')
        belief_count = len(payload.get('beliefs', []))
        
        return f"@{handle}: {mission}... ({belief_count} beliefs)"
    
    def _calculate_diff(self, old: Dict[str, Any], new: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Calculate differences between two persona versions"""
        changes = []
        
        # Check all keys
        all_keys = set(old.keys()) | set(new.keys())
        
        for key in all_keys:
            if key not in old:
                changes.append({
                    "field": key,
                    "type": "added",
                    "new_value": new[key]
                })
            elif key not in new:
                changes.append({
                    "field": key,
                    "type": "removed",
                    "old_value": old[key]
                })
            elif old[key] != new[key]:
                changes.append({
                    "field": key,
                    "type": "modified",
                    "old_value": old[key],
                    "new_value": new[key]
                })
        
        return changes
    
    def get_current_hash(self) -> str:
        """Get hash of current persona"""
        if not self.current_persona:
            return ""
        return self._current_hash or self._calculate_hash(self.current_persona)
    
    def export_persona(self, version: Optional[int] = None) -> Dict[str, Any]:
        """Export persona (current or specific version)"""
        if version is None:
            return self.get_current_persona()
        
        with get_db_session() as session:
            persona_version = session.query(PersonaVersion).filter(
                PersonaVersion.version == version
            ).first()
            
            if not persona_version:
                raise ValueError(f"Version {version} not found")
            
            return persona_version.payload

