"""Tests for BrainRouter routing logic + classify_complexity — mocked LLMs."""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── classify_complexity ───────────────────────────────────────────────────

class TestClassifyComplexity:
    def test_simple_empty(self):
        from core.brain_router import classify_complexity
        assert classify_complexity('') == 'simple'

    def test_simple_1_word(self):
        from core.brain_router import classify_complexity
        assert classify_complexity('hello') == 'simple'

    def test_simple_6_words(self):
        from core.brain_router import classify_complexity
        assert classify_complexity('open chrome browser for me now') == 'simple'

    def test_medium_7_words(self):
        from core.brain_router import classify_complexity
        assert classify_complexity('what is the best way to open excel') == 'medium'

    def test_medium_15_words(self):
        from core.brain_router import classify_complexity
        text = ' '.join(['word'] * 15)
        assert classify_complexity(text) == 'medium'

    def test_complex_16_words(self):
        from core.brain_router import classify_complexity
        text = ' '.join(['word'] * 16)
        assert classify_complexity(text) == 'complex'

    def test_complex_long_sentence(self):
        from core.brain_router import classify_complexity
        text = 'explain to me in detail how i should manage my ZATCA e-invoicing compliance for phase 2 deadline'
        assert classify_complexity(text) == 'complex'

    def test_arabic_simple(self):
        from core.brain_router import classify_complexity
        assert classify_complexity('كم الساعة') == 'simple'

    def test_arabic_medium(self):
        from core.brain_router import classify_complexity
        text = 'ايه الفرق بين شنايدر و ABB في المحولات الصناعية'
        assert classify_complexity(text) == 'medium'


# ── _parse_result ─────────────────────────────────────────────────────────

class TestParseResult:
    def test_clean_json(self):
        from core.brain_router import _parse_result
        raw = '{"action":"time","params":null,"spoken":"ok","detailed":"","confirmation_required":false,"confidence":1.0,"thinking":"x"}'
        result = _parse_result(raw)
        assert result['action'] == 'time'
        assert result['confidence'] == 1.0

    def test_json_with_markdown_fence(self):
        from core.brain_router import _parse_result
        raw = '```json\n{"action":"chat","params":null,"spoken":"hi","detailed":"","confirmation_required":false,"confidence":0.9,"thinking":"t"}\n```'
        result = _parse_result(raw)
        assert result['action'] == 'chat'

    def test_json_with_trailing_comma(self):
        from core.brain_router import _parse_result
        raw = '{"action":"time","params":null,"spoken":"ok","detailed":"","confirmation_required":false,"confidence":1.0,"thinking":"x",}'
        result = _parse_result(raw)
        assert result['action'] == 'time'

    def test_json_embedded_in_text(self):
        from core.brain_router import _parse_result
        raw = 'Here is my answer: {"action":"screenshot","params":null,"spoken":"ok","detailed":"","confirmation_required":false,"confidence":0.95,"thinking":"t"}'
        result = _parse_result(raw)
        assert result['action'] == 'screenshot'

    def test_invalid_json_raises(self):
        from core.brain_router import _parse_result
        with pytest.raises(Exception):
            _parse_result('this is not json at all')


# ── _build_result ─────────────────────────────────────────────────────────

class TestBuildResult:
    def test_has_all_keys(self):
        from core.brain_router import _build_result
        parsed = {
            'action': 'time', 'params': None, 'spoken': 'ok',
            'detailed': '', 'thinking': 'test', 'confirmation_required': False,
            'confidence': 0.9
        }
        result = _build_result(parsed, 0.5, 'test transcript', 'claude')
        for key in ('action', 'params', 'spoken', 'detailed', 'response', 'thinking',
                    'confirmation_required', 'confidence', 'duration_s', 'raw_text', 'backend'):
            assert key in result, f"Missing key: {key}"

    def test_response_equals_spoken(self):
        from core.brain_router import _build_result
        parsed = {'action': 'chat', 'spoken': 'Hello Boss', 'detailed': '', 'thinking': '', 'confirmation_required': False, 'confidence': 0.8}
        result = _build_result(parsed, 1.0, 'hi', 'claude')
        assert result['response'] == result['spoken']

    def test_duration_stored(self):
        from core.brain_router import _build_result
        parsed = {'action': 'chat', 'spoken': 'x', 'detailed': '', 'thinking': '', 'confirmation_required': False, 'confidence': 0.5}
        result = _build_result(parsed, 2.34, 'q', 'gemini')
        assert abs(result['duration_s'] - 2.34) < 0.01

    def test_backend_stored(self):
        from core.brain_router import _build_result
        parsed = {'action': 'time', 'spoken': 'x', 'detailed': '', 'thinking': '', 'confirmation_required': False, 'confidence': 0.9}
        result = _build_result(parsed, 0.5, 'q', 'anthropic/claude-sonnet-4-6')
        assert result['backend'] == 'anthropic/claude-sonnet-4-6'

    def test_confirmation_required_bool(self):
        from core.brain_router import _build_result
        parsed = {'action': 'close_app', 'spoken': 'confirm?', 'detailed': '', 'thinking': '', 'confirmation_required': True, 'confidence': 0.9}
        result = _build_result(parsed, 0.5, 'close chrome', 'gemini')
        assert result['confirmation_required'] is True

    def test_confidence_float(self):
        from core.brain_router import _build_result
        parsed = {'action': 'chat', 'spoken': 'x', 'detailed': '', 'thinking': '', 'confirmation_required': False, 'confidence': '0.85'}
        result = _build_result(parsed, 0.5, 'q', 'b')
        assert isinstance(result['confidence'], float)


