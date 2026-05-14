"""Read-only MSMA DB access — latest quotes, customer summary, attention items."""
import sqlite3
from pathlib import Path
from loguru import logger
from datetime import datetime, timedelta

MSMA_DB = Path(r'C:\Users\walid\Documents\MSMA\msma.db')


class MSMAReader:
    def __init__(self):
        if not MSMA_DB.exists():
            logger.warning(f"MSMA DB not found at {MSMA_DB}")
            self._conn = None
            return
        try:
            self._conn = sqlite3.connect(
                f"file:{MSMA_DB}?mode=ro", uri=True, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            logger.info("MSMA DB: connected read-only")
        except Exception as e:
            logger.warning(f"MSMA DB open failed: {e}")
            self._conn = None

    def _available(self) -> bool:
        return self._conn is not None

    def latest_quote_for(self, customer: str = None, limit: int = 5) -> list:
        """Get recent quotes, optionally filtered by customer name."""
        if not self._available():
            return []
        try:
            cur = self._conn.cursor()
            if customer:
                cur.execute(
                    "SELECT * FROM quotes WHERE customer LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f'%{customer}%', limit)
                )
            else:
                cur.execute("SELECT * FROM quotes ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"MSMA latest_quote_for: {e}")
            return []

    def customer_summary(self) -> list:
        """Count of RFQs per customer, sorted by volume."""
        if not self._available():
            return []
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT customer, COUNT(*) as count FROM quotes "
                "GROUP BY customer ORDER BY count DESC LIMIT 10"
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"MSMA customer_summary: {e}")
            return []

    def attention_items(self) -> list:
        """Quotes not yet sent, created in the last 7 days — need action."""
        if not self._available():
            return []
        try:
            since = (datetime.now() - timedelta(days=7)).isoformat()
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM quotes WHERE status != 'sent' AND created_at >= ? "
                "ORDER BY created_at DESC LIMIT 10",
                (since,)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"MSMA attention_items: {e}")
            return []

    def recent_quotes(self, days: int = 7, limit: int = 10) -> list:
        """Quotes from the last N days."""
        if not self._available():
            return []
        try:
            since = (datetime.now() - timedelta(days=days)).isoformat()
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM quotes WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (since, limit)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"MSMA recent_quotes: {e}")
            return []

    def verified_prices_count(self) -> int:
        """Count of quotes with status='sent' (confirmed and dispatched)."""
        if not self._available():
            return 0
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM quotes WHERE status = 'sent'")
            return cur.fetchone()[0]
        except Exception as e:
            logger.warning(f"MSMA verified_prices_count: {e}")
            return 0

    def summary_text(self) -> str:
        """One-shot Arabic text summary for Jarvis to speak."""
        if not self._available():
            return "MSMA DB مش متاحة دلوقتي"
        recent = self.recent_quotes(days=7)
        verified = self.verified_prices_count()
        attention = self.attention_items()
        customers = self.customer_summary()

        lines = [f"MSMA: {len(recent)} quote الـ7 أيام، {verified} اتبعتوا"]
        if attention:
            lines.append(f"{len(attention)} بيستنى ردك")
        if customers:
            top = customers[0]
            lines.append(
                f"أكبر عميل: {top.get('customer', '?')} ({top.get('count', 0)} RFQ)"
            )
        return ". ".join(lines)
