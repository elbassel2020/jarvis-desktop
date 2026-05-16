"""Audit log tests."""
import pytest
import sqlite3
from datetime import datetime
from pathlib import Path
from jarvis.security.audit import (
    write_audit, query_audit, daily_summary, _redact, DB_PATH
)


def test_write_and_query():
    write_audit(
        actor="test_actor",
        action="test_action",
        params={"key": "value"},
        outcome="ok",
        cost_usd_cents=5,
        tokens=100,
    )
    rows = query_audit(actor="test_actor", limit=1)
    assert len(rows) == 1
    assert rows[0]["action"] == "test_action"
    assert rows[0]["cost_usd_cents"] == 5


def test_redaction_in_params():
    write_audit(
        actor="test_actor",
        action="test_action_with_secret",
        params={"api_key": "sk-secret123456789012345", "normal": "value"},
    )
    rows = query_audit(action="test_action_with_secret", limit=1)
    assert "sk-secret" not in rows[0]["params_redacted"]
    assert "[REDACTED" in rows[0]["params_redacted"]


def test_redact_function():
    assert "[REDACTED_KEY]" in _redact("api_key=sk-abcdef1234567890123456")
    assert "[REDACTED]" in _redact('{"password": "mypass"}')
    assert _redact("normal text") == "normal text"


def test_daily_summary_aggregates():
    write_audit(actor="test", action="alpha", tokens=10, cost_usd_cents=1)
    write_audit(actor="test", action="alpha", tokens=20, cost_usd_cents=2)
    write_audit(actor="test", action="beta", tokens=5)

    summary = daily_summary()
    assert summary["total_actions"] >= 3


def test_audit_table_exists():
    conn = sqlite3.connect(str(DB_PATH))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "jarvis_audit" in tables
