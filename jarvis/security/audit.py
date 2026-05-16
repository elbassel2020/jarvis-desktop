"""
Jarvis-level audit log.

Every action call writes one row. Used for:
- Cost tracking (tokens x rate)
- Privacy invariant verification (no unexpected egress)
- Self-improvement budget tracking
- Daily morning brief generation
"""
import json
import logging
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger("jarvis.security.audit")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "memory.db"

# Patterns to redact from audit log payloads
REDACT_PATTERNS = [
    (re.compile(r'("api_?key"\s*:\s*")[^"]+'), r'\1[REDACTED]'),
    (re.compile(r'("token"\s*:\s*")[^"]+'), r'\1[REDACTED]'),
    (re.compile(r'("password"\s*:\s*")[^"]+'), r'\1[REDACTED]'),
    (re.compile(r'("secret"\s*:\s*")[^"]+'), r'\1[REDACTED]'),
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), '[REDACTED_KEY]'),
    (re.compile(r'AIza[0-9A-Za-z_-]{35}'), '[REDACTED_KEY]'),
    (re.compile(r'gsk_[A-Za-z0-9]{20,}'), '[REDACTED_KEY]'),
]


def _ensure_table():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jarvis_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL DEFAULT (datetime('now')),
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            params_redacted TEXT,
            outcome TEXT NOT NULL,
            egress_host TEXT,
            cost_usd_cents INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0,
            duration_ms INTEGER,
            notes TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON jarvis_audit(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON jarvis_audit(action, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor_ts ON jarvis_audit(actor, ts)")
    conn.commit()
    conn.close()


_ensure_table()


def _redact(s: str) -> str:
    if not s:
        return s
    for pat, repl in REDACT_PATTERNS:
        s = pat.sub(repl, s)
    return s


def write_audit(
    actor: str,
    action: str,
    params: Optional[dict] = None,
    outcome: str = "ok",
    egress_host: Optional[str] = None,
    cost_usd_cents: int = 0,
    tokens: int = 0,
    duration_ms: Optional[int] = None,
    notes: Optional[str] = None,
):
    """Append a row to the audit log."""
    params_json = ""
    if params:
        try:
            params_json = _redact(json.dumps(params, ensure_ascii=False, default=str))
        except Exception:
            params_json = str(params)[:500]

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """INSERT INTO jarvis_audit
           (actor, action, params_redacted, outcome, egress_host,
            cost_usd_cents, tokens, duration_ms, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (actor, action, params_json, outcome, egress_host,
         cost_usd_cents, tokens, duration_ms, _redact(notes or ""))
    )
    conn.commit()
    conn.close()


def query_audit(
    since_minutes: Optional[int] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Read audit log entries."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    where = []
    params: list[Any] = []
    if since_minutes:
        where.append("ts >= datetime('now', ?)")
        params.append(f"-{since_minutes} minutes")
    if actor:
        where.append("actor = ?")
        params.append(actor)
    if action:
        where.append("action = ?")
        params.append(action)

    sql = "SELECT * FROM jarvis_audit"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)

    rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    return rows


def daily_summary(date_str: Optional[str] = None) -> dict:
    """Aggregate stats for a date (YYYY-MM-DD). Defaults to today."""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT actor, action, outcome, COUNT(*) AS n,
                  SUM(cost_usd_cents) AS cents, SUM(tokens) AS tokens
           FROM jarvis_audit
           WHERE date(ts) = ?
           GROUP BY actor, action, outcome
           ORDER BY n DESC""",
        (date_str,)
    ).fetchall()
    total = conn.execute(
        """SELECT COUNT(*) AS n, SUM(cost_usd_cents) AS cents, SUM(tokens) AS tokens
           FROM jarvis_audit WHERE date(ts) = ?""",
        (date_str,)
    ).fetchone()
    conn.close()

    return {
        "date": date_str,
        "total_actions": total["n"] or 0,
        "total_cents": total["cents"] or 0,
        "total_tokens": total["tokens"] or 0,
        "by_action": [dict(r) for r in rows],
    }
