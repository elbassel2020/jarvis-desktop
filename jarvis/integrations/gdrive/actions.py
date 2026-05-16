"""Google Drive read-only actions."""
import io
import logging
import time

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from jarvis.integrations.gmail.auth import get_credentials
from jarvis.security.audit import write_audit

_logger = logging.getLogger("jarvis.gdrive")


def _service():
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Google OAuth not set up. Run scripts/setup_gmail_oauth.py")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def search(query: str, limit: int = 10) -> list[dict]:
    """Search Drive for files matching query (name or full-text)."""
    t0 = time.monotonic()
    try:
        svc = _service()
        # Sanitize single quotes in query to avoid Drive API injection
        safe_q = query.replace("'", "\\'")
        q = f"name contains '{safe_q}' or fullText contains '{safe_q}'"
        resp = svc.files().list(
            q=q,
            pageSize=limit,
            fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        ).execute()
        files = resp.get("files", [])
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gdrive", action="search",
                    params={"query": query[:100]}, outcome="ok",
                    egress_host="www.googleapis.com",
                    duration_ms=duration_ms,
                    notes=f"{len(files)} files found")
        return files
    except Exception as e:
        write_audit(actor="gdrive", action="search", outcome="error",
                    notes=str(e)[:200])
        raise


def read_file(file_id: str) -> dict:
    """Read file content. Google Docs → export as plain text. Binary → metadata only."""
    t0 = time.monotonic()
    try:
        svc = _service()
        meta = svc.files().get(
            fileId=file_id, fields="id, name, mimeType"
        ).execute()
        mime = meta.get("mimeType", "")

        content = ""
        if mime == "application/vnd.google-apps.document":
            request = svc.files().export_media(fileId=file_id, mimeType="text/plain")
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            content = fh.getvalue().decode("utf-8", errors="ignore")[:8000]
        elif mime == "text/plain":
            request = svc.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            content = fh.getvalue().decode("utf-8", errors="ignore")[:8000]
        else:
            content = f"[Binary file: {mime} — open in Drive UI]"

        result = {
            "id": meta["id"],
            "name": meta["name"],
            "mimeType": mime,
            "content": content,
        }
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gdrive", action="read",
                    params={"file_id": file_id}, outcome="ok",
                    egress_host="www.googleapis.com",
                    duration_ms=duration_ms,
                    notes=meta.get("name", "unknown"))
        return result
    except Exception as e:
        write_audit(actor="gdrive", action="read", outcome="error",
                    notes=str(e)[:200])
        raise
