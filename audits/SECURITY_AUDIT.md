# Jarvis Desktop — Security Audit

**Date:** 2026-05-14 | **Version:** v0.8.0
**Auditor:** Claude Sonnet 4.6 (autonomous audit)
**Scope:** All `.py` files in `core/`, `actions/`, `main.py`

---

## Executive Summary

Jarvis Desktop has a **good security posture** for a local-only desktop app. No hardcoded API keys found. The primary concern is a low-severity `subprocess(shell=True)` call that — due to the existing whitelist — is not directly exploitable by voice input. All other findings are informational or best-practice improvements.

---

## Findings

### MEDIUM — subprocess with `shell=True` in `open_app`

**File:** `actions/safe_actions.py` line 172
**Code:**
```python
subprocess.Popen(exe, shell=True)
```
**Where `exe` comes from:**
```python
for name, exe in self.allowed_apps.items():
    if name in text_lower:
        matched = (name, exe)
        break
```

**Analysis:**
- `exe` is always a hardcoded string from `allowed_apps` dict (e.g., `'calc.exe'`, `'chrome.exe'`)
- The dict key (app name) is matched against voice transcript — transcript never enters `exe`
- `shell=True` is unnecessary since `exe` is a fixed string, not a shell command
- **Exploitability:** LOW — would require modifying the `allowed_apps` dict in source (not via voice)
- **Concern:** If a future developer passes `transcript` directly to `Popen`, `shell=True` becomes injection risk

**Remediation (not yet implemented):**
```python
# Replace:
subprocess.Popen(exe, shell=True)
# With:
subprocess.Popen([exe])  # shell=False (default), no injection possible
```

---

### LOW — `taskkill` with whitelist-matched process name

**File:** `actions/safe_actions.py`, `close_app()` method
**Code:**
```python
subprocess.run(['taskkill', '/F', '/IM', exe], capture_output=True)
```

**Analysis:**
- `exe` is hardcoded in `process_map` dict (e.g., `'chrome.exe'`, `'WINWORD.EXE'`)
- Voice transcript only selects the dict key, never enters the subprocess args
- Uses list form (not `shell=True`) — correct
- **Exploitability:** None via voice input
- **Concern:** `taskkill /F` is force-kill — no graceful shutdown, may cause data loss

**Remediation suggestion:** For Word/Excel/Outlook, prefer `taskkill /IM` without `/F` to allow graceful shutdown.

---

### LOW — API key loaded from `os.environ` without validation

**Files:** `core/brain_router.py`, `core/daily_learning.py`, `core/transcriber.py`
**Example:**
```python
self._client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
```

**Analysis:**
- Keys come from `config/.env` (excluded from git via `.gitignore` ✓)
- No validation that keys are non-empty before use
- If `.env` missing or key empty, `Anthropic(api_key='')` is called — fails at API call time (not init)
- **Exploitability:** None. Local-only concern.

**Remediation suggestion:**
```python
key = os.getenv('ANTHROPIC_API_KEY')
if not key:
    raise RuntimeError("ANTHROPIC_API_KEY not set")
```
(Already implemented in `Transcriber` — pattern should be consistent across all modules.)

---

### LOW — Audit log `pipeline.jsonl` contains full transcripts

**File:** `core/pipeline.py`, `logs/pipeline.jsonl`
**Code:**
```python
entry = {
    'transcript': transcript,   # full voice text
    'decision': decision,
    ...
}
```

**Analysis:**
- All voice commands are stored in plaintext in `logs/pipeline.jsonl`
- Includes potentially sensitive business queries (customer names, quotes, etc.)
- Log file has no access controls beyond filesystem permissions
- **Risk:** If device is compromised or log file is shared, business-sensitive info exposed

**Remediation suggestion:**
- Add log retention cleanup (`logs/*.jsonl` → 7-day rotation, already done for `jarvis_*.log`)
- Consider hashing or omitting sensitive transcript content in audit log

---

### LOW — SQLite database has no encryption

**File:** `data/memory.db`
**Analysis:**
- Contains full interaction history, identity facts, ZATCA notes, business insights
- SQLite file is unencrypted on disk
- Accessible to any process/user on the machine
- **Risk:** If device is stolen or shared, business data exposed

**Remediation suggestion (optional, complex):**
- Use SQLCipher (encrypted SQLite) — requires replacing `sqlite3` with `sqlcipher3`
- Or: simply ensure full-disk encryption (BitLocker) is enabled on machine

---

### INFORMATIONAL — No authentication on local process

**Analysis:**
- Jarvis runs as any Python process — no PID file, no lock file
- Multiple instances could run simultaneously (not prevented)
- `stop_jarvis.bat` kills ALL `python.exe` processes — may affect other Python apps

**Remediation suggestion:**
- Use a PID file (`logs/jarvis.pid`) to track and stop specific process
- `taskkill /PID <pid>` instead of `/IM python.exe`

---

### INFORMATIONAL — No rate limiting on wake detection

**Analysis:**
- Wake detection fires callback, which acquires a threading lock
- Lock prevents concurrent processing — good
- But no rate limit on how often "hey jarvis" can be triggered
- A looping audio source could trigger continuous processing
- **Exploitability:** Physical access required. Local-only threat.

---

## Positive Findings ✓

| Item | Status |
|------|--------|
| API keys in `.env`, excluded from git | ✓ GOOD |
| Action whitelist hardcoded in source | ✓ GOOD |
| `taskkill` uses list form (no shell injection) | ✓ GOOD |
| No `eval()` or `exec()` in codebase | ✓ GOOD |
| No hardcoded API keys in source | ✓ GOOD |
| Memory DB path is local-only | ✓ GOOD |
| Confirmation required for destructive actions | ✓ GOOD |
| No web-facing endpoints | ✓ GOOD |

---

## Risk Summary

| Severity | Count | Items |
|----------|-------|-------|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 1 | subprocess shell=True (not exploitable via voice) |
| LOW | 4 | API key validation, audit log contents, DB encryption, PID file |
| INFO | 2 | Multi-instance, wake rate limiting |

**Overall risk level: LOW** for a local desktop app with no network exposure.
