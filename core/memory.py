"""4-layer memory + daily patterns + reflections + success tracking."""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
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
CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, insights TEXT, metrics_json TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS tuning (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodic_time ON episodic(timestamp);
CREATE INDEX IF NOT EXISTS idx_daily_apps ON daily_apps(date, hour);
CREATE TABLE IF NOT EXISTS daily_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, category TEXT, query TEXT, summary TEXT, source_url TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS morning_briefs (
    date TEXT PRIMARY KEY, brief TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_insights_date ON daily_insights(date, category);
"""


class JarvisMemory:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._seed_walid()

    def _seed_walid(self):
        facts = {
            # --- Identity ---
            'name': 'Walid Al-Bassel (والد البصل) — يفضل "يا بابا" أو "يا فالح"',
            'business': 'MSMA Group — B2B electrical contractor, solo operator',
            'location': 'Jubail, Saudi Arabia (المنطقة الشرقية)',
            'nationality': 'Egyptian living in Saudi Arabia — مصري في جبيل',
            'languages': 'Arabic Egyptian dialect + English — يخلطهم بشكل طبيعي',
            'age_range': 'Mid-career professional, experienced engineer',

            # --- Business Operations ---
            'work_capacity': '60 hours/month billable — solo so time is critical',
            'business_model': 'B2B only — no retail, no end users, only industrial clients',
            'specialization': 'MV/LV electrical panels, switchgear, power distribution',
            'quote_process': 'RFQ → supplier quotes → margin → proposal — solo workflow',
            'payment_preference': 'Cash clients first — deferred payment strains cash flow',
            'invoicing': 'ZATCA Phase 2 compliant e-invoicing required by June 30 2026',

            # --- Customers ---
            'primary_customer': 'Zamilfood — cash payment, fast decisions, priority 1',
            'secondary_customer': 'SMI — high RFQ volume but deferred payment',
            'customer_olayan': 'Olayan Descon — contact: Fardeen, good relationship',
            'customer_bhig': 'BHIG — active customer',
            'customer_taj': 'Taj Construction — active customer',
            'customer_priority': 'Zamilfood > Olayan > BHIG = Taj > SMI (by cash priority)',

            # --- Preferred Brands & Suppliers ---
            'preferred_brands': 'Schneider Electric > ABB > Siemens for panels',
            'schneider_use': 'MV/LV switchgear, automation, easiest KSA sourcing',
            'abb_use': 'Drives, motors, heavy industrial — secondary choice',
            'siemens_use': 'Backup option, less common in his supply chain',
            'supplier_strategy': 'Source locally in KSA first, import if unavoidable',

            # --- MSMA Bot System ---
            'msma_bot': 'MSMA bot runs 24/7 as Windows service at C:\\\\Users\\\\walid\\\\Documents\\\\MSMA',
            'msma_bot_function': 'Monitors emails, extracts RFQs, auto-responds, generates quotes',
            'msma_bot_stack': 'Python FastAPI, SQLite, Claude API, Gmail IMAP/SMTP',
            'msma_bot_status': 'Operational — Jarvis future bridge planned via localhost:9000',
            'msma_email_rule': 'Customer emails must NEVER mention AI/bot/automated — appear personal from Walid',

            # --- Jarvis System ---
            'jarvis_purpose': 'Personal AI companion, voice assistant, MSMA bridge — يارفيس مش أداة، صاحب',
            'jarvis_voice': 'Brian (ElevenLabs) — warm, friendly — Walid chose it',
            'jarvis_wake_word': 'hey_jarvis',
            'jarvis_llm_routing': 'Gemini (simple) → Claude Sonnet (medium) → Claude Opus+web (complex) → Qwen fallback',
            'jarvis_stt': 'Groq Whisper-Large-v3-Turbo — sub-second Arabic + English',

            # --- Communication Style ---
            'communication_style': 'Direct, practical, hates fluff and filler words',
            'preferred_response_length': 'Short answers — 20 words max for spoken, detail only if asked',
            'honesty_expectation': 'Correct him when wrong — do NOT agree just to please him',
            'emotional_support': 'When tired/stressed: ريّح يا بابا — validate then move on',
            'humor': 'Light Egyptian humor OK — يا فالح, يا باشا — context-sensitive',

            # --- Compliance & Finance ---
            'compliance_concern': 'ZATCA Phase 2 e-invoicing — deadline June 30 2026',
            'tax_regime': 'VAT registered Saudi Arabia — 15% VAT on B2B services',
            'financial_sensitivity': 'Cash flow critical — solo operator, no buffer team',

            # --- Technical Expertise ---
            'engineering_background': 'Electrical engineer — MV/LV systems, IEC standards, KSA SASO norms',
            'standards_knowledge': 'IEC 60364, IEC 61439, Saudi SASO equivalents',
            'site_experience': 'Industrial sites: food processing, petrochemical support, general industry',
            'software_comfort': 'Windows power user, Python-aware, comfortable with APIs',

            # --- Personal Preferences ---
            'working_hours': 'Early morning focus — uses Jarvis 6-8 AM primarily',
            'pc_setup': 'Windows 11, VSCode, Python env, always-on MSMA service',
            'browser_default': 'Chrome — edge as fallback',
            'music_taste': 'Occasionally plays music during work — can stop with voice',
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

    def get_relevant_facts(self, query: str, max_facts: int = 5) -> str:
        """Return facts relevant to query via keyword scoring."""
        cur = self.conn.cursor()
        cur.execute("SELECT key, value FROM semantic WHERE category='identity'")
        all_facts = cur.fetchall()
        q_words = {w.lower() for w in query.split() if len(w) > 2}
        identity_keys = {'name', 'business', 'location', 'languages'}
        scored = []
        for k, v in all_facts:
            text = (k + ' ' + v).lower()
            score = sum(1 for w in q_words if w in text)
            if k in identity_keys:
                score += 2  # always include core identity
            scored.append((score, k, v))
        scored.sort(reverse=True)
        top = [item for item in scored if item[0] > 0][:max_facts + len(identity_keys)]
        return '\n'.join(f'- {k}: {v}' for _, k, v in top) if top else ''

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

    def get_recent_episodes(self, n=5):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT transcript, intent, response, success FROM episodic ORDER BY id DESC LIMIT ?", (n,)
        )
        return cur.fetchall()

    def get_success_stats(self, days=7):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) as total, SUM(success) as successes, "
            "AVG(latency_s) as avg_latency, AVG(confidence) as avg_conf "
            "FROM episodic WHERE timestamp > ?",
            ((datetime.now() - timedelta(days=days)).isoformat(),)
        )
        return cur.fetchone()

    def get_context_for_prompt(self):
        """Full context (used by screen_awareness path)."""
        cur = self.conn.cursor()
        cur.execute("SELECT key, value FROM semantic WHERE category='identity'")
        facts = '\n'.join(f'- {k}: {v}' for k, v in cur.fetchall())
        cur.execute("SELECT transcript, intent, response FROM episodic ORDER BY id DESC LIMIT 5")
        recent = cur.fetchall()
        recent_str = (
            '\n'.join(f"- '{t}' → {i} → '{r[:60]}'" for t, i, r in recent)
            if recent else 'None yet'
        )
        return f"\nIDENTITY:\n{facts}\n\nRECENT 5:\n{recent_str}"

    def save_reflection(self, insights, metrics_json=None):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO reflections (date, insights, metrics_json, created_at) VALUES (?, ?, ?, ?)",
            (datetime.now().strftime('%Y-%m-%d'), insights, metrics_json or '{}', datetime.now().isoformat())
        )
        self.conn.commit()

    def get_latest_reflection(self):
        cur = self.conn.cursor()
        cur.execute("SELECT date, insights FROM reflections ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return f"Last reflection ({row[0]}): {row[1][:200]}" if row else "No reflections yet"

    def set_tuning(self, key, value):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO tuning VALUES (?, ?, ?)",
            (key, str(value), datetime.now().isoformat())
        )
        self.conn.commit()

    def get_tuning(self, key, default=None):
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM tuning WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def add_insight(self, category: str, query: str, summary: str, source_url: str = ''):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO daily_insights (date, category, query, summary, source_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime('%Y-%m-%d'), category, query, summary, source_url, datetime.now().isoformat())
        )
        self.conn.commit()

    def save_morning_brief(self, brief: str):
        today = datetime.now().strftime('%Y-%m-%d')
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO morning_briefs (date, brief, created_at) VALUES (?, ?, ?)",
            (today, brief, datetime.now().isoformat())
        )
        self.conn.commit()

    def get_today_brief(self) -> str:
        today = datetime.now().strftime('%Y-%m-%d')
        cur = self.conn.cursor()
        cur.execute("SELECT brief FROM morning_briefs WHERE date=?", (today,))
        row = cur.fetchone()
        return row[0] if row else ''

    def get_recent_insights(self, days: int = 3, limit: int = 10) -> list:
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        cur = self.conn.cursor()
        cur.execute(
            "SELECT category, query, summary, source_url, date FROM daily_insights "
            "WHERE date >= ? ORDER BY id DESC LIMIT ?",
            (since, limit)
        )
        return cur.fetchall()

    def get_insights_context(self, days: int = 3) -> str:
        rows = self.get_recent_insights(days=days, limit=8)
        if not rows:
            return ''
        lines = [f"- [{r[0]}] {r[2]}" for r in rows]
        return "RECENT LEARNINGS:\n" + '\n'.join(lines)

    def stats(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM episodic")
        e = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM semantic")
        s = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM daily_apps")
        a = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM reflections")
        r = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM daily_insights")
        i = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM morning_briefs")
        b = cur.fetchone()[0]
        return {'episodes': e, 'facts': s, 'app_records': a, 'reflections': r, 'insights': i, 'briefs': b}
