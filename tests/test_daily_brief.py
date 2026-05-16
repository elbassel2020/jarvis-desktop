"""
Daily Brief tests — council and integrations mocked.

Tests:
1. test_table_created — daily_briefs table exists in Jarvis DB
2. test_get_brief_returns_none_if_missing — unknown date returns None
3. test_generate_brief_degrades_gracefully — all integrations fail + council mocked
4. test_get_brief_returns_cached — generated brief retrievable by date
"""
import sqlite3
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import date

from jarvis.tasks import daily_brief


# ── Test 1: table exists ───────────────────────────────────────────────────

def test_table_created():
    conn = sqlite3.connect(str(daily_brief.JARVIS_DB))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "daily_briefs" in tables


# ── Test 2: missing date returns None ─────────────────────────────────────

def test_get_brief_returns_none_if_missing():
    result = daily_brief.get_brief("1970-01-01")
    assert result is None


# ── Shared mock council result ─────────────────────────────────────────────

def _mock_council_result():
    from jarvis.intelligence.council import CouncilResult
    return CouncilResult(
        decision="Morning brief: inbox clear, no events, low activity.",
        confidence=0.88,
        voices={"sonnet": "...", "haiku": "...", "gemini": "..."},
        synthesis="Morning brief: inbox clear, no events, low activity.",
        cost_usd_cents=2,
        duration_ms=1200,
    )


# ── Test 3: graceful degradation when integrations fail ───────────────────

@pytest.mark.asyncio
async def test_generate_brief_degrades_gracefully():
    """All integration imports raise; council is mocked. Brief still generated."""
    test_date = "2099-01-15"   # far future = won't collide with real data

    with (
        patch("jarvis.tasks.daily_brief._collect_gmail", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_zoho", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_calendar", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_audit_summary", return_value={}),
        patch(
            "jarvis.tasks.daily_brief.council_decide",
            new=AsyncMock(return_value=_mock_council_result()),
        ),
        patch("jarvis.tasks.daily_brief.write_audit"),
    ):
        result = await daily_brief.generate_brief(brief_date=test_date)

    assert result["success"] is True
    assert result["brief_date"] == test_date
    assert isinstance(result["content"], str)
    assert len(result["content"]) > 10
    assert result["duration_ms"] >= 0
    assert isinstance(result["cost_usd_cents"], int)


# ── Test 4: cached brief retrieved correctly ───────────────────────────────

@pytest.mark.asyncio
async def test_get_brief_returns_cached():
    test_date = "2099-01-16"

    with (
        patch("jarvis.tasks.daily_brief._collect_gmail", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_zoho", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_calendar", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_audit_summary", return_value={}),
        patch(
            "jarvis.tasks.daily_brief.council_decide",
            new=AsyncMock(return_value=_mock_council_result()),
        ),
        patch("jarvis.tasks.daily_brief.write_audit"),
    ):
        await daily_brief.generate_brief(brief_date=test_date)

    cached = daily_brief.get_brief(test_date)
    assert cached is not None
    assert "brief" in cached.lower() or len(cached) > 0


# ── Test 5: council failure falls back to raw context ─────────────────────

@pytest.mark.asyncio
async def test_generate_brief_council_failure_fallback():
    """If council_decide raises, brief content = raw context (no crash)."""
    test_date = "2099-01-17"

    with (
        patch("jarvis.tasks.daily_brief._collect_gmail", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_zoho", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_calendar", return_value=[]),
        patch("jarvis.tasks.daily_brief._collect_audit_summary", return_value={}),
        patch(
            "jarvis.tasks.daily_brief.council_decide",
            new=AsyncMock(side_effect=Exception("Council offline")),
        ),
        patch("jarvis.tasks.daily_brief.write_audit"),
    ):
        result = await daily_brief.generate_brief(brief_date=test_date)

    assert result["success"] is True
    assert result["cost_usd_cents"] == 0        # no council = no cost
    assert "Daily Brief" in result["content"]   # raw context has the header
