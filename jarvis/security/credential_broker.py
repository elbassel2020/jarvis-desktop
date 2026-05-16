"""
Credential Broker — single safe place for all secrets.

All secrets live in Windows Credential Manager (DPAPI-encrypted) via keyring.
LLM only ever sees opaque handles like 'cred://gmail/walid'.
Long tokens (>2.5KB) are wrapped with Fernet; the Fernet key lives in keyring,
the encrypted blob lives in data/secrets/<service>_<account>.enc.
"""
import keyring
import logging
import os
import re
from cryptography.fernet import Fernet
from pathlib import Path
from typing import Optional


NAMESPACE = "jarvis"
HANDLE_RE = re.compile(r"^cred://([a-z_]+)/([a-z0-9_-]+)$")
LONG_TOKEN_THRESHOLD = 2400  # Windows Credential Manager limit ~2560
SECRETS_DIR = Path(__file__).parent.parent.parent / "data" / "secrets"
SECRETS_DIR.mkdir(parents=True, exist_ok=True)

# Audit log for credential access (no secret values)
ACCESS_LOG = Path(__file__).parent.parent.parent / "logs" / "credential_access.log"
ACCESS_LOG.parent.mkdir(exist_ok=True)
_logger = logging.getLogger("jarvis.security.credential_broker")
_handler = logging.FileHandler(ACCESS_LOG, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


# Patterns that should never appear in logs (defense in depth)
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),     # OpenAI/Anthropic style
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),   # Google API
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),    # Groq
    re.compile(r"xai-[A-Za-z0-9]{20,}"),    # xAI
    re.compile(r"[A-Za-z0-9]{32,}"),        # Generic long alphanumeric
]


class CredentialBrokerError(Exception):
    pass


class CredentialBroker:
    """Single point of access for all secrets in Jarvis."""

    def __init__(self):
        self.namespace = NAMESPACE

    def _key(self, service: str, account: str) -> str:
        return f"{self.namespace}/{service}/{account}"

    def _validate_handle(self, handle: str) -> tuple[str, str]:
        m = HANDLE_RE.match(handle)
        if not m:
            raise CredentialBrokerError(f"Invalid handle format: {handle}")
        return m.group(1), m.group(2)

    def get_handle(self, service: str, account: str) -> str:
        """Return opaque handle for LLM to reference."""
        return f"cred://{service}/{account}"

    def store(self, service: str, account: str, secret: str) -> str:
        """Store a secret, return its handle. Handles long tokens via Fernet."""
        key = self._key(service, account)

        if len(secret.encode("utf-8")) < LONG_TOKEN_THRESHOLD:
            # Fits in Credential Manager directly
            keyring.set_password(self.namespace, f"{service}/{account}", secret)
            _logger.info(f"STORE_DIRECT service={service} account={account} bytes={len(secret)}")
        else:
            # Encrypt with Fernet, store key in keyring, ciphertext on disk
            fernet_key = Fernet.generate_key()
            ciphertext = Fernet(fernet_key).encrypt(secret.encode("utf-8"))
            blob_path = SECRETS_DIR / f"{service}_{account}.enc"
            blob_path.write_bytes(ciphertext)
            keyring.set_password(self.namespace, f"{service}/{account}:fernet_key", fernet_key.decode())
            _logger.info(f"STORE_WRAPPED service={service} account={account} bytes={len(secret)}")

        return self.get_handle(service, account)

    def resolve(self, handle: str) -> str:
        """Resolve handle to actual secret value. Only call at action-execution time."""
        service, account = self._validate_handle(handle)

        # Try direct first
        direct = keyring.get_password(self.namespace, f"{service}/{account}")
        if direct is not None:
            _logger.info(f"RESOLVE_DIRECT service={service} account={account}")
            return direct

        # Fall back to wrapped
        fernet_key_str = keyring.get_password(self.namespace, f"{service}/{account}:fernet_key")
        if fernet_key_str is None:
            _logger.warning(f"RESOLVE_MISSING service={service} account={account}")
            raise CredentialBrokerError(f"No credential for {service}/{account}")

        blob_path = SECRETS_DIR / f"{service}_{account}.enc"
        if not blob_path.exists():
            raise CredentialBrokerError(f"Encrypted blob missing for {service}/{account}")

        ciphertext = blob_path.read_bytes()
        plaintext = Fernet(fernet_key_str.encode()).decrypt(ciphertext).decode("utf-8")
        _logger.info(f"RESOLVE_WRAPPED service={service} account={account}")
        return plaintext

    def delete(self, service: str, account: str) -> bool:
        """Remove a credential entirely."""
        deleted = False
        try:
            keyring.delete_password(self.namespace, f"{service}/{account}")
            deleted = True
        except keyring.errors.PasswordDeleteError:
            pass

        try:
            keyring.delete_password(self.namespace, f"{service}/{account}:fernet_key")
            deleted = True
        except keyring.errors.PasswordDeleteError:
            pass

        blob_path = SECRETS_DIR / f"{service}_{account}.enc"
        if blob_path.exists():
            blob_path.unlink()
            deleted = True

        _logger.info(f"DELETE service={service} account={account} success={deleted}")
        return deleted

    def list_handles(self) -> list[str]:
        """List all known credential handles (for diagnostics, not values)."""
        # keyring doesn't expose enumeration on Windows; track manually
        manifest_path = SECRETS_DIR / "manifest.txt"
        if not manifest_path.exists():
            return []
        return [l.strip() for l in manifest_path.read_text().splitlines() if l.strip()]


# Singleton
broker = CredentialBroker()


def redact_secrets_in_text(text: str) -> str:
    """Best-effort redaction for log messages. Defense in depth."""
    if not text:
        return text
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
