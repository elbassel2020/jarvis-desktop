"""
sqlite-vec + BGE-M3 hybrid retrieval.

Embeds Arabic and English text using multilingual BGE-M3.
Stores embeddings in existing SQLite via sqlite-vec extension.
Hybrid retrieval: vector top-K + LIKE/FTS top-K → RRF fusion.
"""
import logging
import struct
import sqlite3
from pathlib import Path
from typing import Optional

import sqlite_vec

_logger = logging.getLogger("jarvis.memory.vector")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "memory.db"
EMBED_DIM = 1024  # BGE-M3 output dimension

# Lazy-loaded singleton
_embed_model = None


def _model():
    """Lazy-load BGE-M3 (first call ~30s, cached after)."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _logger.info("Loading BGE-M3 embedding model...")
        _embed_model = SentenceTransformer("BAAI/bge-m3", device="cpu")
        _logger.info("BGE-M3 loaded")
    return _embed_model


def embed(text: str) -> bytes:
    """Embed text → BGE-M3 float[1024] packed as bytes for sqlite-vec."""
    if not text or not text.strip():
        return b""
    vec = _model().encode(text, normalize_embeddings=True, show_progress_bar=False)
    return struct.pack(f"{EMBED_DIM}f", *vec)


def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _ensure_tables(conn: sqlite3.Connection):
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS semantic_vec
        USING vec0(embedding float[1024])
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS semantic_vec_link (
            vec_rowid  INTEGER PRIMARY KEY,
            semantic_rowid INTEGER NOT NULL UNIQUE,
            text       TEXT NOT NULL,
            updated_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


class VectorMemory:
    def __init__(self):
        self.conn = _open_conn()
        _ensure_tables(self.conn)

    def add(self, semantic_rowid: int, text: str) -> int:
        """Add or update embedding for a semantic fact. Returns vec_rowid."""
        if not text:
            return -1
        emb = embed(text)

        existing = self.conn.execute(
            "SELECT vec_rowid FROM semantic_vec_link WHERE semantic_rowid = ?",
            (semantic_rowid,),
        ).fetchone()

        if existing:
            vec_rowid = existing[0]
            self.conn.execute(
                "UPDATE semantic_vec SET embedding = ? WHERE rowid = ?",
                (emb, vec_rowid),
            )
            self.conn.execute(
                "UPDATE semantic_vec_link SET text = ?, updated_at = datetime('now')"
                " WHERE vec_rowid = ?",
                (text, vec_rowid),
            )
            self.conn.commit()
            return vec_rowid
        else:
            cur = self.conn.execute(
                "INSERT INTO semantic_vec(embedding) VALUES (?)", (emb,)
            )
            vec_rowid = cur.lastrowid
            self.conn.execute(
                "INSERT INTO semantic_vec_link(vec_rowid, semantic_rowid, text)"
                " VALUES (?, ?, ?)",
                (vec_rowid, semantic_rowid, text),
            )
            self.conn.commit()
            return vec_rowid

    def vector_search(self, query: str, k: int = 10) -> list[dict]:
        """Top-K nearest neighbors by cosine similarity."""
        query_emb = embed(query)
        if not query_emb:
            return []
        rows = self.conn.execute(
            """
            SELECT v.rowid, v.distance, l.semantic_rowid, l.text
            FROM semantic_vec v
            JOIN semantic_vec_link l ON l.vec_rowid = v.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (query_emb, k),
        ).fetchall()
        return [
            {"semantic_rowid": r[2], "text": r[3], "distance": r[1]}
            for r in rows
        ]

    def fts_search(self, query: str, k: int = 10) -> list[dict]:
        """LIKE-based keyword search on semantic table (FTS5 fallback)."""
        try:
            rows = self.conn.execute(
                """
                SELECT rowid, value FROM semantic
                WHERE value LIKE ? OR key LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", k),
            ).fetchall()
            return [{"semantic_rowid": r[0], "text": r[1], "score": 1.0} for r in rows]
        except Exception as e:
            _logger.warning(f"FTS search failed: {e}")
            return []

    def close(self):
        self.conn.close()


def hybrid_retrieve(query: str, k: int = 10) -> list[dict]:
    """Vector top-2K + FTS top-2K → RRF fusion → top-K.

    Reciprocal Rank Fusion: score = Σ(1 / (rank + 60)) across sources.
    Falls back gracefully if no embeddings exist yet.
    """
    mem = VectorMemory()
    try:
        try:
            vec_results = mem.vector_search(query, k=k * 2)
        except Exception as e:
            _logger.warning(f"Vector search failed: {e}")
            vec_results = []

        fts_results = mem.fts_search(query, k=k * 2)

        # RRF fusion
        scores: dict[int, dict] = {}
        for rank, item in enumerate(vec_results):
            sid = item["semantic_rowid"]
            if sid not in scores:
                scores[sid] = {"item": item, "score": 0.0}
            scores[sid]["score"] += 1.0 / (rank + 60)

        for rank, item in enumerate(fts_results):
            sid = item["semantic_rowid"]
            if sid not in scores:
                scores[sid] = {"item": item, "score": 0.0}
            scores[sid]["score"] += 1.0 / (rank + 60)

        sorted_results = sorted(scores.values(), key=lambda x: -x["score"])
        return [
            {
                "semantic_rowid": r["item"]["semantic_rowid"],
                "text": r["item"]["text"],
                "score": r["score"],
            }
            for r in sorted_results[:k]
        ]
    finally:
        mem.close()
