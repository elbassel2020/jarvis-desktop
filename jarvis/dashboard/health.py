"""
Health Dashboard + Audit Reports.

get_health_status() — snapshot of integrations, task queue, memory stats.
get_audit_report(days) — multi-day audit summary by actor/outcome.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from jarvis.security.audit import daily_summary, query_audit
from jarvis.security.credential_broker import broker

_MEMORY_DB = Path(__file__).parent.parent.parent / "data" / "memory.db"
_TASK_DB   = Path(__file__).parent.parent.parent / "data" / "memory.db"

# ── Integration credential handles ────────────────────────────────────────
_CREDENTIAL_HANDLES = {
    "gmail":     "cred://gmail_refresh/walid",
    "zoho":      "cred://zoho_imap_password/lighting",
    "telegram":  "cred://telegram/msma-walid-bot",
    "anthropic": "cred://anthropic/default",
    "gemini":    "cred://gemini/default",
}


def _check_integrations() -> dict:
    result = {}
    for name, handle in _CREDENTIAL_HANDLES.items():
        try:
            val = broker.resolve(handle)
            result[name] = "configured" if val else "missing"
        except Exception:
            result[name] = "missing"
    return result


def _check_task_queue() -> dict:
    try:
        conn = sqlite3.connect(str(_TASK_DB))
        counts = {}
        for status in ("pending", "running", "completed", "failed"):
            try:
                n = conn.execute(
                    "SELECT COUNT(*) FROM task_queue WHERE status = ?", (status,)
                ).fetchone()[0]
                counts[status] = n
            except Exception:
                counts[status] = 0
        conn.close()
        return counts
    except Exception as exc:
        return {"error": str(exc)}


def _check_memory() -> dict:
    tables = ["semantic", "semantic_vec_link", "daily_briefs", "customer_deepdives"]
    stats = {}
    try:
        conn = sqlite3.connect(str(_MEMORY_DB))
        for tbl in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                stats[tbl] = n
            except Exception:
                stats[tbl] = 0
        conn.close()
    except Exception as exc:
        stats["error"] = str(exc)
    return stats


def get_health_status() -> dict:
    """
    Return a health snapshot dict.

    Keys: timestamp, integrations, task_queue, audit_today, memory.
    All sections degrade gracefully — never raises.
    """
    status = {
        "timestamp":    datetime.now().isoformat(),
        "integrations": {},
        "task_queue":   {},
        "audit_today":  {},
        "memory":       {},
    }

    status["integrations"] = _check_integrations()
    status["task_queue"]   = _check_task_queue()
    status["memory"]       = _check_memory()

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        status["audit_today"] = daily_summary(date_str=today)
    except Exception as exc:
        status["audit_today"] = {"error": str(exc)}

    return status


def get_audit_report(days: int = 7) -> dict:
    """
    Aggregate audit log entries from the last `days` days.

    Returns dict with:
        days, by_actor, by_outcome, errors_recent (up to 10)
    """
    report: dict = {
        "days":          days,
        "by_actor":      {},
        "by_outcome":    {},
        "errors_recent": [],
    }

    since_minutes = days * 24 * 60   # correct query_audit signature

    try:
        rows = query_audit(since_minutes=since_minutes, limit=500)
        for row in rows:
            actor   = row.get("actor", "unknown")
            outcome = row.get("outcome", "unknown")
            action  = row.get("action", "")
            notes   = row.get("notes", "")

            report["by_actor"][actor] = report["by_actor"].get(actor, 0) + 1
            report["by_outcome"][outcome] = report["by_outcome"].get(outcome, 0) + 1

            if outcome.startswith("error") and len(report["errors_recent"]) < 10:
                report["errors_recent"].append({
                    "actor":  actor,
                    "action": action,
                    "notes":  str(notes)[:100],
                })
    except Exception as exc:
        report["error"] = str(exc)

    return report
