"""
Backfill embeddings for existing semantic facts.

Idempotent — safe to re-run. Skips already-embedded facts.
Processes in batches to avoid memory pressure.
"""
import logging
import sqlite3
from pathlib import Path

from jarvis.memory.vector import VectorMemory, _ensure_tables, _open_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("backfill")

DB_PATH = Path("data/memory.db")


def main():
    conn = _open_conn()
    _ensure_tables(conn)

    unembedded = conn.execute("""
        SELECT s.rowid, s.key, s.value
        FROM semantic s
        LEFT JOIN semantic_vec_link l ON l.semantic_rowid = s.rowid
        WHERE l.vec_rowid IS NULL
          AND s.value IS NOT NULL
          AND s.value != ''
        ORDER BY s.rowid
    """).fetchall()
    conn.close()

    total = len(unembedded)
    logger.info(f"Found {total} unembedded semantic facts")
    if total == 0:
        logger.info("Nothing to do.")
        return

    mem = VectorMemory()
    processed = 0
    failed = 0
    for rowid, key, value in unembedded:
        text = f"{key}: {value}" if key else value
        try:
            mem.add(rowid, text[:1000])  # cap to avoid huge inputs
            processed += 1
            if processed % 25 == 0:
                logger.info(f"  {processed}/{total} embedded")
        except Exception as e:
            logger.warning(f"  Failed rowid={rowid}: {e}")
            failed += 1

    mem.close()
    logger.info(f"Backfill complete: {processed} embedded, {failed} failed")


if __name__ == "__main__":
    main()
