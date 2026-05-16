"""
Daily Morning Brief — aggregated intelligence for Walid.

Pulls from Gmail, Zoho, Google Calendar, and the audit log, then uses
Council Mode to synthesise a concise morning brief in Walid's language
(defaults to English; switch to Arabic by setting BRIEF_LANG=ar).

Each source is wrapped in its own try/except so a missing credential
or unconfigured integration never blocks the brief from generating.

Usage (queue)::
    # Enqueued by scheduler at 07:00 Asia/Riyadh daily
    from jarvis.tasks.queue import enqueue
    enqueue("daily_brief", {})

Usage (direct)::
    result = await generate_brief()
"""
import asyncio
import json
import logging
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from jarvis.security.audit import write_audit, daily_summary
from jarvis.tasks.queue import task_handler
from jarvis.intelligence.council import council_decide

_logger = logging.getLogger("jarvis.tasks.daily_brief")

JARVIS_DB = Path(__file__).parent.parent.parent / "data" / "memory.db"

# ── Table setup ────────────────────────────────────────────────────────────

def _ensure_table():
    conn = sqlite3.connect(str(JARVIS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_briefs (
            brief_date   TEXT PRIMARY KEY,
            content      TEXT NOT NULL,
            metadata_json TEXT,
            generated_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


_ensure_table()


# ── Cache helpers ──────────────────────────────────────────────────────────

def get_brief(brief_date: Optional[str] = None) -> Optional[str]:
    """
    Return cached brief content for a date (YYYY-MM-DD), or None if missing.

    Defaults to today.
    """
    brief_date = brief_date or date.today().isoformat()
    conn = sqlite3.connect(str(JARVIS_DB))
    row = conn.execute(
        "SELECT content FROM daily_briefs WHERE brief_date = ?",
        (brief_date,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _save_brief(brief_date: str, content: str, metadata: dict):
    conn = sqlite3.connect(str(JARVIS_DB))
    conn.execute(
        """INSERT OR REPLACE INTO daily_briefs
           (brief_date, content, metadata_json, generated_at)
           VALUES (?, ?, ?, datetime('now'))""",
        (brief_date, content, json.dumps(metadata, ensure_ascii=False, default=str)),
    )
    conn.commit()
    conn.close()


# ── Per-source collectors (all gracefully degrade) ─────────────────────────

def _collect_gmail(limit: int = 5) -> list[dict]:
    try:
        from jarvis.integrations.gmail.actions import email_list_unread
        return email_list_unread(limit=limit)
    except Exception as exc:
        _logger.info(f"Gmail unavailable: {exc}")
        return []


def _collect_zoho(limit: int = 5) -> list[dict]:
    try:
        from jarvis.integrations.zoho_mail.imap_client import list_unread
        return list_unread(limit=limit)
    except Exception as exc:
        _logger.info(f"Zoho unavailable: {exc}")
        return []


def _collect_calendar() -> list[dict]:
    try:
        from jarvis.integrations.gcal.actions import list_today
        return list_today()
    except Exception as exc:
        _logger.info(f"Calendar unavailable: {exc}")
        return []


def _collect_audit_summary(brief_date: str) -> dict:
    try:
        return daily_summary(brief_date)
    except Exception as exc:
        _logger.info(f"Audit summary unavailable: {exc}")
        return {}


# ── Brief formatter ────────────────────────────────────────────────────────

def _build_context(
    brief_date: str,
    gmail_msgs: list[dict],
    zoho_msgs: list[dict],
    calendar_events: list[dict],
    audit: dict,
) -> str:
    """Format raw data into a structured context block for council_decide."""
    lines = [f"Daily Brief — {brief_date}", "=" * 40]

    # Emails
    total_unread = len(gmail_msgs) + len(zoho_msgs)
    lines.append(f"\nUNREAD EMAILS ({total_unread} total):")
    for msg in gmail_msgs[:5]:
        sender = msg.get("from", "?")
        subject = msg.get("subject", "(no subject)")
        lines.append(f"  [Gmail] {sender}: {subject}")
    for msg in zoho_msgs[:5]:
        sender = msg.get("from", msg.get("from_", "?"))
        subject = msg.get("subject", "(no subject)")
        lines.append(f"  [Zoho]  {sender}: {subject}")
    if total_unread == 0:
        lines.append("  (inbox clear)")

    # Calendar
    lines.append(f"\nCALENDAR — TODAY ({len(calendar_events)} events):")
    for ev in calendar_events:
        start = ev.get("start", "?")
        summary = ev.get("summary", "(no title)")
        lines.append(f"  {start} — {summary}")
    if not calendar_events:
        lines.append("  (no events)")

    # Audit
    if audit:
        lines.append(
            f"\nYESTERDAY'S ACTIVITY: "
            f"{audit.get('total_actions', 0)} actions, "
            f"{audit.get('total_tokens', 0)} tokens, "
            f"{audit.get('total_cents', 0)} USD-cents cost"
        )

    return "\n".join(lines)


# ── Main generator ─────────────────────────────────────────────────────────

async def generate_brief(brief_date: Optional[str] = None) -> dict:
    """
    Generate and cache the morning brief for `brief_date` (YYYY-MM-DD).

    Defaults to today. Overwrites any existing cached brief for that date.

    Returns
    -------
    dict with keys: brief_date, content, success, duration_ms, cost_usd_cents
    """
    t0 = time.monotonic()
    brief_date = brief_date or date.today().isoformat()

    # Collect sources (all sync, wrapped)
    gmail_msgs     = _collect_gmail()
    zoho_msgs      = _collect_zoho()
    calendar_events = _collect_calendar()
    audit          = _collect_audit_summary(brief_date)

    context = _build_context(brief_date, gmail_msgs, zoho_msgs, calendar_events, audit)

    metadata = {
        "gmail_count":    len(gmail_msgs),
        "zoho_count":     len(zoho_msgs),
        "calendar_count": len(calendar_events),
        "audit_actions":  audit.get("total_actions", 0),
    }

    # Council synthesis
    try:
        council_result = await council_decide(
            question=(
                "Summarise the following morning data for Walid Al-Bassel (MSMA Group, Jubail). "
                "Highlight urgent emails, today's schedule, and any action items. "
                "Be concise — 150 words max."
            ),
            context=context,
            include_gemini=True,
        )
        content = council_result.decision
        cost_cents = council_result.cost_usd_cents
        metadata["council_confidence"] = council_result.confidence
    except Exception as exc:
        _logger.warning(f"Council unavailable, using raw context: {exc}")
        content = context          # graceful fallback: raw data as brief
        cost_cents = 0

    _save_brief(brief_date, content, metadata)

    duration_ms = int((time.monotonic() - t0) * 1000)
    write_audit(
        actor="daily_brief",
        action="generate_brief",
        params={"brief_date": brief_date, **metadata},
        outcome="ok",
        cost_usd_cents=cost_cents,
        duration_ms=duration_ms,
    )

    _logger.info(f"Brief generated for {brief_date} ({len(content)} chars, {cost_cents}¢)")
    return {
        "brief_date":     brief_date,
        "content":        content,
        "success":        True,
        "duration_ms":    duration_ms,
        "cost_usd_cents": cost_cents,
    }


# ── Queue handler ──────────────────────────────────────────────────────────

@task_handler("daily_brief")
async def _handle_daily_brief(payload: dict) -> dict:
    """Queue worker entry point. payload may contain optional 'brief_date'."""
    brief_date = payload.get("brief_date")
    return await generate_brief(brief_date=brief_date)
