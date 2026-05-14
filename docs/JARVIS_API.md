# Jarvis Desktop — Developer API Reference

**v0.8.0**

---

## Module Structure

```
core/
  pipeline.py          # Main orchestrator — wake → STT → brain → action
  wake_listener.py     # OpenWakeWord keyword detection
  voice_capture.py     # VAD recording → WAV
  transcriber.py       # Groq Whisper → text (faster-whisper fallback)
  brain_router.py      # Multi-LLM routing + JSON parsing
  llm_brain.py         # Thin LLMBrain wrapper over BrainRouter
  memory.py            # 7-table SQLite memory system
  screen_awareness.py  # win32gui window enumeration
  reflection.py        # Nightly Claude-based self-reflection
  daily_learning.py    # 6 AM web search → morning brief

actions/
  safe_actions.py      # All executable desktop actions + TTS

tests/                 # pytest test suite (204+ tests)
config/.env            # API keys + runtime config
data/memory.db         # SQLite persistent memory
logs/                  # Log files, captures, screenshots
```

---

## JarvisMemory (`core/memory.py`)

SQLite-backed 7-table memory store.

```python
from core.memory import JarvisMemory
mem = JarvisMemory()
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `log_episode` | `(transcript, intent, response, backend, latency, confidence, success)` | Log one interaction |
| `log_app_open` | `(app_name: str)` | Increment daily app counter |
| `get_relevant_facts` | `(query: str, max_facts=5) → str` | Keyword-scored fact retrieval |
| `get_recent_episodes` | `(n=5) → list` | Last N interactions |
| `get_success_stats` | `(days=7) → tuple` | `(total, successes, avg_lat, avg_conf)` |
| `get_context_for_prompt` | `() → str` | Full identity + recent episodes string |
| `get_typical_apps` | `(hour=None) → list` | Top apps for given hour |
| `get_daily_summary` | `() → str` | Last 7 days app usage summary |
| `save_reflection` | `(insights: str, metrics_json=None)` | Save nightly reflection |
| `get_latest_reflection` | `() → str` | Most recent reflection text |
| `set_tuning` | `(key: str, value)` | Set tuning parameter |
| `get_tuning` | `(key: str, default=None) → str` | Get tuning parameter |
| `add_insight` | `(category, query, summary, source_url)` | Add daily learning insight |
| `save_morning_brief` | `(brief: str)` | Save today's brief (upsert) |
| `get_today_brief` | `() → str` | Today's brief or `''` |
| `get_recent_insights` | `(days=3, limit=10) → list` | Recent insight rows |
| `get_insights_context` | `(days=3) → str` | Formatted insights for LLM prompt |
| `stats` | `() → dict` | `{episodes, facts, app_records, reflections, insights, briefs}` |

### Schema

```sql
episodic      -- interactions (transcript, intent, response, backend, latency_s, confidence, success)
semantic      -- key-value facts (identity category seeded at init)
daily_apps    -- hour-bucketed app open counts
reflections   -- nightly insights from Claude
tuning        -- dynamic parameters (confidence_threshold)
daily_insights -- web search results by category/date
morning_briefs -- one per day (upsert)
```

---

## BrainRouter (`core/brain_router.py`)

Multi-LLM routing engine. Selects backend by query complexity.

```python
from core.brain_router import BrainRouter
router = BrainRouter()
result = router.think("open excel")
```

### `classify_complexity(text: str) → str`

Word-count heuristic:
- `≤ 6 words` → `'simple'` (Gemini first)
- `7–15 words` → `'medium'` (Claude Sonnet first)
- `≥ 16 words` → `'complex'` (Claude Opus + web_search)

### `BrainRouter.think(transcript: str) → dict`

Returns standard result dict:

```python
{
    'action': str,              # intent label
    'params': str | None,       # action parameter
    'spoken': str,              # TTS-safe short response
    'detailed': str,            # Markdown-OK long response
    'response': str,            # same as spoken (backward compat)
    'thinking': str,            # internal reasoning
    'confirmation_required': bool,
    'confidence': float,        # 0.0–1.0
    'duration_s': float,
    'raw_text': str,
    'backend': str,             # 'anthropic/claude-sonnet-4-6', 'google/gemini-2.5-flash', etc.
    'complexity': str,
}
```

### Routing Order

| Complexity | Attempt order |
|-----------|--------------|
| simple | Gemini → Claude Sonnet → Qwen |
| medium | Claude Sonnet → Gemini → Qwen |
| complex | Claude Opus (web) → Claude Sonnet (web) → Gemini → Qwen |

Web search (`web_search_20250305`) enabled for complex queries via Claude.

---

## SafeActions (`actions/safe_actions.py`)

All desktop actions. Each returns `{'action': str, 'success': bool, ...}`.

```python
from actions.safe_actions import SafeActions, execute
actions = SafeActions()
result = actions.time()
# or via intent dict:
result = execute({'intent': 'time', 'raw_text': ''}, actions)
```

### Action Methods

| Method | Confirmation | Description |
|--------|-------------|-------------|
| `time()` | No | Speak current time |
| `weather(city='Jubail')` | No | wttr.in weather |
| `screenshot()` | No | Capture + open + speak |
| `open_app(transcript)` | No | Launch whitelisted app |
| `close_app(transcript)` | **Yes** | taskkill whitelisted process |
| `volume_up()` | No | +5 volume steps |
| `volume_down()` | No | -5 volume steps |
| `mute()` | No | Toggle mute |
| `lock_screen()` | **Yes** | rundll32 LockWorkStation |
| `sleep_pc()` | **Yes** | SetSuspendState |
| `search(transcript)` | No | Open Google search |
| `system_status()` | No | psutil CPU + RAM |
| `morning_brief()` | No | Speak today's brief |
| `cancel()` | No | Speak "Cancelled" |

### Adding a New Action

1. Add method to `SafeActions`:
```python
def my_action(self, transcript=None) -> dict:
    # ... logic ...
    self.speak("Done!")
    return {'action': 'my_action', 'success': True}
