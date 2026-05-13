# Jarvis Desktop — Companion to MSMA Bot

**Status:** Phase 1/6 — Foundation + Wake Word Detection Only

## What this does (Phase 1)
- Listens to microphone always-on
- Detects "Hey Jarvis" wake word via openWakeWord
- Logs every detection to `logs/audit.jsonl`
- Does NOT execute any commands yet

## What it does NOT do (yet)
- Execute commands
- Touch files
- Access internet
- Talk to MSMA Bot

## Run

```bash
.\venv\Scripts\activate
python main.py
```

## Test

```bash
.\venv\Scripts\activate
python -m pytest tests/ -v
```

## Phase Roadmap

| Phase | Goal |
|-------|------|
| 1 (NOW) | Wake word detection + audit log |
| 2 | Speech-to-text (Whisper) |
| 3 | Intent classification (local LLM) |
| 4 | MSMA Bot bridge via Telegram |
| 5 | File ops + system actions (gated) |
| 6 | UI overlay |

## Security Gates (config/.env)

All action phases OFF by default:
```
ENABLE_ACTIONS=false
ENABLE_FILE_OPS=false
ENABLE_DIRECT_EXEC=false
```

Never enable without Walid explicit approval.
