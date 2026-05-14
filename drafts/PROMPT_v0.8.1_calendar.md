# Sprint Prompt: JARVIS v0.8.1 — Google Calendar Integration

> Paste this to Claude Code to implement. Review PHASE_10_MSMA_BRIDGE.md section 9 first.

---

JARVIS v0.8.1 — Google Calendar Integration

Add voice-driven Google Calendar read + create via `google-api-python-client`.

SCOPE:
- Read today's events
- Create new events by voice
- List upcoming week
- NO delete, NO modify existing events

CONSTRAINTS:
- New file: `core/calendar_bridge.py` — CalendarBridge class
- Add `calendar_query` and `calendar_create` to `safe_actions.py` + ACTION_MAP
- Add `calendar_query`, `calendar_create` to brain_router.py SYSTEM_PROMPT ACTIONS
- `calendar_create` is DESTRUCTIVE → `confirmation_required=true`
- OAuth token stored in `config/google_token.json` (gitignored)
- DO NOT modify core/*.py logic beyond safe_actions.py

FILES TO MODIFY: actions/safe_actions.py, core/brain_router.py
FILES TO CREATE: core/calendar_bridge.py
DEPENDENCIES: Add to requirements.txt: google-api-python-client, google-auth-oauthlib

IMPLEMENTATION STEPS:
1. Create core/calendar_bridge.py:
   - CalendarBridge class with OAuth2 flow
   - `get_today_events() → list[dict]`
   - `get_week_events() → list[dict]`
   - `create_event(title, date, time, duration_h=1) → dict`
   - Format events as Arabic/English spoken strings

2. Add to safe_actions.py:
   - `calendar_today(transcript=None) → dict` — speak today's events
   - `calendar_week(transcript=None) → dict` — speak week events
   - `calendar_create(transcript=None) → dict` — parse transcript for date/time/title, confirm, create

3. Add to ACTION_MAP:
   - `'calendar_today': 'calendar_today'`
   - `'calendar_week': 'calendar_week'`
   - `'calendar_create': 'calendar_create'`

4. Add to brain_router.py SYSTEM_PROMPT ACTIONS section:
   - `calendar_today`: read today's calendar
   - `calendar_week`: read this week's schedule
   - `calendar_create`: create calendar event (DESTRUCTIVE — needs confirmation)

5. Add tests in tests/test_calendar_bridge.py — all OAuth mocked

VOICE EXAMPLES:
"ايه اجندتي النهارده" → calendar_today
"show this week's schedule" → calendar_week
"add meeting with SMI tomorrow 10 AM" → calendar_create (confirms first)

COMMIT MESSAGE TEMPLATE:
feat: v0.8.1 — Google Calendar integration (read + create)

DO NOT implement:
- Calendar event deletion or modification
- Recurring events
- Shared calendars (only primary calendar)
