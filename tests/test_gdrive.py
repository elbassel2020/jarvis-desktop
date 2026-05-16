"""Google Drive tests — API mocked."""
import pytest
from unittest.mock import MagicMock, patch

from jarvis.integrations.gdrive import actions


@pytest.fixture
def mock_svc():
    svc = MagicMock()
    with patch("jarvis.integrations.gdrive.actions._service", return_value=svc):
        yield svc


def test_search_returns_files(mock_svc):
    mock_svc.files().list().execute.return_value = {
        "files": [
            {
                "id": "f1",
                "name": "Zamilfood Quote 2026",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-05-17",
                "webViewLink": "https://drive.google.com/file/d/f1",
            }
        ]
    }
    files = actions.search("Zamilfood")
    assert len(files) == 1
    assert "Zamilfood" in files[0]["name"]


def test_search_empty(mock_svc):
    mock_svc.files().list().execute.return_value = {"files": []}
    files = actions.search("nonexistent_xyz")
    assert files == []


def test_read_file_binary(mock_svc):
    mock_svc.files().get().execute.return_value = {
        "id": "f2",
        "name": "photo.jpg",
        "mimeType": "image/jpeg",
    }
    result = actions.read_file("f2")
    assert result["mimeType"] == "image/jpeg"
    assert "Binary file" in result["content"]


def test_audit_written_on_search(mock_svc):
    mock_svc.files().list().execute.return_value = {"files": []}
    actions.search("test query")
    from jarvis.security.audit import query_audit
    rows = query_audit(actor="gdrive", action="search", limit=1)
    assert len(rows) >= 1
    assert rows[0]["outcome"] == "ok"
