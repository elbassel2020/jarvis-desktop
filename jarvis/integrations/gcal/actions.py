"""Google Calendar actions. Reuses Gmail OAuth credentials (shared scopes)."""
import logging
import time
from datetime import datetime, timedelta

from googleapiclient.discovery import build

from jarvis.integrations.gmail.auth import get_credentials
from jarvis.security.audit import write_audit

_logger = logging.getLogger("jarvis.gcal")

TZ = "Asia/Riyadh"


def _service():
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google OAuth not set up. Run scripts/setup_gmail_oauth.py")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_today() -> list[dict]:
    """Return today's calendar events."""
    t0 = time.monotonic()
    try:
        svc = _service()
        now = datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "+03:00"
        day_end = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat() + "+03:00"

        resp = svc.events().list(
            calendarId="primary",
            timeMin=day_start,
            timeMax=day_end,
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute()

        events = [
            {
                "id": e["id"],
                "summary": e.get("summary", "(no title)"),
                "start": e.get("start", {}).get(
                    "dateTime", e.get("start", {}).get("date")
                ),
                "end": e.get("end", {}).get(
                    "dateTime", e.get("end", {}).get("date")
                ),
                "location": e.get("location", ""),
            }
            for e in resp.get("items", [])
        ]
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gcal", action="list_today", outcome="ok",
                    egress_host="www.googleapis.com",
                    duration_ms=duration_ms,
                    notes=f"{len(events)} events")
        return events
    except Exception as e:
        write_audit(actor="gcal", action="list_today", outcome="error",
                    notes=str(e)[:200])
        raise


def free_busy(start_iso: str, end_iso: str) -> dict:
    """Check if calendar is free in a given window."""
    t0 = time.monotonic()
    try:
        svc = _service()
        resp = svc.freebusy().query(body={
            "timeMin": start_iso,
            "timeMax": end_iso,
            "timeZone": TZ,
            "items": [{"id": "primary"}],
        }).execute()
        busy = resp.get("calendars", {}).get("primary", {}).get("busy", [])
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gcal", action="free_busy", outcome="ok",
                    egress_host="www.googleapis.com",
                    duration_ms=duration_ms,
                    notes=f"{len(busy)} busy intervals")
        return {"busy_intervals": busy, "is_free": len(busy) == 0}
    except Exception as e:
        write_audit(actor="gcal", action="free_busy", outcome="error",
                    notes=str(e)[:200])
        raise


def create_event(summary: str, start_iso: str, end_iso: str,
                 description: str = "", location: str = "") -> dict:
    """Create calendar event. Destructive — requires confirmation upstream."""
    t0 = time.monotonic()
    try:
        svc = _service()
        event_body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_iso, "timeZone": TZ},
            "end": {"dateTime": end_iso, "timeZone": TZ},
        }
        event = svc.events().insert(calendarId="primary", body=event_body).execute()
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gcal", action="create_event",
                    params={"summary": summary[:100], "start": start_iso},
                    outcome="ok", egress_host="www.googleapis.com",
                    duration_ms=duration_ms,
                    notes=f"event_id={event.get('id')}")
        return {"event_id": event.get("id"), "link": event.get("htmlLink")}
    except Exception as e:
        write_audit(actor="gcal", action="create_event", outcome="error",
                    notes=str(e)[:200])
        raise
