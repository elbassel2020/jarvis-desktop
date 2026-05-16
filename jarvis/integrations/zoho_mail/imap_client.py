"""
Zoho IMAP client using imap-tools.
Reads credentials from Credential Broker.
"""
import logging
import time

from imap_tools import MailBox, A

from jarvis.security.credential_broker import broker
from jarvis.security.audit import write_audit

_logger = logging.getLogger("jarvis.zoho")

ZOHO_IMAP_SERVER = "imap.zoho.com"
ZOHO_IMAP_PORT = 993


def _credentials() -> tuple[str, str]:
    user = broker.resolve("cred://zoho_imap_user/lighting")
    pw = broker.resolve("cred://zoho_imap_password/lighting")
    return user, pw


def list_unread(limit: int = 10, folder: str = "INBOX") -> list[dict]:
    """Return list of unread emails, newest first."""
    t0 = time.monotonic()
    try:
        user, pw = _credentials()
        with MailBox(ZOHO_IMAP_SERVER, ZOHO_IMAP_PORT).login(
            user, pw, initial_folder=folder
        ) as mb:
            messages = list(
                mb.fetch(criteria=A(seen=False), limit=limit, reverse=True, mark_seen=False)
            )
            results = [
                {
                    "uid": m.uid,
                    "from": m.from_,
                    "subject": m.subject,
                    "date": str(m.date),
                    "snippet": (m.text or "")[:200],
                }
                for m in messages
            ]
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="zoho", action="list_unread",
                    params={"limit": limit, "folder": folder}, outcome="ok",
                    egress_host="imap.zoho.com",
                    duration_ms=duration_ms,
                    notes=f"{len(results)} unread")
        return results
    except Exception as e:
        write_audit(actor="zoho", action="list_unread", outcome="error",
                    notes=str(e)[:200])
        raise


def read_message(uid: str, folder: str = "INBOX") -> dict:
    """Fetch one message body by UID."""
    t0 = time.monotonic()
    try:
        user, pw = _credentials()
        with MailBox(ZOHO_IMAP_SERVER, ZOHO_IMAP_PORT).login(
            user, pw, initial_folder=folder
        ) as mb:
            messages = list(mb.fetch(A(uid=uid), mark_seen=False, limit=1))
            if not messages:
                return {}
            m = messages[0]
            result = {
                "uid": m.uid,
                "from": m.from_,
                "to": m.to,
                "subject": m.subject,
                "date": str(m.date),
                "body": (m.text or "")[:5000],
                "html_preview": (m.html or "")[:500],
            }
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="zoho", action="read", params={"uid": uid}, outcome="ok",
                    egress_host="imap.zoho.com", duration_ms=duration_ms)
        return result
    except Exception as e:
        write_audit(actor="zoho", action="read", params={"uid": uid}, outcome="error",
                    notes=str(e)[:200])
        raise


def search(query: str, folder: str = "INBOX", limit: int = 20) -> list[dict]:
    """Search emails by text content."""
    t0 = time.monotonic()
    try:
        user, pw = _credentials()
        with MailBox(ZOHO_IMAP_SERVER, ZOHO_IMAP_PORT).login(
            user, pw, initial_folder=folder
        ) as mb:
            messages = list(
                mb.fetch(A(text=query), limit=limit, reverse=True, mark_seen=False)
            )
            results = [
                {
                    "uid": m.uid,
                    "from": m.from_,
                    "subject": m.subject,
                    "date": str(m.date),
                }
                for m in messages
            ]
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="zoho", action="search",
                    params={"query": query[:100]}, outcome="ok",
                    egress_host="imap.zoho.com",
                    duration_ms=duration_ms,
                    notes=f"{len(results)} matches")
        return results
    except Exception as e:
        write_audit(actor="zoho", action="search", outcome="error",
                    notes=str(e)[:200])
        raise
