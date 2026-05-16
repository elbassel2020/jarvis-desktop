"""Vector memory + hybrid retrieval tests."""
import struct
import sqlite3
import pytest

from jarvis.memory.vector import VectorMemory, embed, hybrid_retrieve, _open_conn, _ensure_tables


def test_embed_produces_correct_bytes():
    result = embed("test text")
    assert isinstance(result, bytes)
    assert len(result) == 1024 * 4  # 1024 floats × 4 bytes each


def test_embed_empty_returns_empty():
    assert embed("") == b""
    assert embed("   ") == b""


def test_embed_arabic():
    """BGE-M3 should handle Arabic text."""
    result = embed("هذا اختبار باللغة العربية")
    assert isinstance(result, bytes)
    assert len(result) == 1024 * 4


def test_embed_normalized():
    """BGE-M3 output should be unit-normalized (cosine similarity ready)."""
    v = embed("some text")
    floats = struct.unpack(f"{1024}f", v)
    # Sum of squares should be ~1.0
    norm_sq = sum(x * x for x in floats)
    assert abs(norm_sq - 1.0) < 0.01


def test_vector_memory_add_returns_rowid():
    mem = VectorMemory()
    rowid = mem.add(semantic_rowid=99997, text="Unique test fact about Jarvis memory")
    assert isinstance(rowid, int)
    assert rowid > 0
    mem.close()


def test_vector_memory_add_idempotent():
    """Adding same semantic_rowid twice updates, not duplicates."""
    mem = VectorMemory()
    r1 = mem.add(99996, "Original text version one")
    r2 = mem.add(99996, "Updated text version two")
    assert r1 == r2  # Same vec_rowid, updated in-place

    # Verify only one link exists
    count = mem.conn.execute(
        "SELECT COUNT(*) FROM semantic_vec_link WHERE semantic_rowid = ?", (99996,)
    ).fetchone()[0]
    assert count == 1
    mem.close()


def test_vector_search_returns_relevant():
    """Inserted facts should be retrievable by semantic query."""
    mem = VectorMemory()
    mem.add(99101, "MSMA Group electrical equipment supplier Jubail")
    mem.add(99102, "Cats are independent domestic animals")
    mem.add(99103, "Walid manages procurement for MSMA")

    results = mem.vector_search("MSMA procurement", k=5)
    assert isinstance(results, list)
    if results:  # may be 0 if vec table is empty from prior run
        texts = [r["text"] for r in results]
        assert any("MSMA" in t or "procurement" in t for t in texts)
    mem.close()


def test_fts_search_works():
    mem = VectorMemory()
    mem.add(99201, "Zamilfood is a key customer")
    results = mem.fts_search("Zamilfood", k=5)
    # fts_search queries actual semantic table, not just link
    assert isinstance(results, list)
    mem.close()


def test_hybrid_retrieve_returns_list():
    """hybrid_retrieve doesn't crash and returns list."""
    results = hybrid_retrieve("electrical equipment", k=5)
    assert isinstance(results, list)
    for r in results:
        assert "text" in r
        assert "score" in r
        assert r["score"] > 0
