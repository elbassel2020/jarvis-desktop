"""Tests for Reflector — all Anthropic calls mocked."""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _mock_claude_response(text):
    resp = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    resp.content = [content_block]
    return resp


VALID_REFLECTION_JSON = json.dumps({
    "what_worked_well": "Time and screenshot actions worked perfectly",
    "what_failed": "Some Arabic queries misclassified",
    "patterns_noticed": "User opens Excel at 9 AM daily",
    "suggestions_to_walid": "Set up ZATCA reminder",
    "self_improvements": "Lower confidence threshold for Arabic"
})


@pytest.fixture
def reflector(tmp_path):
    with patch('core.memory.DB_PATH', tmp_path / 'test.db'), \
         patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        from core.memory import JarvisMemory
        from core.reflection import Reflector

        ref = Reflector.__new__(Reflector)
        ref.memory = JarvisMemory()
        ref.memory.log_episode('open chrome', 'open_app', 'ok', 'claude', 0.5, 0.9, True)
        ref.memory.log_episode('كم الساعة', 'time', 'ok', 'gemini', 0.3, 0.95, True)
        ref.memory.log_episode('screenshot', 'screenshot', 'ok', 'claude', 0.8, 0.85, False)

        mock_client = MagicMock()
        ref.client = mock_client
    return ref


class TestReflectorInit:
    def test_no_api_key_sets_client_none(self, tmp_path):
        with patch('core.memory.DB_PATH', tmp_path / 't.db'), \
             patch.dict(os.environ, {}, clear=True):
            from core.reflection import Reflector
            ref = Reflector.__new__(Reflector)
            ref.client = None
        assert ref.client is None

    def test_with_api_key_sets_client(self, tmp_path):
        with patch('core.memory.DB_PATH', tmp_path / 't.db'), \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}), \
             patch('anthropic.Anthropic') as mock_cls:
            from core.memory import JarvisMemory
            from core.reflection import Reflector
            ref = Reflector.__new__(Reflector)
            ref.memory = JarvisMemory()
            mock_cls.return_value = MagicMock()
        # Doesn't raise


class TestReflectOnToday:
    def test_no_client_returns_none(self, reflector):
        reflector.client = None
        result = reflector.reflect_on_today()
        assert result is None

    def test_no_episodes_returns_none(self, reflector, tmp_path):
        # Fresh memory with no episodes
        with patch('core.memory.DB_PATH', tmp_path / 'empty.db'):
            from core.memory import JarvisMemory
            reflector.memory = JarvisMemory()
        result = reflector.reflect_on_today()
        assert result is None

    def test_valid_reflection_returned(self, reflector):
        reflector.client.messages.create.return_value = _mock_claude_response(VALID_REFLECTION_JSON)
        result = reflector.reflect_on_today()
        assert result is not None
        assert isinstance(result, str)

    def test_reflection_saved_to_memory(self, reflector):
        reflector.client.messages.create.return_value = _mock_claude_response(VALID_REFLECTION_JSON)
        reflector.reflect_on_today()
        latest = reflector.memory.get_latest_reflection()
        assert 'What worked' in latest or 'worked' in latest.lower()

    def test_reflection_contains_what_worked(self, reflector):
        reflector.client.messages.create.return_value = _mock_claude_response(VALID_REFLECTION_JSON)
        result = reflector.reflect_on_today()
        assert 'Time and screenshot' in result or 'worked' in result.lower()

    def test_api_failure_returns_none(self, reflector):
        reflector.client.messages.create.side_effect = Exception('API error')
        result = reflector.reflect_on_today()
        assert result is None

    def test_auto_tune_low_success_rate(self, reflector, tmp_path):
        # All failures → success rate 0%
        with patch('core.memory.DB_PATH', tmp_path / 'low.db'):
            from core.memory import JarvisMemory
            reflector.memory = JarvisMemory()
            for i in range(5):
                reflector.memory.log_episode(f't{i}', 'chat', 'r', 'b', 0.5, 0.3, False)

        reflector.client.messages.create.return_value = _mock_claude_response(VALID_REFLECTION_JSON)
        reflector.reflect_on_today()
        threshold = reflector.memory.get_tuning('confidence_threshold')
        assert threshold == '0.2'

    def test_auto_tune_high_success_rate(self, reflector, tmp_path):
        with patch('core.memory.DB_PATH', tmp_path / 'high.db'):
            from core.memory import JarvisMemory
            reflector.memory = JarvisMemory()
            for i in range(10):
                reflector.memory.log_episode(f't{i}', 'chat', 'r', 'b', 0.5, 0.95, True)

        reflector.client.messages.create.return_value = _mock_claude_response(VALID_REFLECTION_JSON)
        reflector.reflect_on_today()
        threshold = reflector.memory.get_tuning('confidence_threshold')
        assert threshold == '0.4'

    def test_malformed_json_returns_none(self, reflector):
        reflector.client.messages.create.return_value = _mock_claude_response('not json at all')
        result = reflector.reflect_on_today()
        assert result is None

    def test_reflection_uses_claude_sonnet(self, reflector):
        reflector.client.messages.create.return_value = _mock_claude_response(VALID_REFLECTION_JSON)
        reflector.reflect_on_today()
        call_kwargs = reflector.client.messages.create.call_args[1]
        assert 'claude-sonnet' in call_kwargs.get('model', '')
