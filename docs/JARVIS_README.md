# Jarvis Desktop — User Guide

**v0.8.0 | B2B Electrical Contractor AI Companion**
Personal voice assistant for Walid Al-Bassel | MSMA Group, Jubail KSA

---

## What Is Jarvis?

Jarvis is a voice-activated desktop AI that:
- Wakes on "Hey Jarvis" keyword
- Transcribes Arabic / English speech via Groq Whisper (≈300ms)
- Routes intent through Claude / Gemini / Qwen (by complexity)
- Executes safe desktop actions or responds conversationally
- Remembers interactions, reflects nightly, learns daily at 6 AM

---

## Quick Start

### Prerequisites
- Windows 10/11
- Python 3.11+
- Microphone
- API keys: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `ELEVENLABS_API_KEY`
- Optional: `GEMINI_API_KEY` (faster simple queries)

### Install
```bat
cd C:\Users\walid\Documents\Jarvis
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Configure
Edit `config/.env`:
```env
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
ELEVENLABS_API_KEY=...
GEMINI_API_KEY=...          # optional
ENABLE_ACTIONS=true         # enable desktop actions
WAKE_WORD=hey_jarvis_v0.1
WAKE_THRESHOLD=0.45
CAPTURE_DURATION=5
WHISPER_MODEL=whisper-large-v3-turbo
LLM_MODEL=qwen2.5:7b
```

### Run Manually
```bat
start_jarvis.bat            # visible console
```

### Auto-Start (Windows Startup)
Jarvis installs itself at Windows startup via `start_jarvis_silent.vbs`.
This runs silently on login — no console window.

**Controls:**
```bat
stop_jarvis.bat             # kill python.exe
restart_jarvis.bat          # stop + silent restart
```

---

## Voice Commands

### Time & Status
| Say | Action |
|-----|--------|
| "كم الساعة" / "what time is it" | Reads current time |
| "system status" / "how's the PC" | CPU + RAM report |
| "take a screenshot" / "خد لقطة" | Screenshot + open |

### Apps
| Say | Action |
|-----|--------|
| "open chrome" / "افتح كروم" | Launch Chrome |
| "open excel" / "افتحلي excel" | Launch Excel |
| "open word / notepad / calculator" | Launch app |
| "close chrome" / "اغلق كروم" | Close (asks confirmation) |

**Full whitelist:** calculator, notepad, chrome, edge, explorer, cmd, terminal, powershell, vscode, word, excel, outlook, paint, taskmgr, settings, calendar, mail, photos, store, snipping

### System Controls
| Say | Action |
|-----|--------|
| "volume up / down / mute" | Adjust volume |
| "lock screen" / "اقفل الشاشة" | Lock PC (confirms first) |
| "sleep" / "نم" | Sleep PC (confirms first) |

### Search & Weather
| Say | Action |
|-----|--------|
| "search for Schneider MCB" | Google search |
| "weather" | Jubail weather |

### Daily Brief
| Say | Action |
|-----|--------|
| "morning brief" / "ايه الجديد" | Read today's AI-generated brief |

### Conversation
Everything else → Claude/Gemini/Qwen conversation.
Arabic Egyptian dialect + English both work.

---

## Confirmation Dialogs

**Destructive actions require "yes/no":**
- `close_app`, `lock_screen`, `sleep_pc`

Say: **"تمام" / "yes" / "ok" / "confirm"** → execute
Say: **"لا" / "no" / "cancel"** → abort

---

## Daily Learning (v0.8.0)

Every day at **6:00 AM**, Jarvis runs 7 web searches:
- Saudi electrical standards updates
- ZATCA e-invoicing news
- Schneider pricing
- Energy tariffs
- B2B procurement tips
- USD/SAR rate
- Jubail business news

Results stored in memory. Morning brief available via voice command.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "GROQ_API_KEY not set" | Add key to `config/.env` |
| Wake word not triggering | Lower `WAKE_THRESHOLD` (e.g. 0.35) |
| TTS silent | Check `ELEVENLABS_API_KEY`, test speakers |
| Actions not executing | Set `ENABLE_ACTIONS=true` in `.env` |
| High latency | Use Gemini for simple queries (add `GEMINI_API_KEY`) |
| Arabic not recognized | Groq auto-detects — ensure clear speech |
| Memory errors | Delete `data/memory.db` to reset (loses history) |

---

## File Locations

| Path | Purpose |
|------|---------|
| `config/.env` | API keys + settings |
| `data/memory.db` | SQLite memory (do not delete casually) |
| `logs/jarvis_*.log` | Daily logs (7-day retention) |
| `logs/captures/` | WAV audio captures |
| `logs/screenshots/` | Screenshots |
| `logs/pipeline.jsonl` | Full interaction audit log |
