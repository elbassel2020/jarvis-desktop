# Jarvis Desktop — Code Quality Audit

**Date:** 2026-05-14 | **Version:** v0.8.0
**Auditor:** Claude Sonnet 4.6 (autonomous audit)

---

## 1. File Summary

| File | Lines | Functions | Long Functions (>30L) |
|------|-------|-----------|----------------------|
| `core/pipeline.py` | 194 | 6 | `__init__` (69L), `on_wake_detected` (85L) |
| `core/brain_router.py` | 292 | 9 | `__init__` (31L), `think` (50L) |
| `core/memory.py` | 245 | 20 | None |
| `core/screen_awareness.py` | 60 | 3 | None |
| `core/voice_capture.py` | 65 | 2 | `capture` (43L) |
| `core/transcriber.py` | 85 | 5 | None |
| `core/reflection.py` | 104 | 2 | `reflect_on_today` (68L) |
| `core/daily_learning.py` | 117 | 3 | `_search_one` (34L), `run` (37L) |
| `core/llm_brain.py` | 61 | 3 | None |
| `actions/safe_actions.py` | 324 | 20 | `close_app` (37L) |
| `main.py` | 34 | 1 | None |
| **TOTAL** | **1481** | **74** | |

---

## 2. Type Hint Coverage

| File | Args Annotated | Return Types |
|------|---------------|-------------|
| `core/pipeline.py` | 0% | 0% |
| `core/brain_router.py` | 68% | 89% |
| `core/memory.py` | 21% | 20% |
| `core/screen_awareness.py` | 0% | 0% |
| `core/voice_capture.py` | 0% | 50% |
| `core/transcriber.py` | 0% | 0% |
| `core/reflection.py` | 0% | 0% |
| `core/daily_learning.py` | 33% | 33% |
| `core/llm_brain.py` | 33% | 67% |
| `actions/safe_actions.py` | 14% | 85% |

**Overall:** ~25% arg annotation, ~50% return type annotation. `brain_router.py` best. Most modules near zero.

**Recommendation:** Add type hints incrementally. Priority: `memory.py` (20 methods), `pipeline.py` (orchestrator), `safe_actions.py` (14 action methods).

---

## 3. Long Functions (>30 lines) — Complexity Concerns

### `pipeline.py::on_wake_detected` — 85 lines ⚠️

Handles 7 distinct responsibilities:
1. Record audio
2. Transcribe
3. Check pending confirmation state
4. Call LLM brain
5. Gate by confidence threshold
6. Execute action
7. Log to memory + audit file

**Refactor suggestion:** Extract into:
- `_handle_confirmation(transcript) → bool`
- `_execute_decision(decision, transcript) → dict`
- `_log_interaction(transcript, decision, execution)`

### `pipeline.py::__init__` — 69 lines ⚠️

Inlines both reflection and learning scheduler thread setup.

**Refactor suggestion:** Extract `_start_reflection_thread()` and `_start_learning_thread()` helpers.

### `reflection.py::reflect_on_today` — 68 lines ⚠️

Handles: stats fetch → prompt build → Claude API call → JSON parse → text format → auto-tune.

**Refactor suggestion:**
- `_build_data_summary() → str`
- `_parse_insights(raw: str) → dict`
- `_auto_tune(success_rate: float)`

### `brain_router.py::think` — 50 lines

Routing + attempt loop. Acceptable — logic is sequential and well-commented.

### `voice_capture.py::capture` — 43 lines

Fixed + VAD mode in one function. Consider splitting into `_capture_fixed()` and `_capture_vad()`.

---

## 4. Duplicate Logic

### `open_app` whitelist vs `close_app` process_map

**File:** `actions/safe_actions.py`

Both `self.allowed_apps` (open) and `process_map` in `close_app` define the same ~12 apps with slightly different exe names:

| App | `allowed_apps` | `process_map` |
|-----|---------------|--------------|
| chrome | `chrome.exe` | `chrome.exe` ✓ |
| word | `winword.exe` | `WINWORD.EXE` (case diff) |
| calculator | `calc.exe` | `CalculatorApp.exe` (different!) |
| calendar | `outlookcal:` | `HxOutlook.exe` (different!) |
| mail | `outlookmail:` | `HxOutlook.exe` (different!) |

