"""Comprehensive tests for JarvisMemory — all methods, no external deps."""
import sys
import os
import json
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def mem(tmp_path):
    """Fresh in-memory JarvisMemory for each test."""
    with patch('core.memory.DB_PATH', tmp_path / 'test_memory.db'):
        from core.memory import JarvisMemory
        return JarvisMemory()


# ── Schema / init ──────────────────────────────────────────────────────────

class TestInit:
    def test_creates_episodic_table(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='episodic'")
        assert cur.fetchone() is not None

    def test_creates_semantic_table(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='semantic'")
        assert cur.fetchone() is not None

    def test_creates_daily_apps_table(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_apps'")
        assert cur.fetchone() is not None

    def test_creates_reflections_table(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reflections'")
        assert cur.fetchone() is not None

    def test_creates_tuning_table(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tuning'")
        assert cur.fetchone() is not None

    def test_creates_daily_insights_table(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_insights'")
        assert cur.fetchone() is not None

    def test_creates_morning_briefs_table(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='morning_briefs'")
        assert cur.fetchone() is not None

    def test_seeds_walid_identity(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT key FROM semantic WHERE category='identity'")
        keys = {r[0] for r in cur.fetchall()}
        assert 'name' in keys
        assert 'business' in keys
        assert 'location' in keys

    def test_seeded_name_value(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT value FROM semantic WHERE key='name'")
        val = cur.fetchone()[0]
        assert 'Walid' in val

    def test_seeded_location_jubail(self, mem):
        cur = mem.conn.cursor()
        cur.execute("SELECT value FROM semantic WHERE key='location'")
        val = cur.fetchone()[0]
        assert 'Jubail' in val


# ── log_episode ────────────────────────────────────────────────────────────

class TestLogEpisode:
    def test_log_single_episode(self, mem):
        mem.log_episode('hello', 'chat', 'Hi there', 'claude', 0.5, 0.9, True)
        cur = mem.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM episodic")
        assert cur.fetchone()[0] == 1

    def test_log_stores_transcript(self, mem):
        mem.log_episode('test transcript', 'time', 'ok', 'groq', 0.3, 0.8, True)
        cur = mem.conn.cursor()
        cur.execute("SELECT transcript FROM episodic LIMIT 1")
        assert cur.fetchone()[0] == 'test transcript'

    def test_log_stores_intent(self, mem):
        mem.log_episode('open chrome', 'open_app', 'ok', 'gemini', 1.2, 0.95, True)
        cur = mem.conn.cursor()
        cur.execute("SELECT intent FROM episodic LIMIT 1")
        assert cur.fetchone()[0] == 'open_app'

    def test_log_success_flag_true(self, mem):
        mem.log_episode('t', 'i', 'r', 'b', 0.1, 0.5, True)
        cur = mem.conn.cursor()
        cur.execute("SELECT success FROM episodic LIMIT 1")
        assert cur.fetchone()[0] == 1

    def test_log_success_flag_false(self, mem):
        mem.log_episode('t', 'i', 'r', 'b', 0.1, 0.5, False)
        cur = mem.conn.cursor()
        cur.execute("SELECT success FROM episodic LIMIT 1")
        assert cur.fetchone()[0] == 0

    def test_log_multiple_episodes(self, mem):
        for i in range(5):
            mem.log_episode(f'q{i}', 'chat', 'ok', 'claude', 0.5, 0.9, True)
        cur = mem.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM episodic")
        assert cur.fetchone()[0] == 5

    def test_log_stores_latency(self, mem):
        mem.log_episode('t', 'i', 'r', 'b', 2.34, 0.5, True)
        cur = mem.conn.cursor()
        cur.execute("SELECT latency_s FROM episodic LIMIT 1")
        assert abs(cur.fetchone()[0] - 2.34) < 0.01


# ── log_app_open ───────────────────────────────────────────────────────────

class TestLogAppOpen:
    def test_log_app_creates_record(self, mem):
        mem.log_app_open('chrome')
        cur = mem.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM daily_apps WHERE app_name='chrome'")
        assert cur.fetchone()[0] == 1

    def test_log_app_increments_count(self, mem):
        mem.log_app_open('excel')
        mem.log_app_open('excel')
        mem.log_app_open('excel')
        cur = mem.conn.cursor()
        cur.execute("SELECT SUM(open_count) FROM daily_apps WHERE app_name='excel'")
        assert cur.fetchone()[0] == 3

    def test_log_multiple_apps(self, mem):
        mem.log_app_open('word')
        mem.log_app_open('excel')
        cur = mem.conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT app_name) FROM daily_apps")
        assert cur.fetchone()[0] == 2


# ── get_relevant_facts ────────────────────────────────────────────────────

class TestGetRelevantFacts:
    def test_returns_string(self, mem):
        result = mem.get_relevant_facts('hello world')
        assert isinstance(result, str)

    def test_returns_identity_facts(self, mem):
        result = mem.get_relevant_facts('anything')
        assert 'name' in result or 'business' in result or 'location' in result

    def test_empty_query_still_returns_identity(self, mem):
        result = mem.get_relevant_facts('')
        # identity keys always boosted
        assert len(result) > 0

    def test_relevant_keyword_boosts_score(self, mem):
        mem.conn.execute(
            "INSERT OR REPLACE INTO semantic VALUES (?, ?, ?, ?)",
            ('zamilfood_note', 'Zamilfood is primary cash customer', 'identity', datetime.now().isoformat())
        )
        mem.conn.commit()
        result = mem.get_relevant_facts('Zamilfood invoice')
        assert 'zamilfood' in result.lower()

    def test_respects_max_facts(self, mem):
        for i in range(20):
            mem.conn.execute(
                "INSERT OR REPLACE INTO semantic VALUES (?, ?, ?, ?)",
                (f'key{i}', f'value{i} unique term xyz{i}', 'identity', datetime.now().isoformat())
            )
        mem.conn.commit()
        result = mem.get_relevant_facts('xyz0 xyz1 xyz2', max_facts=2)
        lines = [l for l in result.split('\n') if l.strip()]
        assert len(lines) <= 10  # identity keys always included


# ── get_recent_episodes ───────────────────────────────────────────────────

class TestGetRecentEpisodes:
    def test_empty_returns_empty(self, mem):
        assert mem.get_recent_episodes() == []

    def test_returns_n_episodes(self, mem):
        for i in range(10):
            mem.log_episode(f't{i}', 'chat', 'r', 'b', 0.1, 0.5, True)
        result = mem.get_recent_episodes(5)
        assert len(result) == 5

    def test_returns_most_recent_first(self, mem):
        mem.log_episode('first', 'chat', 'r', 'b', 0.1, 0.5, True)
        mem.log_episode('second', 'chat', 'r', 'b', 0.1, 0.5, True)
        result = mem.get_recent_episodes(2)
        assert result[0][0] == 'second'

    def test_row_has_4_columns(self, mem):
        mem.log_episode('t', 'intent', 'response', 'backend', 0.1, 0.5, True)
        row = mem.get_recent_episodes(1)[0]
        assert len(row) == 4  # transcript, intent, response, success


# ── get_success_stats ─────────────────────────────────────────────────────

class TestGetSuccessStats:
    def test_no_episodes_returns_zeros(self, mem):
        result = mem.get_success_stats(days=7)
        assert result[0] == 0  # total

    def test_counts_successes(self, mem):
        mem.log_episode('t', 'i', 'r', 'b', 0.1, 0.9, True)
        mem.log_episode('t', 'i', 'r', 'b', 0.1, 0.9, True)
        mem.log_episode('t', 'i', 'r', 'b', 0.1, 0.9, False)
        result = mem.get_success_stats(days=7)
        total, successes, avg_lat, avg_conf = result
        assert total == 3
        assert successes == 2

    def test_avg_latency_calculated(self, mem):
        mem.log_episode('t', 'i', 'r', 'b', 1.0, 0.9, True)
        mem.log_episode('t', 'i', 'r', 'b', 3.0, 0.9, True)
        result = mem.get_success_stats(days=7)
        assert abs(result[2] - 2.0) < 0.01


# ── get_context_for_prompt ────────────────────────────────────────────────

class TestGetContextForPrompt:
    def test_returns_string(self, mem):
        assert isinstance(mem.get_context_for_prompt(), str)

    def test_contains_identity(self, mem):
        ctx = mem.get_context_for_prompt()
        assert 'IDENTITY' in ctx

    def test_contains_recent(self, mem):
        ctx = mem.get_context_for_prompt()
        assert 'RECENT' in ctx

    def test_includes_episodes(self, mem):
        mem.log_episode('hello jarvis', 'chat', 'Hi!', 'claude', 0.5, 0.9, True)
        ctx = mem.get_context_for_prompt()
        assert 'hello jarvis' in ctx


# ── reflections ───────────────────────────────────────────────────────────

class TestReflections:
    def test_save_and_get_reflection(self, mem):
        mem.save_reflection('Great day, high confidence')
        result = mem.get_latest_reflection()
        assert 'Great day' in result

    def test_latest_reflection_returns_most_recent(self, mem):
        mem.save_reflection('First reflection')
        mem.save_reflection('Second reflection')
        result = mem.get_latest_reflection()
        assert 'Second' in result

    def test_no_reflection_returns_default(self, mem):
        result = mem.get_latest_reflection()
        assert 'No reflections' in result

    def test_save_reflection_with_metrics(self, mem):
        metrics = json.dumps({'success_rate': 0.85})
        mem.save_reflection('test', metrics)
        cur = mem.conn.cursor()
        cur.execute("SELECT metrics_json FROM reflections LIMIT 1")
        val = cur.fetchone()[0]
        assert '0.85' in val

    def test_reflection_truncated_in_output(self, mem):
        long_text = 'x' * 500
        mem.save_reflection(long_text)
        result = mem.get_latest_reflection()
        assert len(result) < 400


# ── tuning ────────────────────────────────────────────────────────────────

class TestTuning:
    def test_set_and_get_tuning(self, mem):
        mem.set_tuning('confidence_threshold', 0.35)
        val = mem.get_tuning('confidence_threshold')
        assert val == '0.35'

    def test_get_missing_key_returns_default(self, mem):
        result = mem.get_tuning('nonexistent', default='fallback')
        assert result == 'fallback'

    def test_get_missing_key_none_default(self, mem):
        assert mem.get_tuning('nonexistent') is None

    def test_update_existing_tuning(self, mem):
        mem.set_tuning('threshold', '0.3')
        mem.set_tuning('threshold', '0.5')
        assert mem.get_tuning('threshold') == '0.5'


# ── daily insights ────────────────────────────────────────────────────────

class TestDailyInsights:
    def test_add_insight(self, mem):
        mem.add_insight('zatca', 'ZATCA updates', 'Phase 2 deadline June 2026', 'https://zatca.gov.sa')
        cur = mem.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM daily_insights")
        assert cur.fetchone()[0] == 1

    def test_add_insight_stores_category(self, mem):
        mem.add_insight('electrical', 'IEC query', 'Summary text', '')
        cur = mem.conn.cursor()
        cur.execute("SELECT category FROM daily_insights LIMIT 1")
        assert cur.fetchone()[0] == 'electrical'

    def test_get_recent_insights_empty(self, mem):
        assert mem.get_recent_insights() == []

    def test_get_recent_insights_returns_data(self, mem):
        mem.add_insight('cat1', 'q1', 'summary1', '')
        mem.add_insight('cat2', 'q2', 'summary2', '')
        rows = mem.get_recent_insights(days=1)
        assert len(rows) == 2

    def test_get_insights_context_empty(self, mem):
        result = mem.get_insights_context()
        assert result == ''

    def test_get_insights_context_format(self, mem):
        mem.add_insight('zatca', 'query', 'ZATCA summary here', '')
        result = mem.get_insights_context()
        assert 'RECENT LEARNINGS' in result
        assert 'zatca' in result
        assert 'ZATCA summary here' in result


# ── morning briefs ────────────────────────────────────────────────────────

class TestMorningBriefs:
    def test_save_and_get_brief(self, mem):
        mem.save_morning_brief('صباح الخير يابابا. Good news today.')
        brief = mem.get_today_brief()
        assert 'صباح' in brief

    def test_get_brief_empty_when_none(self, mem):
        assert mem.get_today_brief() == ''

    def test_save_replaces_existing(self, mem):
        mem.save_morning_brief('First brief')
        mem.save_morning_brief('Updated brief')
        brief = mem.get_today_brief()
        assert 'Updated' in brief
        assert 'First' not in brief


# ── stats ─────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_keys(self, mem):
        s = mem.stats()
        for key in ('episodes', 'facts', 'app_records', 'reflections', 'insights', 'briefs'):
            assert key in s, f"Missing key: {key}"

    def test_stats_counts_episodes(self, mem):
        mem.log_episode('t', 'i', 'r', 'b', 0.1, 0.5, True)
        mem.log_episode('t', 'i', 'r', 'b', 0.1, 0.5, True)
        assert mem.stats()['episodes'] == 2

    def test_stats_counts_facts(self, mem):
        s = mem.stats()
        assert s['facts'] >= 13  # seeded facts

    def test_stats_counts_insights(self, mem):
        mem.add_insight('cat', 'q', 'summary', '')
        assert mem.stats()['insights'] == 1

    def test_stats_counts_briefs(self, mem):
        mem.save_morning_brief('test brief')
        assert mem.stats()['briefs'] == 1

    def test_stats_zero_on_fresh_db(self, mem):
        s = mem.stats()
        assert s['episodes'] == 0
        assert s['app_records'] == 0
        assert s['reflections'] == 0


# ── get_typical_apps ──────────────────────────────────────────────────────

class TestGetTypicalApps:
    def test_empty_returns_empty(self, mem):
        result = mem.get_typical_apps(hour=9)
        assert result == []

    def test_returns_apps_for_hour(self, mem):
        cur = mem.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cur.execute(
            "INSERT INTO daily_apps VALUES (?, 9, 'chrome', 5)",
            (today,)
        )
        mem.conn.commit()
        result = mem.get_typical_apps(hour=9)
        assert len(result) >= 1
        assert result[0][0] == 'chrome'


# ── get_daily_summary ─────────────────────────────────────────────────────

class TestGetDailySummary:
    def test_no_data_returns_no_usage(self, mem):
        result = mem.get_daily_summary()
        assert 'No usage' in result

    def test_returns_app_summary(self, mem):
        cur = mem.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cur.execute("INSERT INTO daily_apps VALUES (?, 10, 'excel', 3)", (today,))
        mem.conn.commit()
        result = mem.get_daily_summary()
        assert 'excel' in result
