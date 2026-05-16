"""Customer deepdive tests — MSMA DB access mocked where destructive."""
import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from jarvis.tasks import customer_deepdive


def test_table_created():
    """customer_deepdives table must exist in Jarvis DB."""
    conn = sqlite3.connect(str(customer_deepdive.JARVIS_DB))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "customer_deepdives" in tables


def test_get_deepdive_returns_none_when_missing():
    result = customer_deepdive.get_deepdive("nonexistent_company_xyz_12345")
    assert result is None


def test_deepdive_handles_missing_msma_db(tmp_path, monkeypatch):
    """Must fail gracefully if MSMA DB is absent."""
    monkeypatch.setattr(customer_deepdive, "MSMA_DB", tmp_path / "missing.db")
    result = customer_deepdive.deepdive_one("Zamilfood")
    assert result["success"] is False
    assert "MSMA DB not found" in result["error"]


def test_schedule_all_handles_missing_db(tmp_path, monkeypatch):
    """schedule_all_active must not raise when MSMA DB absent."""
    monkeypatch.setattr(customer_deepdive, "MSMA_DB", tmp_path / "missing.db")
    count = customer_deepdive.schedule_all_active()
    assert count == 0


@pytest.mark.skipif(
    not Path(r"C:\Users\walid\Documents\MSMA\msma.db").exists(),
    reason="MSMA DB not available on this machine",
)
def test_deepdive_one_real_customer():
    """Integration test — generates real deepdive for Zamilfood."""
    result = customer_deepdive.deepdive_one("Zamilfood")
    assert result["success"] is True
    assert result["summary_length"] > 50

    # Verify cached
    cached = customer_deepdive.get_deepdive("Zamilfood")
    assert cached is not None
    assert "Zamilfood" in cached or "zamil" in cached.lower()


@pytest.mark.skipif(
    not Path(r"C:\Users\walid\Documents\MSMA\msma.db").exists(),
    reason="MSMA DB not available on this machine",
)
def test_schedule_all_active_enqueues():
    """Integration test — enqueues at least 1 task."""
    count = customer_deepdive.schedule_all_active()
    assert count >= 1
