"""Zoho IMAP tests — imap-tools and credentials mocked."""
import pytest
from unittest.mock import MagicMock, patch

from jarvis.integrations.zoho_mail import imap_client


@pytest.fixture
def mock_mb():
    """Mock MailBox context manager and _credentials."""
    mb = MagicMock()
    mb_ctx = MagicMock()
    mb_ctx.__enter__.return_value = mb
    mb.fetch.return_value = []
    with patch("jarvis.integrations.zoho_mail.imap_client.MailBox") as MB:
        MB.return_value.login.return_value = mb_ctx
        with patch(
            "jarvis.integrations.zoho_mail.imap_client._credentials",
            return_value=("lighting@amscontrol.com", "fakepass"),
        ):
            yield mb


def _fake_msg(uid="1", from_="sender@example.com", subject="Test",
              date="2026-05-17", text="body text", html="<p>html</p>"):
    m = MagicMock()
    m.uid = uid
    m.from_ = from_
    m.to = "lighting@amscontrol.com"
    m.subject = subject
    m.date = date
    m.text = text
    m.html = html
    return m


def test_list_unread_returns_list(mock_mb):
    mock_mb.fetch.return_value = [_fake_msg()]
    result = imap_client.list_unread(limit=10)
    assert len(result) == 1
    assert result[0]["from"] == "sender@example.com"
    assert result[0]["snippet"] == "body text"


def test_list_unread_empty(mock_mb):
    mock_mb.fetch.return_value = []
    result = imap_client.list_unread()
    assert result == []


def test_read_message_returns_body(mock_mb):
    mock_mb.fetch.return_value = [_fake_msg(text="Full body content")]
    result = imap_client.read_message("1")
    assert result["body"] == "Full body content"
    assert result["uid"] == "1"


def test_search_returns_matches(mock_mb):
    mock_mb.fetch.return_value = [_fake_msg(subject="Zamilfood RFQ 2026")]
    result = imap_client.search("Zamilfood")
    assert len(result) == 1
    assert "Zamilfood" in result[0]["subject"]


def test_audit_written_on_list(mock_mb):
    mock_mb.fetch.return_value = []
    imap_client.list_unread()
    from jarvis.security.audit import query_audit
    rows = query_audit(actor="zoho", action="list_unread", limit=1)
    assert len(rows) >= 1
    assert rows[0]["outcome"] == "ok"
