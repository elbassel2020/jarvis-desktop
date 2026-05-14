# Sprint Prompt: JARVIS v0.9.1 — Advanced Actions (Email + Clipboard + Notifications)

> Paste this to Claude Code. Requires v0.9.0 (MSMA bridge) to be running.

---

JARVIS v0.9.1 — Advanced Desktop Actions

Add 3 new safe desktop actions: clipboard read/write, Windows toast notification, and email draft open in Outlook.

SCOPE:
- `clipboard_read` — read clipboard and speak/summarize contents
- `clipboard_write` — write a voice-dictated text to clipboard
- `notify` — send Windows toast notification with custom text
- `open_email_draft` — open Outlook with pre-filled To/Subject from voice
- NO actual email sending — draft only, Walid clicks Send in Outlook

CONSTRAINTS:
- Modify: `actions/safe_actions.py` only (+ ACTION_MAP)
- Modify: `core/brain_router.py` SYSTEM_PROMPT ACTIONS section only
- New dependency: `pyperclip` (clipboard), `win10toast` or `plyer` (notifications)
- `clipboard_write` requires confirmation (overwrites current clipboard)
- `open_email_draft` requires confirmation (opens new Outlook window)
- All other actions: no confirmation needed

IMPLEMENTATION STEPS:

1. Add to safe_actions.py:

```python
def clipboard_read(self, transcript=None) -> dict:
    import pyperclip
    text = pyperclip.paste()
    if not text:
        self.speak("Clipboard is empty يابابا")
        return {'action': 'clipboard_read', 'content': '', 'success': True}
    # Truncate to 200 chars for TTS
    summary = text[:200]
    self.speak(f"Clipboard says: {summary}")
    return {'action': 'clipboard_read', 'content': text[:500], 'success': True}

def clipboard_write(self, transcript=None) -> dict:
    # Extract what to write (after "copy" / "clipboard" keywords)
    if not transcript:
        return {'action': 'clipboard_write', 'error': 'no transcript', 'success': False}
    import pyperclip
    import re
    text = re.sub(r'.*(copy|clipboard|write|انسخ|اكتب)\s+', '', transcript, flags=re.IGNORECASE).strip()
    if not text:
        self.speak("What should I copy يابابا?")
        return {'action': 'clipboard_write', 'error': 'no content', 'success': False}
    pyperclip.copy(text)
    self.speak(f"Copied to clipboard: {text[:50]}")
    return {'action': 'clipboard_write', 'content': text, 'success': True}

def notify(self, transcript=None) -> dict:
    if not transcript:
        return {'action': 'notify', 'error': 'no transcript', 'success': False}
    import re
    msg = re.sub(r'.*(notify|notification|remind|ذكرني|بلغني)\s*:?\s*', '', transcript, flags=re.IGNORECASE).strip()
    if not msg:
        msg = transcript
    try:
        from plyer import notification
        notification.notify(
            title='Jarvis',
            message=msg[:200],
            app_name='Jarvis',
            timeout=10,
        )
        self.speak(f"Notification sent: {msg[:50]}")
        return {'action': 'notify', 'message': msg, 'success': True}
    except Exception as e:
        logger.error(f"Notification failed: {e}")
        return {'action': 'notify', 'error': str(e), 'success': False}

def open_email_draft(self, transcript=None) -> dict:
    if not transcript:
        return {'action': 'open_email_draft', 'error': 'no transcript', 'success': False}
    import re, urllib.parse
    # Parse "email Fardeen about electrical specs"
    to_match = re.search(r'(to|email|send|لـ|ابعت)\s+(\w+)', transcript, re.IGNORECASE)
    subj_match = re.search(r'(about|re|regarding|بخصوص|عن)\s+(.+)', transcript, re.IGNORECASE)
    to = to_match.group(2) if to_match else ''
    subject = subj_match.group(2)[:100] if subj_match else 'Follow up'
    # Open Outlook mailto URI
    mailto = f"mailto:{to}?subject={urllib.parse.quote(subject)}"
    os.startfile(mailto)
    self.speak(f"Opening Outlook draft to {to or 'recipient'} يابابا")
    return {'action': 'open_email_draft', 'to': to, 'subject': subject, 'success': True}
```

2. Add to ACTION_MAP:
```python
'clipboard_read': 'clipboard_read',
'clipboard_write': 'clipboard_write',
'notify': 'notify',
'open_email_draft': 'open_email_draft',
```

3. `clipboard_write` and `open_email_draft` → `confirmation_required: true` in brain

4. Add to brain_router.py SYSTEM_PROMPT ACTIONS:
```
- clipboard_read: read and speak clipboard contents
- clipboard_write: write text to clipboard (DESTRUCTIVE — needs confirmation)
- notify: send Windows desktop notification with custom message
- open_email_draft: open Outlook with pre-filled To/Subject (DESTRUCTIVE — needs confirmation)
```

VOICE EXAMPLES:
"read my clipboard" → clipboard_read
"copy meeting on Thursday 3 PM" → clipboard_write (confirms: "Copy this text?")
"remind me inspect Zamilfood panel" → notify (toast popup)
"open email draft to Fardeen about cable schedule" → open_email_draft (confirms first)

DEPENDENCIES (add to requirements.txt):
```
pyperclip
plyer
```

TESTS: tests/test_advanced_actions.py — mock pyperclip, plyer, os.startfile

COMMIT: feat: v0.9.1 — clipboard + notifications + email draft actions
