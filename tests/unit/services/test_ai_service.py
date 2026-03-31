"""Tests para AgentIA."""
import pytest
from unittest.mock import Mock, patch

from domain.services.ai_service import AgentIA


class TestAgentIA:
    @pytest.fixture
    def agent(self):
        return AgentIA()
    
    def test_initialization(self, agent):
        assert agent is not None
    
    @patch('domain.services.ai_service.settings')
    def test_initialization_with_api_key(self, mock_settings):
        mock_settings.GROQ_API_KEY = 'test_key'
        mock_settings.GROQ_BASE_URL = 'https://test.com'
        mock_settings.AI_MODEL = 'test-model'
        
        agent = AgentIA()
        assert agent is not None
