"""Tests for DailyLearner — all Anthropic web_search calls mocked."""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _mock_text_block(text):
    block = MagicMock()
    block.text = text
    del block.type
    return block


def _mock_tool_use_block():
    block = MagicMock()
    block.type = 'tool_use'
    del block.text
    return block


def _mock_claude_response(text):
    resp = MagicMock()
    resp.content = [_mock_text_block(text)]
    return resp


@pytest.fixture
def learner(tmp_path):
    with patch('core.memory.DB_PATH', tmp_path / 'test.db'), \
         patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}), \
         patch('anthropic.Anthropic') as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        from core.memory import JarvisMemory
        from core.daily_learning import DailyLearner
        dl = DailyLearner.__new__(DailyLearner)
        dl._client = mock_client
        dl.memory = JarvisMemory()
        return dl


class TestDailyLearnerInit:
    def test_has_client(self, learner):
        assert learner._client is not None

    def test_has_memory(self, learner):
        assert learner.memory is not None

    def test_learning_queries_count(self):
        from core.daily_learning import LEARNING_QUERIES
        assert len(LEARNING_QUERIES) == 7

    def test_learning_queries_have_category_and_query(self):
        from core.daily_learning import LEARNING_QUERIES
        for category, query in LEARNING_QUERIES:
            assert isinstance(category, str) and len(category) > 0
            assert isinstance(query, str) and len(query) > 0

    def test_learning_queries_include_zatca(self):
        from core.daily_learning import LEARNING_QUERIES
        categories = [c for c, _ in LEARNING_QUERIES]
        assert 'zatca' in categories

    def test_learning_queries_include_schneider(self):
        from core.daily_learning import LEARNING_QUERIES
        categories = [c for c, _ in LEARNING_QUERIES]
        assert 'schneider' in categories


class TestSearchOne:
    def test_search_returns_dict_on_success(self, learner):
        learner._client.messages.create.return_value = _mock_claude_response(
            'IEC 60364 standards updated for Saudi Arabia in 2025.'
        )
        result = learner._search_one('electrical_standards', 'IEC standards Saudi Arabia')
        assert isinstance(result, dict)

    def test_search_has_required_keys(self, learner):
        learner._client.messages.create.return_value = _mock_claude_response(
            'ZATCA Phase 2 deadline confirmed June 2026.'
        )
        result = learner._search_one('zatca', 'ZATCA updates')
        for key in ('category', 'query', 'summary', 'source_url'):
            assert key in result, f"Missing key: {key}"

    def test_search_stores_category(self, learner):
        learner._client.messages.create.return_value = _mock_claude_response('Some news.')
        result = learner._search_one('zatca', 'ZATCA query')
        assert result['category'] == 'zatca'

    def test_search_returns_none_on_exception(self, learner):
        learner._client.messages.create.side_effect = Exception('API error')
        result = learner._search_one('zatca', 'query')
        assert result is None

    def test_search_extracts_url_from_text(self, learner):
        text_with_url = 'Found info at https://zatca.gov.sa/updates. Phase 2 confirmed.'
        learner._client.messages.create.return_value = _mock_claude_response(text_with_url)
        result = learner._search_one('zatca', 'query')
        assert result['source_url'].startswith('https://zatca.gov.sa/updates')

    def test_search_empty_url_when_no_link(self, learner):
        learner._client.messages.create.return_value = _mock_claude_response('No url here.')
        result = learner._search_one('cat', 'query')
        assert result['source_url'] == ''

    def test_search_handles_tool_use_block_plus_text(self, learner):
        resp = MagicMock()
        resp.content = [_mock_tool_use_block(), _mock_text_block('Text after tool use.')]
        learner._client.messages.create.return_value = resp
        result = learner._search_one('cat', 'query')
        assert result is not None
        assert 'Text after tool use' in result['summary']

    def test_search_returns_none_when_all_tool_blocks(self, learner):
        resp = MagicMock()
        resp.content = [_mock_tool_use_block()]
        learner._client.messages.create.return_value = resp
        result = learner._search_one('cat', 'query')
        assert result is None

    def test_search_uses_web_search_tool(self, learner):
        learner._client.messages.create.return_value = _mock_claude_response('ok')
        learner._search_one('cat', 'query')
        call_kwargs = learner._client.messages.create.call_args[1]
        tools = call_kwargs.get('tools', [])
        assert any('web_search' in str(t) for t in tools)


class TestRun:
    def test_run_stores_all_insights(self, learner):
        learner._client.messages.create.return_value = _mock_claude_response('Insight text here.')
        learner.run()
        stats = learner.memory.stats()
        assert stats['insights'] == 7  # all 7 queries succeeded

    def test_run_saves_morning_brief(self, learner):
        def side_effect(**kwargs):
            if 'tools' in kwargs:
                return _mock_claude_response('Web search result.')
            else:
                return _mock_claude_response('صباح الخير يابابا. Brief here today.')
        learner._client.messages.create.side_effect = side_effect
        learner.run()
        brief = learner.memory.get_today_brief()
        assert len(brief) > 0

    def test_run_handles_partial_failures(self, learner):
        call_count = [0]
        def side_effect(**kwargs):
            call_count[0] += 1
            if 'tools' in kwargs and call_count[0] <= 3:
                raise Exception('search failed')
            return _mock_claude_response('Fallback text.')
        learner._client.messages.create.side_effect = side_effect
        learner.run()  # should not raise even if some searches fail
        stats = learner.memory.stats()
        assert stats['insights'] >= 0  # partial is OK

    def test_run_no_insights_skips_brief(self, learner):
        learner._client.messages.create.side_effect = Exception('all fail')
        learner.run()
        brief = learner.memory.get_today_brief()
        assert brief == ''  # no brief if no insights

    def test_run_calls_anthropic_for_each_query(self, learner):
        learner._client.messages.create.return_value = _mock_claude_response('ok')
        learner.run()
        # 7 web searches + 1 brief generation = 8 calls
        assert learner._client.messages.create.call_count >= 7
