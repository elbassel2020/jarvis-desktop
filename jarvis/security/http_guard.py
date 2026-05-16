"""
HTTP Guard — outbound egress allowlist enforcement.

Wraps httpx + requests so any outbound HTTP call validates the destination
against safety/identity.yaml::allowed_third_parties. Catches both accidental
leaks and prompt-injection-driven exfiltration attempts.
"""
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

_logger = logging.getLogger("jarvis.security.http_guard")

IDENTITY_PATH = Path(__file__).parent.parent.parent / "safety" / "identity.yaml"
LOCALHOST_PATTERNS = [
    re.compile(r"^127\."),
    re.compile(r"^localhost$"),
    re.compile(r"^::1$"),
    re.compile(r"^0\.0\.0\.0$"),  # explicit allow for local testing
]


class EgressDeniedError(Exception):
    """Raised when an outbound HTTP call targets a non-allowlisted host."""
    def __init__(self, host: str, reason: str = "not in allowlist"):
        self.host = host
        self.reason = reason
        super().__init__(f"Egress denied to {host}: {reason}")


def _load_allowlist() -> list[str]:
    if not IDENTITY_PATH.exists():
        _logger.warning("identity.yaml missing; defaulting to deny-all")
        return []
    data = yaml.safe_load(IDENTITY_PATH.read_text(encoding="utf-8"))
    return data.get("allowed_third_parties", []) or []


def _is_allowed(host: str) -> bool:
    if not host:
        return False
    # Localhost always allowed
    for pat in LOCALHOST_PATTERNS:
        if pat.match(host):
            return True
    # Check allowlist (subdomain match)
    allowlist = _load_allowlist()
    for allowed in allowlist:
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def check_url(url: str) -> None:
    """Raise EgressDeniedError if URL not allowed."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not _is_allowed(host):
        _logger.warning(f"DENIED outbound={host} url={url}")
        raise EgressDeniedError(host)
    _logger.debug(f"ALLOWED outbound={host}")


class SafeAsyncClient(httpx.AsyncClient):
    """httpx.AsyncClient with egress allowlist enforcement."""

    async def send(self, request, **kwargs):
        check_url(str(request.url))
        return await super().send(request, **kwargs)


class SafeClient(httpx.Client):
    """httpx.Client with egress allowlist enforcement."""

    def send(self, request, **kwargs):
        check_url(str(request.url))
        return super().send(request, **kwargs)


# Convenience factories
def safe_async_client(**kwargs) -> SafeAsyncClient:
    return SafeAsyncClient(**kwargs)


def safe_client(**kwargs) -> SafeClient:
    return SafeClient(**kwargs)
