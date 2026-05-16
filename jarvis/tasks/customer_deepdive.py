"""
Nightly customer deep-dive — pre-compute narrative summaries.

Reads from MSMA DB (read-only) and writes summaries to Jarvis memory.db
for fast retrieval during conversations.
"""
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from jarvis.security.audit import write_audit
from jarvis.tasks.queue import task_handler

_logger = logging.getLogger("jarvis.tasks.customer_deepdive")

JARVIS_DB = Path("data/memory.db")

# MSMA DB path — Windows production location
_MSMA_CANDIDATES = [
    Path(r"C:\Users\walid\Documents\MSMA\msma.db"),
    Path("/Users/walid/Documents/MSMA/msma.db"),  # macOS fallback
]
MSMA_DB: Path = next((p for p in _MSMA_CANDIDATES if p.exists()), _MSMA_CANDIDATES[0])


def _ensure_table():
    conn = sqlite3.connect(str(JARVIS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_deepdives (
            company_name TEXT PRIMARY KEY,
            summary      TEXT NOT NULL,
            stats_json   TEXT,
            generated_at DATETIME NOT NULL DEFAULT (datetime('now')),
            duration_ms  INTEGER
        )
    """)
    conn.commit()
    conn.close()


_ensure_table()


def deepdive_one(company_name: str) -> dict:
    """Generate and cache a summary for one customer. Read-only from MSMA."""
    t0 = time.monotonic()

    if not MSMA_DB.exists():
        return {"error": "MSMA DB not found", "success": False}

    try:
        msma = sqlite3.connect(f"file:{MSMA_DB}?mode=ro", uri=True)
        msma.row_factory = sqlite3.Row

        # Customer record
        cust = msma.execute(
            "SELECT * FROM customers_unified WHERE company_name LIKE ? LIMIT 1",
            (f"%{company_name}%",),
        ).fetchone()

        if not cust:
            msma.close()
            return {"error": f"Customer '{company_name}' not found in MSMA DB", "success": False}

        cust_dict = dict(cust)

        # Recent quotes (newest first)
        quotes = msma.execute(
            """
            SELECT id, total_min_sar, total_max_sar, created_at, sent, quality_status
            FROM intelligent_quotes
            WHERE LOWER(company) LIKE ?
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (f"%{company_name.lower()}%",),
        ).fetchall()

        msma.close()

        # Build summary
        name = cust_dict.get("company_name", company_name)
        contact = cust_dict.get("primary_contact_name", "Unknown")
        email = cust_dict.get("primary_contact_email", "N/A")
        status = cust_dict.get("status", "unknown")
        last_email = cust_dict.get("last_email_date", "never")
        response_rate = cust_dict.get("response_rate")
        total_rx = cust_dict.get("total_emails_received", 0)

        lines = [
            f"العميل: {name}",
            f"Contact: {contact} <{email}>",
            f"Status: {status} | Last email: {last_email}",
        ]
        if response_rate is not None:
            lines.append(f"Response rate: {response_rate:.0%}")
        if total_rx:
            lines.append(f"Emails received: {total_rx}")

        if quotes:
            sent_count = sum(1 for q in quotes if q["sent"])
            total_value_min = sum((q["total_min_sar"] or 0) for q in quotes)
            lines.append(f"\nQuotes: {len(quotes)} total, {sent_count} sent")
            lines.append(f"Total value range (last {len(quotes)}): {total_value_min:,.0f} SAR+")
            lines.append("Recent quotes:")
            for q in quotes[:5]:
                qid = q["id"]
                val = f"{q['total_min_sar']:,.0f}–{q['total_max_sar']:,.0f}" if q["total_min_sar"] else "N/A"
                qs = q["quality_status"] or "—"
                lines.append(f"  #{qid}: {val} SAR ({q['created_at']}) [{qs}]")
        else:
            lines.append("\nNo quotes found.")

        summary = "\n".join(lines)
        duration_ms = int((time.monotonic() - t0) * 1000)

        # Cache in Jarvis DB
        jarvis = sqlite3.connect(str(JARVIS_DB))
        stats = {
            "quote_count": len(quotes),
            "sent_count": sum(1 for q in quotes if q["sent"]) if quotes else 0,
        }
        jarvis.execute(
            """
            INSERT OR REPLACE INTO customer_deepdives
              (company_name, summary, stats_json, duration_ms)
            VALUES (?, ?, ?, ?)
            """,
            (name, summary, json.dumps(stats), duration_ms),
        )
        jarvis.commit()
        jarvis.close()

        write_audit(
            actor="customer_deepdive", action="generate",
            params={"company": company_name}, outcome="ok",
            duration_ms=duration_ms,
        )
        return {"success": True, "company": name, "summary_length": len(summary), "quotes": len(quotes)}

    except Exception as e:
        _logger.error(f"deepdive_one({company_name}): {e}")
        write_audit(
            actor="customer_deepdive", action="generate",
            params={"company": company_name}, outcome="error",
            notes=str(e)[:200],
        )
        return {"error": str(e), "success": False}


def get_deepdive(company_name: str) -> Optional[str]:
    """Return cached summary for a customer, or None if not yet generated."""
    conn = sqlite3.connect(str(JARVIS_DB))
    row = conn.execute(
        "SELECT summary FROM customer_deepdives WHERE company_name LIKE ?",
        (f"%{company_name}%",),
    ).fetchone()
    conn.close()
    return row[0] if row else None


@task_handler("customer_deepdive")
async def handle_deepdive_task(payload: dict, task: dict) -> dict:
    """Task queue handler for async deepdive generation."""
    company_name = payload.get("company_name", "")
    if not company_name:
        return {"error": "company_name required in payload"}
    return deepdive_one(company_name)


def schedule_all_active() -> int:
    """Enqueue deepdive tasks for all customers with recent activity."""
    from jarvis.tasks.queue import enqueue

    if not MSMA_DB.exists():
        _logger.warning("MSMA DB not found — skipping schedule_all_active")
        return 0

    try:
        msma = sqlite3.connect(f"file:{MSMA_DB}?mode=ro", uri=True)
        rows = msma.execute(
            "SELECT company_name FROM customers_unified WHERE total_emails_received > 0 LIMIT 25"
        ).fetchall()
        msma.close()
    except Exception as e:
        _logger.error(f"schedule_all_active: {e}")
        return 0

    date_key = datetime.now().strftime("%Y%m%d")
    count = 0
    for (name,) in rows:
        enqueue(
            kind="customer_deepdive",
            payload={"company_name": name},
            priority=8,
            idempotency_key=f"deepdive_{name}_{date_key}",
        )
        count += 1

    _logger.info(f"Enqueued {count} customer deepdive tasks for {date_key}")
    return count