```

2. Add to `ACTION_MAP`:
```python
ACTION_MAP = {
    ...
    'my_action': 'my_action',
}
```

3. Add to `SYSTEM_PROMPT` in `brain_router.py` under `ACTIONS:`.

4. Add tests in `tests/test_safe_actions_full.py`.

---

## Transcriber (`core/transcriber.py`)

```python
from core.transcriber import Transcriber
t = Transcriber(model_name='whisper-large-v3-turbo')
result = t.transcribe(audio_path)
# result: {'text', 'language', 'duration_s', 'audio_file', 'backend'}
```

- **Primary**: Groq Whisper-Large-v3-Turbo (~300ms)
- **Fallback**: faster-whisper medium (CPU, lazy-loaded)
- `language=None` → auto-detect (Arabic/English both work)

---

## VoiceCapture (`core/voice_capture.py`)

```python
from core.voice_capture import VoiceCapture
vc = VoiceCapture(duration=5, use_vad=True)
path = vc.capture()  # returns Path to .wav file
```

VAD mode: 100ms chunks, stops after 1s silence post-speech. Falls back to fixed-duration if VAD disabled.

---

## JarvisPipeline (`core/pipeline.py`)

Main entry point. Runs three background daemons:
- **Wake listener** — OpenWakeWord keyword detection
- **Reflection thread** — fires at 00:05 daily
- **Learning thread** — fires at 06:00 daily

```python
from core.pipeline import JarvisPipeline
JarvisPipeline().run()
```

---

## DailyLearner (`core/daily_learning.py`)

```python
from core.daily_learning import DailyLearner
DailyLearner().run()  # runs all 7 searches + generates brief
```

Can be run manually to seed learning on demand.

---

## Reflector (`core/reflection.py`)

```python
from core.reflection import Reflector
result = Reflector().reflect_on_today()  # returns insight text or None
```

Auto-tunes `confidence_threshold` in memory:
- `< 70%` success rate → threshold 0.2 (more permissive)
- `> 90%` success rate → threshold 0.4 (stricter)