# ── BrainRouter init ──────────────────────────────────────────────────────

class TestBrainRouterInit:
    def test_fallback_model_attribute(self):
        with patch('core.memory.JarvisMemory'), \
             patch('core.screen_awareness.ScreenAwareness'), \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY': '', 'GEMINI_API_KEY': ''}):
            from core.brain_router import BrainRouter
            router = BrainRouter()
        assert hasattr(router, '_fallback_model')

    def test_fallback_model_default(self):
        with patch('core.memory.JarvisMemory'), \
             patch('core.screen_awareness.ScreenAwareness'), \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY': '', 'GEMINI_API_KEY': ''}):
            from core.brain_router import BrainRouter
            router = BrainRouter()
        assert router._fallback_model == 'qwen2.5:7b'

    def test_fallback_model_from_env(self):
        with patch('core.memory.JarvisMemory'), \
             patch('core.screen_awareness.ScreenAwareness'), \
             patch.dict(os.environ, {'LLM_FALLBACK': 'llama3.1:8b', 'ANTHROPIC_API_KEY': '', 'GEMINI_API_KEY': ''}):
            from core.brain_router import BrainRouter
            router = BrainRouter()
        assert router._fallback_model == 'llama3.1:8b'


# ── think — routing logic ─────────────────────────────────────────────────

