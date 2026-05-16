"""Gmail action tests — all Google API calls mocked."""
import base64
import pytest
from unittest.mock import MagicMock, patch

from jarvis.integrations.gmail import actions


@pytest.fixture
def mock_svc():
    svc = MagicMock()
    with patch("jarvis.integrations.gmail.actions._service", return_value=svc):
        yield svc


def test_list_unread_returns_list(mock_svc):
    mock_svc.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg1"}, {"id": "msg2"}]
    }
    mock_svc.users().messages().get().execute.side_effect = [
        {
            "payload": {"headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "Subject", "value": "Hello"},
                {"name": "Date", "value": "2026-05-17"},
            ]},
            "snippet": "Snippet 1",
        },
        {
            "payload": {"headers": [
                {"name": "From", "value": "bob@example.com"},
                {"name": "Subject", "value": "World"},
                {"name": "Date", "value": "2026-05-17"},
            ]},
            "snippet": "Snippet 2",
        },
    ]
    results = actions.email_list_unread(limit=10)
    assert len(results) == 2
    assert results[0]["from"] == "alice@example.com"
    assert results[0]["subject"] == "Hello"


def test_list_unread_empty(mock_svc):
    mock_svc.users().messages().list().execute.return_value = {"messages": []}
    results = actions.email_list_unread()
    assert results == []


def test_email_read_extracts_body(mock_svc):
    body_text = "Hello world body"
    body_b64 = base64.urlsafe_b64encode(body_text.encode()).decode()
    mock_svc.users().messages().get().execute.return_value = {
        "id": "msg1",
        "threadId": "thread1",
        "payload": {
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "Subject", "value": "Test"},
                {"name": "To", "value": "me@example.com"},
            ],
            "parts": [{"mimeType": "text/plain", "body": {"data": body_b64}}],
        },
    }
    result = actions.email_read("msg1")
    assert result["body"] == body_text
    assert result["thread_id"] == "thread1"
    assert result["from"] == "alice@example.com"


def test_email_draft_creates_draft(mock_svc):
    mock_svc.users().drafts().create().execute.return_value = {
        "id": "draft123",
        "message": {"id": "msg123"},
    }
    result = actions.email_draft(to="bob@example.com", subject="Hi", body="Hello")
    assert result["draft_id"] == "draft123"
    assert result["message_id"] == "msg123"


def test_email_send_draft(mock_svc):
    mock_svc.users().drafts().send().execute.return_value = {"id": "msg456"}
    result = actions.email_send_draft("draft123")
    assert result["sent"] is True
    assert result["message_id"] == "msg456"


def test_audit_written_on_list(mock_svc):
    mock_svc.users().messages().list().execute.return_value = {"messages": []}
    actions.email_list_unread(limit=3)
    from jarvis.security.audit import query_audit
    rows = query_audit(actor="gmail", action="list_unread", limit=1)
    assert len(rows) >= 1
    assert rows[0]["outcome"] == "ok"
