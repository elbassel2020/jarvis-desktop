"""Gmail actions: list_unread, read, draft, send_draft."""
import base64
import logging
import time
from email.mime.text import MIMEText
from typing import Optional

from googleapiclient.discovery import build

from jarvis.integrations.gmail.auth import get_credentials
from jarvis.security.audit import write_audit

_logger = logging.getLogger("jarvis.gmail")


def _service():
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Gmail not set up. Run scripts/setup_gmail_oauth.py")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def email_list_unread(limit: int = 10) -> list[dict]:
    """List unread messages. Returns metadata only — no body."""
    t0 = time.monotonic()
    try:
        svc = _service()
        resp = svc.users().messages().list(
            userId="me", q="is:unread", maxResults=limit
        ).execute()
        msg_ids = [m["id"] for m in resp.get("messages", [])]

        results = []
        for mid in msg_ids:
            msg = svc.users().messages().get(
                userId="me", id=mid, format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
            headers = {h["name"]: h["value"]
                       for h in msg.get("payload", {}).get("headers", [])}
            results.append({
                "id": mid,
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", "")[:200],
            })

        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gmail", action="list_unread",
                    params={"limit": limit}, outcome="ok",
                    egress_host="gmail.googleapis.com",
                    duration_ms=duration_ms,
                    notes=f"{len(results)} messages")
        return results

    except Exception as e:
        write_audit(actor="gmail", action="list_unread",
                    params={"limit": limit}, outcome="error",
                    notes=str(e)[:200])
        raise


def email_read(message_id: str) -> dict:
    """Read full message body (plain text, capped at 5000 chars)."""
    t0 = time.monotonic()
    try:
        svc = _service()
        msg = svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = {h["name"]: h["value"]
                   for h in msg.get("payload", {}).get("headers", [])}

        body = ""
        payload = msg.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break
        elif payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="ignore")

        result = {
            "id": message_id,
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body[:5000],
            "thread_id": msg.get("threadId"),
        }
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gmail", action="read",
                    params={"message_id": message_id}, outcome="ok",
                    egress_host="gmail.googleapis.com",
                    duration_ms=duration_ms)
        return result

    except Exception as e:
        write_audit(actor="gmail", action="read",
                    params={"message_id": message_id}, outcome="error",
                    notes=str(e)[:200])
        raise


def email_draft(to: str, subject: str, body: str,
                in_reply_to: Optional[str] = None,
                thread_id: Optional[str] = None) -> dict:
    """Create draft in Drafts folder. Does NOT send."""
    t0 = time.monotonic()
    try:
        svc = _service()
        message = MIMEText(body, "plain", "utf-8")
        message["To"] = to
        message["Subject"] = subject
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        draft_body: dict = {"message": {"raw": raw}}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id

        draft = svc.users().drafts().create(userId="me", body=draft_body).execute()

        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gmail", action="draft",
                    params={"to": to, "subject": subject[:100]}, outcome="ok",
                    egress_host="gmail.googleapis.com",
                    duration_ms=duration_ms,
                    notes=f"draft_id={draft.get('id')}")
        return {
            "draft_id": draft.get("id"),
            "message_id": draft.get("message", {}).get("id"),
        }

    except Exception as e:
        write_audit(actor="gmail", action="draft",
                    params={"to": to, "subject": subject[:100]}, outcome="error",
                    notes=str(e)[:200])
        raise


def email_send_draft(draft_id: str) -> dict:
    """Send a previously-created draft. Requires explicit confirmation upstream."""
    t0 = time.monotonic()
    try:
        svc = _service()
        sent = svc.users().drafts().send(
            userId="me", body={"id": draft_id}
        ).execute()
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="gmail", action="send_draft",
                    params={"draft_id": draft_id}, outcome="ok",
                    egress_host="gmail.googleapis.com",
                    duration_ms=duration_ms,
                    notes=f"message_id={sent.get('id')}")
        return {"sent": True, "message_id": sent.get("id")}

    except Exception as e:
        write_audit(actor="gmail", action="send_draft",
                    params={"draft_id": draft_id}, outcome="error",
                    notes=str(e)[:200])
        raise
