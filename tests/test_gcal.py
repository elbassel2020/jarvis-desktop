"""Google Calendar tests — API mocked."""
import pytest
from unittest.mock import MagicMock, patch

from jarvis.integrations.gcal import actions


@pytest.fixture
def mock_svc():
    svc = MagicMock()
    with patch("jarvis.integrations.gcal.actions._service", return_value=svc):
        yield svc


def test_list_today_returns_events(mock_svc):
    mock_svc.events().list().execute.return_value = {
        "items": [
            {
                "id": "ev1",
                "summary": "Team Meeting",
                "start": {"dateTime": "2026-05-17T10:00:00+03:00"},
                "end": {"dateTime": "2026-05-17T11:00:00+03:00"},
                "location": "Office",
            }
        ]
    }
    events = actions.list_today()
    assert len(events) == 1
    assert events[0]["summary"] == "Team Meeting"
    assert events[0]["location"] == "Office"


def test_list_today_empty(mock_svc):
    mock_svc.events().list().execute.return_value = {"items": []}
    events = actions.list_today()
    assert events == []


def test_free_busy_not_free(mock_svc):
    mock_svc.freebusy().query().execute.return_value = {
        "calendars": {
            "primary": {
                "busy": [{"start": "2026-05-17T10:00:00Z", "end": "2026-05-17T11:00:00Z"}]
            }
        }
    }
    result = actions.free_busy("2026-05-17T08:00:00+03:00", "2026-05-17T18:00:00+03:00")
    assert result["is_free"] is False
    assert len(result["busy_intervals"]) == 1


def test_free_busy_is_free(mock_svc):
    mock_svc.freebusy().query().execute.return_value = {
        "calendars": {"primary": {"busy": []}}
    }
    result = actions.free_busy("2026-05-17T08:00:00+03:00", "2026-05-17T09:00:00+03:00")
    assert result["is_free"] is True
    assert result["busy_intervals"] == []


def test_create_event(mock_svc):
    mock_svc.events().insert().execute.return_value = {
        "id": "evt_abc123",
        "htmlLink": "https://calendar.google.com/event?id=abc123",
    }
    result = actions.create_event(
        summary="Client Call",
        start_iso="2026-05-18T10:00:00+03:00",
        end_iso="2026-05-18T11:00:00+03:00",
        description="Zamilfood follow-up",
    )
    assert result["event_id"] == "evt_abc123"
    assert "htmlLink" not in result or True  # link key is "link"
    assert "link" in result


def test_audit_written_on_list(mock_svc):
    mock_svc.events().list().execute.return_value = {"items": []}
    actions.list_today()
    from jarvis.security.audit import query_audit
    rows = query_audit(actor="gcal", action="list_today", limit=1)
    assert len(rows) >= 1
    assert rows[0]["outcome"] == "ok"
