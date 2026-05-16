"""
SQLite-backed task queue.

Three async workers consume tasks in priority order. Each task:
- Has an idempotency key (prevents duplicate enqueue)
- Has a budget cap (tokens + USD cents)
- Tracks parent_task_id for multi-step plans
- Auto-retries up to max_retries on RetryableError
- Audits every transition

Handlers register via @task_handler decorator.
"""
import asyncio
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from jarvis.security.audit import write_audit

_logger = logging.getLogger("jarvis.tasks.queue")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "memory.db"

# Handler registry
HANDLERS: dict[str, Callable] = {}


class RetryableError(Exception):
    """Mark errors that should trigger a retry (vs permanent failure)."""
    pass


def task_handler(kind: str):
    """Decorator to register an async function as a handler for a task kind."""
    def decorator(fn: Callable):
        HANDLERS[kind] = fn
        return fn
    return decorator


def _ensure_table():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 5,
            status TEXT NOT NULL DEFAULT 'pending',
            parent_task_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT (datetime('now')),
            started_at DATETIME,
            completed_at DATETIME,
            retries INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            result_json TEXT,
            error TEXT,
            budget_tokens INTEGER DEFAULT 50000,
            budget_usd_cents INTEGER DEFAULT 50,
            spent_tokens INTEGER DEFAULT 0,
            spent_usd_cents INTEGER DEFAULT 0,
            idempotency_key TEXT UNIQUE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_pending "
        "ON task_queue(status, priority, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_parent "
        "ON task_queue(parent_task_id)"
    )
    conn.commit()
    conn.close()


_ensure_table()


def enqueue(
    kind: str,
    payload: dict,
    priority: int = 5,
    idempotency_key: Optional[str] = None,
    parent_task_id: Optional[int] = None,
    max_retries: int = 3,
    budget_tokens: int = 50000,
    budget_usd_cents: int = 50,
) -> int:
    """Enqueue a task. Returns task_id. Idempotency-safe."""
    idempotency_key = idempotency_key or str(uuid.uuid4())

    conn = sqlite3.connect(str(DB_PATH))
    # Check idempotency first
    existing = conn.execute(
        "SELECT id FROM task_queue WHERE idempotency_key = ?",
        (idempotency_key,)
    ).fetchone()
    if existing:
        conn.close()
        _logger.info(f"Idempotent replay: kind={kind} task_id={existing[0]}")
        return existing[0]

    cur = conn.execute(
        """INSERT INTO task_queue
           (kind, payload_json, priority, parent_task_id, max_retries,
            budget_tokens, budget_usd_cents, idempotency_key)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (kind, json.dumps(payload, ensure_ascii=False, default=str),
         priority, parent_task_id, max_retries,
         budget_tokens, budget_usd_cents, idempotency_key)
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    _logger.info(f"Enqueued: kind={kind} task_id={task_id} priority={priority}")
    write_audit(actor="task_queue", action="enqueue",
                params={"kind": kind, "task_id": task_id, "priority": priority})
    return task_id


def cancel(task_id: int) -> bool:
    """Mark a pending task as cancelled."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "UPDATE task_queue SET status='cancelled', completed_at=datetime('now') "
        "WHERE id = ? AND status = 'pending'",
        (task_id,)
    )
    conn.commit()
    rowcount = cur.rowcount
    conn.close()
    return rowcount > 0


def status(task_id: int) -> Optional[dict]:
    """Get task status."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM task_queue WHERE id = ?", (task_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


async def _claim_task() -> Optional[dict]:
    """Atomically claim the next pending task."""
    def _do_claim():
        conn = sqlite3.connect(str(DB_PATH), isolation_level="IMMEDIATE")
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """SELECT * FROM task_queue
                   WHERE status='pending' AND retries < max_retries
                   ORDER BY priority ASC, created_at ASC
                   LIMIT 1"""
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """UPDATE task_queue
                   SET status='running', started_at=datetime('now')
                   WHERE id = ?""",
                (row["id"],)
            )
            conn.commit()
            return dict(row)
        finally:
            conn.close()

    return await asyncio.to_thread(_do_claim)


async def _mark_done(task_id: int, result: Any):
    def _do():
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """UPDATE task_queue
               SET status='done', completed_at=datetime('now'),
                   result_json = ?
               WHERE id = ?""",
            (json.dumps(result, ensure_ascii=False, default=str), task_id)
        )
        conn.commit()
        conn.close()
    await asyncio.to_thread(_do)
    write_audit(actor="task_queue", action="task_done",
                params={"task_id": task_id})


async def _mark_retry(task_id: int, err: Exception):
    def _do():
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """UPDATE task_queue
               SET status='pending', retries = retries + 1, error = ?
               WHERE id = ?""",
            (str(err)[:500], task_id)
        )
        conn.commit()
        conn.close()
    await asyncio.to_thread(_do)
    write_audit(actor="task_queue", action="task_retry",
                params={"task_id": task_id, "error": str(err)[:200]},
                outcome="retryable_error")


async def _mark_failed(task_id: int, err: Exception):
    def _do():
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """UPDATE task_queue
               SET status='failed', completed_at=datetime('now'), error = ?
               WHERE id = ?""",
            (str(err)[:500], task_id)
        )
        conn.commit()
        conn.close()
    await asyncio.to_thread(_do)
    write_audit(actor="task_queue", action="task_failed",
                params={"task_id": task_id, "error": str(err)[:200]},
                outcome="permanent_error")


async def worker_loop(worker_id: int, shutdown: asyncio.Event):
    """One worker coroutine."""
    _logger.info(f"Worker {worker_id} starting")
    while not shutdown.is_set():
        task = await _claim_task()
        if not task:
            await asyncio.sleep(2.0)
            continue

        kind = task["kind"]
        handler = HANDLERS.get(kind)
        if not handler:
            await _mark_failed(task["id"], Exception(f"No handler for kind={kind}"))
            continue

        try:
            payload = json.loads(task["payload_json"])
            result = await handler(payload, task)
            await _mark_done(task["id"], result)
        except RetryableError as e:
            await _mark_retry(task["id"], e)
        except Exception as e:
            await _mark_failed(task["id"], e)


async def start_workers(num_workers: int = 3) -> tuple[asyncio.Event, list[asyncio.Task]]:
    """Start N workers, return shutdown event + task handles."""
    shutdown = asyncio.Event()
    tasks = [
        asyncio.create_task(worker_loop(i, shutdown))
        for i in range(num_workers)
    ]
    _logger.info(f"Started {num_workers} task workers")
    return shutdown, tasks
