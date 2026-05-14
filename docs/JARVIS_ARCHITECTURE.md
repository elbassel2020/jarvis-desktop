# Jarvis Desktop — Architecture

**v0.8.0**

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        JARVIS PIPELINE                          │
│                                                                 │
│  ┌──────────────┐    wake event    ┌──────────────────────────┐ │
│  │ WakeListener │ ──────────────▶  │   VoiceCapture (VAD)     │ │
│  │ OpenWakeWord │                  │ 100ms chunks, stop on    │ │
│  │ hey_jarvis   │                  │ 1s silence post-speech   │ │
│  └──────────────┘                  └──────────┬───────────────┘ │
│        ▲                                      │ .wav path        │
│        │ cooldown 2s                          ▼                  │
│        │ lock prevents                ┌───────────────┐          │
│        │ concurrent wakes             │  Transcriber  │          │
│                                       │ Groq Whisper  │          │
│                                       │ ▼ fallback    │          │
│                                       │ faster-whisper│          │
│                                       └───────┬───────┘          │
│                                               │ transcript        │
│                                               ▼                  │
│                              ┌────────────────────────────────┐  │
│                              │  Confirmation State Machine     │  │
│                              │  pending_action? → yes/no path │  │
│                              └───────────────┬────────────────┘  │
│                                              │ new query          │
│                                              ▼                  │
│                                    ┌─────────────────┐          │
│                                    │   BrainRouter   │          │
│                                    │ classify_complexity        │
│                                    │ simple→Gemini   │          │
│                                    │ medium→Claude   │          │
│                                    │ complex→Claude  │          │
│                                    │         +web    │          │
│                                    │ fallback→Qwen   │          │
│                                    └────────┬────────┘          │
│                                             │ decision JSON      │
│                                             ▼                  │
│                              ┌──────────────────────────────┐   │
│                              │  Action Gate                  │   │
│                              │  confirmation_required?       │   │
│                              │    yes → speak + pend         │   │
│                              │    no  → execute or chat      │   │
│                              └─────────────┬────────────────┘   │
│                                            │                    │
│                              ┌─────────────▼────────────────┐   │
│                              │  SafeActions (14 actions)     │   │
│                              │  ElevenLabs TTS primary       │   │
│                              │  edge-tts fallback            │   │
│                              │  pygame playback              │   │
│                              └─────────────┬────────────────┘   │
│                                            │                    │
│                              ┌─────────────▼────────────────┐   │
│                              │  JarvisMemory.log_episode()   │   │
│                              │  pipeline.jsonl audit log     │   │
│                              └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## LLM Routing Logic

```
classify_complexity(text)
        │
        ├─ simple (≤6 words)
        │     Gemini 2.5 Flash → Claude Sonnet 4.6 → Qwen 2.5:7b
        │
        ├─ medium (7–15 words)
        │     Claude Sonnet 4.6 → Gemini 2.5 Flash → Qwen 2.5:7b
        │
        └─ complex (≥16 words)
              Claude Opus 4.6 + web_search
              → Claude Sonnet 4.6 + web_search
              → Gemini 2.5 Flash
              → Qwen 2.5:7b
```

**Web search**: Anthropic `web_search_20250305` built-in tool, max 2 uses per query. Response parsing collects all `TextBlock` items (skips `ToolUseBlock`).

---

## Memory Model (7 Layers)

```
┌─────────────────────────────────────────────────────────────┐
│                    data/memory.db (SQLite)                   │
│                                                             │
│  episodic        interactions (transcript→intent→response)  │
│  semantic        key-value facts (identity, seeded at boot) │
│  daily_apps      hourly app open counts                     │
│  reflections     nightly Claude-generated insights          │
│  tuning          dynamic params (confidence_threshold)      │
│  daily_insights  web search results (7 categories/day)      │
│  morning_briefs  AI-generated daily brief (1 per day)       │
└─────────────────────────────────────────────────────────────┘
```

### Context Injection into LLM System Prompt

Each LLM call gets `_full_system(query)`:
1. `SYSTEM_PROMPT` — personality, protocols, actions list
2. `get_relevant_facts(query)` — keyword-scored semantic facts (top 4)
3. `screen.summary()` — current open windows
4. `get_latest_reflection()` — last nightly insight
5. `get_insights_context()` — last 3 days web learnings (if any)
6. `get_today_brief()[:300]` — morning brief (if generated today)

---

## Confirmation State Machine

```
pending_action = None (default)

Wake event received
  └─ if pending_action:
        parse transcript for yes/no
        yes → execute pending_action, clear
        no  → speak "Cancelled", clear
        other → speak "Say yes or no first"
        RETURN (no LLM call)
  └─ else:
        call brain.think()
        if confirmation_required:
          set pending_action, speak "Confirm?"
        else:
          execute directly
```

---

## Auto-Start Mechanism

```
Windows Startup Folder
  └─ start_jarvis_silent.vbs
        └─ WshShell.Run cmd /c ... venv\python.exe main.py
                        window=0 (invisible)
                        bWaitOnReturn=False
```

`main.py` detects non-tty (headless) and removes stderr logger. All output goes to `logs/jarvis_*.log`.

---

## Background Threads (3 daemons)

| Thread | Name | Fires | Purpose |
|--------|------|-------|---------|
| WakeListener | — | continuous | OpenWakeWord keyword detection |
| Reflection | `reflection` | 00:05 daily | Claude nightly insight |
| Learning | `daily_learning` | 06:00 daily | 7 web searches + morning brief |

All are daemon threads — killed automatically on main thread exit.

---

## TTS Chain

```
speak(text)
  ├─ ELEVENLABS_API_KEY set?
  │     yes → ElevenLabs Brian (nPczCjzI2devNBz1zQrb)
  │           eleven_turbo_v2_5 model
  │           stability=0.5, similarity=0.75
  │           → .mp3 → pygame.mixer playback (blocking)
  │
  └─ no / ElevenLabs failed
        → edge-tts en-US-AriaNeural (async)
          → .mp3 → pygame.mixer playback (blocking)
```

---

## Dependency Map

```
pipeline.py
  ├─ wake_listener.py       (openwakeword)
  ├─ voice_capture.py       (sounddevice, scipy, numpy)
  ├─ transcriber.py         (groq, faster-whisper fallback)
  ├─ brain_router.py
  │    ├─ memory.py         (sqlite3)
  │    ├─ screen_awareness.py (win32gui, win32process, psutil)
  │    ├─ anthropic          (Claude)
  │    ├─ google.genai       (Gemini)
  │    └─ ollama             (Qwen fallback)
  ├─ safe_actions.py
  │    ├─ elevenlabs         (TTS)
  │    ├─ edge_tts           (TTS fallback)
  │    ├─ pygame             (audio playback)
  │    └─ PIL                (screenshots)
  └─ reflection.py + daily_learning.py
       └─ anthropic          (Claude)
```

---

## Agent JSON Schema

All LLM backends must return:

```json
{
  "thinking": "1-sentence internal reasoning",
  "action": "action_name",
  "params": "string or null",
  "spoken": "SHORT TTS-safe response (max 50 words, no markdown)",
  "detailed": "Markdown-OK longer explanation (empty if spoken sufficient)",
  "confirmation_required": false,
  "confidence": 0.95
}
```

`spoken` → spoken aloud by TTS
`detailed` → can be shown on screen (markdown rendered)
`response` → alias for `spoken` (backward compat)
