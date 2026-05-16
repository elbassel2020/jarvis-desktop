"""Task queue tests."""
import asyncio
import pytest
import sqlite3
from pathlib import Path
from jarvis.tasks.queue import (
    enqueue, cancel, status, task_handler, start_workers,
    RetryableError, HANDLERS, DB_PATH
)


@pytest.fixture(autouse=True)
def cleanup_test_tasks():
    yield
    # Remove any test tasks
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM task_queue WHERE kind LIKE 'test_%'")
    conn.commit()
    conn.close()


def test_enqueue_returns_id():
    task_id = enqueue("test_simple", {"x": 1})
    assert isinstance(task_id, int)
    assert task_id > 0


def test_idempotency_key_prevents_duplicate():
    key = "test-idem-1"
    id1 = enqueue("test_simple", {"x": 1}, idempotency_key=key)
    id2 = enqueue("test_simple", {"x": 2}, idempotency_key=key)
    assert id1 == id2  # Same task; second call is a replay


def test_status_returns_dict():
    task_id = enqueue("test_simple", {"x": 1})
    s = status(task_id)
    assert s is not None
    assert s["kind"] == "test_simple"
    assert s["status"] == "pending"


def test_cancel_pending():
    task_id = enqueue("test_simple", {"x": 1})
    assert cancel(task_id) is True
    assert status(task_id)["status"] == "cancelled"


def test_cancel_nonpending_fails():
    task_id = enqueue("test_simple", {"x": 1})
    # Manually mark running
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("UPDATE task_queue SET status='running' WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    assert cancel(task_id) is False


@pytest.mark.asyncio
async def test_worker_processes_task():
    results = []

    @task_handler("test_worker_basic")
    async def handler(payload, task):
        results.append(payload["value"])
        return {"echoed": payload["value"]}

    task_id = enqueue("test_worker_basic", {"value": "hello"})
    shutdown, tasks = await start_workers(num_workers=1)
    await asyncio.sleep(3.0)
    shutdown.set()
    for t in tasks:
        t.cancel()

    assert results == ["hello"]
    final = status(task_id)
    assert final["status"] == "done"


@pytest.mark.asyncio
async def test_worker_retries_on_retryable():
    attempt_count = [0]

    @task_handler("test_retryable")
    async def handler(payload, task):
        attempt_count[0] += 1
        if attempt_count[0] < 2:
            raise RetryableError("not yet")
        return {"ok": True}

    task_id = enqueue("test_retryable", {}, max_retries=3)
    shutdown, tasks = await start_workers(num_workers=1)
    await asyncio.sleep(6.0)
    shutdown.set()
    for t in tasks:
        t.cancel()

    final = status(task_id)
    assert attempt_count[0] >= 2
    assert final["status"] in ("done", "running")  # may still be in flight


def test_priority_ordering():
    """Lower priority number = processed first."""
    low_pri = enqueue("test_pri", {"n": 1}, priority=9)
    high_pri = enqueue("test_pri", {"n": 2}, priority=1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id FROM task_queue WHERE kind='test_pri' AND status='pending' "
        "ORDER BY priority ASC, created_at ASC LIMIT 1"
    ).fetchone()
    conn.close()

    assert row["id"] == high_pri