`calculator` opens `calc.exe` (classic) but closes `CalculatorApp.exe` (UWP). Both coexist on Windows 11.

**Refactor suggestion:** Create a unified `APP_REGISTRY` dict:
```python
APP_REGISTRY = {
    'chrome': {'open_exe': 'chrome.exe', 'close_exe': 'chrome.exe'},
    'calculator': {'open_exe': 'calc.exe', 'close_exe': 'CalculatorApp.exe'},
    ...
}
```

### TTS path construction repeated

`_speak_elevenlabs()` and `_speak_edge_async()` both construct `tts_dir / f'speech_{timestamp}.mp3'` independently.

**Refactor suggestion:** Extract `_tts_path() → Path` helper.

---

## 5. Dead Code / Unused

### `core/llm_brain.py::SYSTEM_PROMPT`

Old v0.6 prompt still at module level. `LLMBrain` delegates entirely to `BrainRouter`. `SYSTEM_PROMPT` in `llm_brain.py` is never used.

**Recommendation:** Delete `SYSTEM_PROMPT` from `llm_brain.py` to avoid confusion.

### `LLMBrain.speak_sync()` in `safe_actions.py`

```python
def speak_sync(self, text: str, voice='en-US-AriaNeural'):
    return self.speak(text, voice)
```
`speak_sync` is just an alias for `speak`. No callers found outside `safe_actions.py`.

**Recommendation:** Remove `speak_sync` — callers can use `speak` directly.

---

## 6. Magic Numbers/Strings

| Location | Value | Meaning |
|----------|-------|---------|
| `pipeline.py` | `2.0`, `5.0`, `8.0` | Cooldown durations (seconds) |
| `pipeline.py` | `0.45` | Wake threshold default |
| `brain_router.py` | `0.3` | Min confidence to execute |
| `brain_router.py` | `6`, `15` | Complexity word thresholds |
| `reflection.py` | `0.7`, `0.9` | Auto-tune success rate bounds |
| `reflection.py` | `0.2`, `0.4` | Auto-tuned threshold values |
| `voice_capture.py` | `0.01` | Silence RMS threshold |
| `safe_actions.py` | `0.75` | ElevenLabs similarity_boost |

**Recommendation:** Extract to named constants in each module:
```python
# pipeline.py
COOLDOWN_POST_ACTION_S = 8.0
COOLDOWN_POST_CHAT_S = 5.0
MIN_CONFIDENCE_TO_EXECUTE = 0.3
```

---

## 7. Missing Error Handling

### `daily_learning.py::run` — brief generation failure is logged but `morning_brief` not saved
If `save_morning_brief` raises after a partial write, state is inconsistent. Current exception handling only logs. Acceptable for non-critical feature.

### `pipeline.py` — no timeout on `brain.think()`
If all LLM backends hang, pipeline blocks indefinitely. No per-backend timeout beyond HTTP client defaults.

**Recommendation:** Wrap `brain.think()` in `threading.Timer` or use `concurrent.futures.ThreadPoolExecutor` with timeout.

---

## 8. Overall Assessment

| Dimension | Score | Notes |
|-----------|-------|-------|
| Readability | 8/10 | Clear naming, good docstrings in key methods |
| Modularity | 7/10 | Good separation of concerns; some long functions |
| Testability | 9/10 | Clean seams, injectable dependencies, no global state |
| Type safety | 4/10 | Minimal type hints; `dict` return types opaque |
| DRY | 7/10 | Duplicate app maps the main violation |
| Error handling | 7/10 | Good try/except coverage; some gaps in daemon threads |
| Documentation | 8/10 | Module docstrings present; inline comments adequate |

**Top 3 refactors to consider (by impact):**
1. Split `on_wake_detected` (85L) into 3 helper methods
2. Unify `allowed_apps` / `process_map` into `APP_REGISTRY`
3. Add type hints to `memory.py` (highest call volume, most important contract)
