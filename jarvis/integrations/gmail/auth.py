"""
Gmail OAuth — Installed App flow.
Reads client_secret.json (one-time download from Google Cloud Console).
Stores refresh token via Credential Broker.
"""
import json
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from jarvis.security.credential_broker import broker

# Single OAuth flow covers Gmail + Calendar + Drive
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]

CLIENT_SECRET_PATH = Path("config/google_client_secret.json")


def get_credentials(account: str = "walid") -> Optional[Credentials]:
    """Get valid credentials, refreshing if needed. Returns None if not set up."""
    try:
        refresh_token = broker.resolve(f"cred://gmail_refresh/{account}")
    except Exception:
        return None

    if not CLIENT_SECRET_PATH.exists():
        return None

    client_config = json.loads(CLIENT_SECRET_PATH.read_text())
    installed = client_config.get("installed", client_config.get("web", {}))

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=installed["client_id"],
        client_secret=installed["client_secret"],
        scopes=SCOPES,
    )

    if not creds.valid:
        creds.refresh(Request())

    return creds


def setup_interactive(account: str = "walid") -> bool:
    """One-time interactive OAuth flow. Returns True on success."""
    if not CLIENT_SECRET_PATH.exists():
        print(f"ERROR: {CLIENT_SECRET_PATH} not found.")
        print("See docs/SPRINT_B_SETUP.md for setup instructions.")
        return False

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    broker.store("gmail_refresh", account, creds.refresh_token)
    print(f"OAuth complete. Token stored as cred://gmail_refresh/{account}")
    return True
