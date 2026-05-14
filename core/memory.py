"""4-layer memory + daily patterns for Jarvis."""
import sqlite3
from pathlib import Path
from datetime import datetime
from loguru import logger

DB_PATH = Path('data/memory.db')
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    transcript TEXT, intent TEXT, response TEXT, backend TEXT,
    latency_s REAL, confidence REAL, success INTEGER
);
CREATE TABLE IF NOT EXISTS semantic (
    key TEXT PRIMARY KEY, value TEXT, category TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS daily_apps (
    date TEXT, hour INTEGER, app_name TEXT, open_count INTEGER DEFAULT 1,
    PRIMARY KEY (date, hour, app_name)
);
CREATE INDEX IF NOT EXISTS idx_episodic_time ON episodic(timestamp);
CREATE INDEX IF NOT EXISTS idx_daily_apps ON daily_apps(date, hour);
"""


class JarvisMemory:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._seed_walid()
        logger.info("Memory: ready")

    def _seed_walid(self):
        facts = {
            'name': 'Walid Al-Bassel (والد البصل)',
            'business': 'MSMA Group — B2B electrical contractor solo operator',
            'location': 'Jubail, Saudi Arabia',
            'languages': 'Arabic (Egyptian dialect primary), English',
            'capacity': '60 hours/month',
            'primary_customer': 'Zamilfood (cash) — PRIMARY focus',
            'secondary_customer': 'SMI (deferred payment, high RFQ volume)',
            'other_customers': 'Olayan Descon (Abdul Fardeen), BHIG, Taj Construction',
            'communication': 'Direct, practical, wants honest feedback',
            'msma_path': 'C:\\\\Users\\\\walid\\\\Documents\\\\MSMA',
            'msma_running': '24/7 Windows service',
            'preferred_brands': 'Schneider > ABB > Siemens',
            'compliance': 'ZATCA Phase 2 deadline June 30 2026',
        }
        cur = self.conn.cursor()
        for k, v in facts.items():
            cur.execute(
                "INSERT OR REPLACE INTO semantic VALUES (?, ?, ?, ?)",
                (k, v, 'identity', datetime.now().isoformat())
            )
        self.conn.commit()

    def log_episode(self, transcript, intent, response, backend, latency, confidence, success):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO episodic (timestamp, transcript, intent, response, backend, latency_s, confidence, success) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), transcript, intent, response, backend, latency, confidence, int(success))
        )
        self.conn.commit()

    def log_app_open(self, app_name):
        now = datetime.now()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO daily_apps (date, hour, app_name, open_count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(date, hour, app_name) DO UPDATE SET open_count = open_count + 1",
            (now.strftime('%Y-%m-%d'), now.hour, app_name)
        )
        self.conn.commit()

    def get_typical_apps(self, hour=None):
        if hour is None:
            hour = datetime.now().hour
        cur = self.conn.cursor()
        cur.execute(
            "SELECT app_name, SUM(open_count) FROM daily_apps WHERE hour=? GROUP BY app_name ORDER BY 2 DESC LIMIT 5",
            (hour,)
        )
        return cur.fetchall()

    def get_daily_summary(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT app_name, SUM(open_count) FROM daily_apps WHERE date >= date('now', '-7 days') "
            "GROUP BY app_name ORDER BY 2 DESC LIMIT 5"
        )
        results = cur.fetchall()
        return 'Top apps last 7 days: ' + ', '.join(f'{a}({n}x)' for a, n in results) if results else 'No usage yet'

    def get_context_for_prompt(self):
        cur = self.conn.cursor()
        cur.execute("SELECT key, value FROM semantic WHERE category='identity'")
        facts = '\n'.join(f"- {k}: {v}" for k, v in cur.fetchall())
        cur.execute("SELECT transcript, intent, response FROM episodic ORDER BY id DESC LIMIT 5")
        recent = cur.fetchall()
        recent_str = (
            '\n'.join(f"- '{t}' → {i} → '{r[:60]}'" for t, i, r in recent)
            if recent else 'None yet'
        )
        return f"\nIDENTITY:\n{facts}\n\nRECENT 5:\n{recent_str}"

    def stats(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM episodic")
        e = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM semantic")
        s = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM daily_apps")
        a = cur.fetchone()[0]
        return {'episodes': e, 'facts': s, 'app_records': a}
