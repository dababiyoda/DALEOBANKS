"""
Tests for persona management system
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock

from services.persona_store import PersonaStore, PersonaSchema
from db.session import get_db_session
from db.models import PersonaVersion

class TestPersonaStore:
    """Test persona store functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.test_persona = {
            "version": 1,
            "handle": "TestBot",
            "mission": "Test mission",
            "beliefs": ["Test belief 1", "Test belief 2"],
            "doctrine": ["Test", "Verify", "Deploy"],
            "tone_rules": {
                "people": "Be respectful",
                "systems": "Be direct"
            },
            "content_mix": {
                "proposals": 0.7,
                "elite_replies": 0.2,
                "summaries": 0.1
            },
            "guardrails": ["no_harm", "no_deception"],
            "templates": {
                "tweet": "Problem → Solution → Test",
                "reply": "Address → Suggest → Next"
            },
            "prompt_overrides": None
        }
        
        # Create temporary persona file
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        json.dump(self.test_persona, self.temp_file)
        self.temp_file.close()
        
        self.persona_store = PersonaStore(persona_file=self.temp_file.name)
    
    def teardown_method(self):
        """Cleanup test fixtures"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    def test_persona_validation(self):
        """Test persona validation against schema"""
        # Valid persona should pass
        validated = self.persona_store.validate_persona(self.test_persona)
        assert validated["handle"] == "TestBot"
        assert validated["mission"] == "Test mission"
        
        # Invalid persona should fail
        invalid_persona = self.test_persona.copy()
        invalid_persona["content_mix"] = {"proposals": 0.5}  # Doesn't sum to 1.0
        
        with pytest.raises(ValueError):
            self.persona_store.validate_persona(invalid_persona)
    
    def test_persona_loading(self):
        """Test persona loading from file"""
        persona = self.persona_store.get_current_persona()
        
        assert persona["handle"] == "TestBot"
        assert persona["mission"] == "Test mission"
        assert len(persona["beliefs"]) == 2
        assert persona["content_mix"]["proposals"] == 0.7
    
    @patch('services.persona_store.get_db_session')
    def test_persona_update(self, mock_db_session):
        """Test persona update with versioning"""
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        
        # Update persona
        new_persona = self.test_persona.copy()
        new_persona["mission"] = "Updated test mission"
        
        new_version = self.persona_store.update_persona(new_persona, actor="test")
        
        # Verify version incremented
        assert new_version == 2
        
        # Verify database interaction
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify file was updated
        with open(self.temp_file.name, 'r') as f:
            updated_persona = json.load(f)
        assert updated_persona["mission"] == "Updated test mission"
        assert updated_persona["version"] == 2

    def test_persona_preview(self):
        """Validate persona preview without saving"""
        preview = self.persona_store.preview_persona(self.test_persona)
        assert preview["validated"]["handle"] == "TestBot"
        assert "system" in preview["system_preview"]
    
    def test_system_prompt_building(self):
        """Test system prompt construction"""
        recent_notes = ["Test improvement 1", "Test improvement 2"]
        
        system_prompt = self.persona_store.build_system_prompt(recent_notes)
        
        # Check that all components are included
        assert "TestBot" in system_prompt
        assert "Test mission" in system_prompt
        assert "Test belief 1" in system_prompt
        assert "Problem → Solution → Test" in system_prompt
        assert "Test improvement 1" in system_prompt
        assert "70%" in system_prompt  # Content mix percentage
    
    def test_persona_hash_calculation(self):
        """Test identity hash calculation"""
        hash1 = self.persona_store._calculate_hash(self.test_persona)
        
        # Same persona should produce same hash
        hash2 = self.persona_store._calculate_hash(self.test_persona)
        assert hash1 == hash2
        
        # Different persona should produce different hash
        different_persona = self.test_persona.copy()
        different_persona["mission"] = "Different mission"
        hash3 = self.persona_store._calculate_hash(different_persona)
        assert hash1 != hash3
    
    def test_file_change_detection(self):
        """Test file change detection and hot reload"""
        # Initial state
        original_mission = self.persona_store.get_current_persona()["mission"]
        
        # Modify file
        modified_persona = self.test_persona.copy()
        modified_persona["mission"] = "File changed mission"
        
        with open(self.temp_file.name, 'w') as f:
            json.dump(modified_persona, f)
        
        # File change should be detected and persona reloaded
        updated_persona = self.persona_store.get_current_persona()
        assert updated_persona["mission"] == "File changed mission"
        assert updated_persona["mission"] != original_mission

class TestPersonaSchema:
    """Test Pydantic schema validation"""
    
    def test_valid_persona_schema(self):
        """Test valid persona passes schema validation"""
        valid_data = {
            "version": 1,
            "handle": "ValidBot",
            "mission": "Valid mission",
            "beliefs": ["Belief 1"],
            "doctrine": ["Step1", "Step2"],
            "tone_rules": {"people": "Be nice"},
            "content_mix": {"proposals": 1.0},
            "guardrails": ["safety"],
            "templates": {"tweet": "Template"}
        }
        
        schema = PersonaSchema(**valid_data)
        assert schema.handle == "ValidBot"
        assert schema.content_mix["proposals"] == 1.0
    
    def test_invalid_content_mix(self):
        """Test content mix validation"""
        invalid_data = {
            "version": 1,
            "handle": "InvalidBot",
            "mission": "Mission",
            "beliefs": ["Belief"],
            "doctrine": ["Step"],
            "tone_rules": {"people": "Rule"},
            "content_mix": {"proposals": 0.5, "replies": 0.3},  # Sums to 0.8, not 1.0
            "guardrails": ["safety"],
            "templates": {"tweet": "Template"}
        }
        
        with pytest.raises(ValueError, match="Content mix must sum to"):
            PersonaSchema(**invalid_data)
    
    def test_invalid_handle(self):
        """Test handle validation"""
        invalid_data = {
            "version": 1,
            "handle": "Invalid@Handle!",  # Contains special characters
            "mission": "Mission",
            "beliefs": ["Belief"],
            "doctrine": ["Step"],
            "tone_rules": {"people": "Rule"},
            "content_mix": {"proposals": 1.0},
            "guardrails": ["safety"],
            "templates": {"tweet": "Template"}
        }
        
        with pytest.raises(ValueError, match="Handle must be alphanumeric"):
            PersonaSchema(**invalid_data)

class TestPersonaVersioning:
    """Test persona versioning and rollback functionality"""
    
    @patch('services.persona_store.get_db_session')
    def test_persona_rollback(self, mock_db_session):
        """Test rollback to previous persona version"""
        # Setup mock database
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        
        # Mock persona version record
        mock_version = MagicMock()
        mock_version.payload = {
            "version": 1,
            "handle": "OldBot",
            "mission": "Old mission",
            "beliefs": ["Old belief"],
            "doctrine": ["Old"],
            "tone_rules": {"people": "Old rule"},
            "content_mix": {"proposals": 1.0},
            "guardrails": ["old_safety"],
            "templates": {"tweet": "Old template"}
        }
        mock_session.query.return_value.filter.return_value.first.return_value = mock_version
        
        # Create persona store with temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        current_persona = {
            "version": 2,
            "handle": "NewBot",
            "mission": "New mission",
            "beliefs": ["New belief"],
            "doctrine": ["New"],
            "tone_rules": {"people": "New rule"},
            "content_mix": {"proposals": 1.0},
            "guardrails": ["new_safety"],
            "templates": {"tweet": "New template"}
        }
        json.dump(current_persona, temp_file)
        temp_file.close()
        
        try:
            persona_store = PersonaStore(persona_file=temp_file.name)
            
            # Perform rollback
            new_version = persona_store.rollback_to_version(1, actor="test_rollback")
            
            # Verify new version was created
            assert new_version == 3
            
            # Verify current persona was updated
            updated_persona = persona_store.get_current_persona()
            assert updated_persona["handle"] == "OldBot"
            assert updated_persona["mission"] == "Old mission"
            assert updated_persona["version"] == 3
            
        finally:
            os.unlink(temp_file.name)

if __name__ == "__main__":
    pytest.main([__file__])