class TestThinkRouting:
    def _make_router(self, has_claude=True, has_gemini=True):
        mock_mem = MagicMock()
        mock_mem.get_relevant_facts.return_value = '- name: Walid'
        mock_mem.get_latest_reflection.return_value = 'No reflections yet'
        mock_mem.get_insights_context.return_value = ''
        mock_mem.get_today_brief.return_value = ''

        mock_screen = MagicMock()
        mock_screen.summary.return_value = 'Desktop empty'

        with patch('core.memory.JarvisMemory', return_value=mock_mem), \
             patch('core.screen_awareness.ScreenAwareness', return_value=mock_screen):
            from core.brain_router import BrainRouter
            router = BrainRouter.__new__(BrainRouter)
            router.memory = mock_mem
            router.screen = mock_screen
            router._fallback_model = 'qwen2.5:7b'
            router._claude = MagicMock() if has_claude else None
            router._genai = MagicMock() if has_gemini else None
            router._genai_client = MagicMock() if has_gemini else None
            router._qwen = None
        return router

    def _good_result(self, action='chat'):
        return {
            'action': action, 'params': None, 'spoken': 'ok', 'detailed': '',
            'response': 'ok', 'thinking': 'test', 'confirmation_required': False,
            'confidence': 0.9, 'duration_s': 0.5, 'raw_text': 'q', 'backend': 'test',
        }

    def test_empty_transcript_returns_cancel(self):
        router = self._make_router()
        result = router.think('')
        assert result['action'] == 'cancel'
        assert result['confidence'] == 0.0

    def test_whitespace_only_returns_cancel(self):
        router = self._make_router()
        result = router.think('   ')
        assert result['action'] == 'cancel'

    def test_simple_query_tries_gemini_first(self):
        router = self._make_router()
        call_order = []
        with patch.object(router, '_call_gemini', side_effect=lambda t: call_order.append('gemini') or self._good_result()), \
             patch.object(router, '_call_claude', side_effect=lambda t, m, **kw: call_order.append('claude') or self._good_result()):
            router.think('hi')  # 1 word = simple
        assert 'gemini' in call_order
        assert call_order[0] == 'gemini'

    def test_medium_query_tries_claude_first(self):
        router = self._make_router()
        call_order = []
        with patch.object(router, '_call_claude', side_effect=lambda t, m, **kw: call_order.append('claude') or self._good_result()), \
             patch.object(router, '_call_gemini', side_effect=lambda t: call_order.append('gemini') or self._good_result()):
            router.think('what is the best way to open excel for work')  # 9 words = medium
        assert 'claude' in call_order
        assert call_order[0] == 'claude'

    def test_complex_query_uses_web_search(self):
        router = self._make_router()
        call_kwargs = {}
        def mock_claude(t, model, use_web=False, **kw):
            call_kwargs['use_web'] = use_web
            return self._good_result()
        with patch.object(router, '_call_claude', side_effect=mock_claude):
            router.think(' '.join(['word'] * 20))  # 20 words = complex
        assert call_kwargs.get('use_web') is True

    def test_all_backends_fail_returns_error(self):
        router = self._make_router()
        with patch.object(router, '_call_gemini', side_effect=Exception('gemini fail')), \
             patch.object(router, '_call_claude', side_effect=Exception('claude fail')):
            with patch.object(router, '_call_qwen', side_effect=Exception('qwen fail')):
                result = router.think('simple question')
        assert result['action'] == 'chat'
        assert result['confidence'] == 0.0

    def test_fallback_to_qwen_on_others_fail(self):
        router = self._make_router()
        qwen_result = self._good_result('time')
        with patch.object(router, '_call_gemini', side_effect=Exception('fail')), \
             patch.object(router, '_call_claude', side_effect=Exception('fail')), \
             patch.object(router, '_call_qwen', return_value=qwen_result):
            result = router.think('كم الساعة')
        assert result['action'] == 'time'

    def test_result_has_complexity_key(self):
        router = self._make_router()
        with patch.object(router, '_call_gemini', return_value=self._good_result()):
            result = router.think('hi')
        assert 'complexity' in result

    def test_no_gemini_skips_gemini(self):
        router = self._make_router(has_gemini=False)
        call_order = []
        with patch.object(router, '_call_claude', side_effect=lambda t, m, **kw: call_order.append('claude') or self._good_result()):
            router.think('hi')
        assert 'claude' in call_order

    def test_no_claude_skips_claude(self):
        router = self._make_router(has_claude=False)
        call_order = []
        with patch.object(router, '_call_gemini', side_effect=lambda t: call_order.append('gemini') or self._good_result()):
            router.think('hi')
        assert 'gemini' in call_order


# ── _full_system ──────────────────────────────────────────────────────────

class TestFullSystem:
    def _make_router(self):
        mock_mem = MagicMock()
        mock_mem.get_relevant_facts.return_value = '- name: Walid'
        mock_mem.get_latest_reflection.return_value = 'Reflection text'
        mock_mem.get_insights_context.return_value = 'RECENT LEARNINGS:\n- [zatca] summary'
        mock_mem.get_today_brief.return_value = 'صباح الخير يابابا. Brief here.'

        mock_screen = MagicMock()
        mock_screen.summary.return_value = 'Open: chrome: Google'

        with patch('core.memory.JarvisMemory', return_value=mock_mem), \
             patch('core.screen_awareness.ScreenAwareness', return_value=mock_screen):
            from core.brain_router import BrainRouter
            router = BrainRouter.__new__(BrainRouter)
            router.memory = mock_mem
            router.screen = mock_screen
        return router

    def test_contains_system_prompt(self):
        from core.brain_router import SYSTEM_PROMPT
        router = self._make_router()
        result = router._full_system('hello')
        assert 'Jarvis' in result

    def test_contains_relevant_context(self):
        router = self._make_router()
        result = router._full_system('hello')
        assert 'RELEVANT CONTEXT' in result

    def test_contains_desktop_state(self):
        router = self._make_router()
        result = router._full_system('hello')
        assert 'DESKTOP NOW' in result

    def test_contains_insights_when_present(self):
        router = self._make_router()
        result = router._full_system('hello')
        assert 'RECENT LEARNINGS' in result

    def test_contains_brief_when_present(self):
        router = self._make_router()
        result = router._full_system('hello')
        assert "TODAY'S BRIEF" in result

    def test_no_insights_not_injected(self):
        router = self._make_router()
        router.memory.get_insights_context.return_value = ''
        result = router._full_system('hello')
        assert 'RECENT LEARNINGS' not in result

    def test_no_brief_not_injected(self):
        router = self._make_router()
        router.memory.get_today_brief.return_value = ''
        result = router._full_system('hello')
        assert "TODAY'S BRIEF" not in result
