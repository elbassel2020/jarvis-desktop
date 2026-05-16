"""
MSMA Bridge Client — talks to the MSMA Bot bridge server.

Provides a typed async interface to MSMA Bot operations (quotes, invoices,
payments, customer data) via authenticated HTTP.

Authentication: HMAC-SHA256 per request.
  message = "{METHOD}\n{path}\n{sha256_hex(body)}\n{timestamp}\n{nonce}"
  signature = HMAC-SHA256(hmac_key, message)

If the HMAC key is not provisioned, the client operates in
"not configured" mode — all calls raise BridgeNotConfiguredError
rather than silently returning empty data.

Production bridge URL: http://localhost:9000 (bridge runs on same machine
as MSMA Bot — no internet egress required).
"""
import hashlib
import hmac
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from jarvis.security.audit import write_audit
from jarvis.security.credential_broker import broker
from jarvis.security.http_guard import safe_async_client

_logger = logging.getLogger("jarvis.bridges.msma_client")

_DEFAULT_BRIDGE_URL = "http://localhost:9000"


class BridgeNotConfiguredError(Exception):
    """Raised when HMAC key not provisioned in credential broker."""


class BridgeCallError(Exception):
    """Raised on non-2xx responses or network failures."""
    def __init__(self, path: str, status: int, body: str = ""):
        self.path = path
        self.status = status
        super().__init__(f"Bridge call failed: {path} → HTTP {status}: {body[:200]}")


class MsmaBridgeClient:
    """
    Async HTTP client for the MSMA Bot bridge server.

    Parameters
    ----------
    bridge_url:
        Base URL of the bridge server. Defaults to http://localhost:9000.
    hmac_key:
        Override HMAC key directly (for testing). If omitted, loaded via
        broker.resolve("cred://msma_bridge/hmac_key").
    """

    def __init__(
        self,
        bridge_url: str = _DEFAULT_BRIDGE_URL,
        hmac_key: Optional[str] = None,
    ):
        self.bridge_url = bridge_url.rstrip("/")
        self._configured = False
        self._hmac_key: bytes = b""

        if hmac_key is not None:
            self._hmac_key = hmac_key.encode() if isinstance(hmac_key, str) else hmac_key
            self._configured = True
        else:
            try:
                raw = broker.resolve("cred://msma_bridge/hmac_key")
                if raw:
                    self._hmac_key = raw.encode() if isinstance(raw, str) else raw
                    self._configured = True
                else:
                    _logger.info("MSMA bridge HMAC key empty — not configured mode")
            except Exception as exc:
                _logger.info(f"MSMA bridge HMAC key not provisioned: {exc}")

    # ── Signing ────────────────────────────────────────────────────────────

    def _sign(
        self,
        method: str,
        path: str,
        body_bytes: bytes,
        nonce: str,
        timestamp: int,
    ) -> str:
        """
        Compute HMAC-SHA256 signature.

        message = "{METHOD}\\n{path}\\n{sha256_hex(body)}\\n{timestamp}\\n{nonce}"
        """
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        message = f"{method.upper()}\n{path}\n{body_hash}\n{timestamp}\n{nonce}"
        sig = hmac.new(self._hmac_key, message.encode("utf-8"), hashlib.sha256)
        return sig.hexdigest()

    # ── HTTP transport ─────────────────────────────────────────────────────

    async def _call(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
    ) -> dict:
        """
        Execute an authenticated bridge call.

        Raises
        ------
        BridgeNotConfiguredError
            If HMAC key not provisioned.
        BridgeCallError
            On non-2xx HTTP response.
        """
        if not self._configured:
            raise BridgeNotConfiguredError(
                "MSMA bridge not configured — provision cred://msma_bridge/hmac_key"
            )

        timestamp = int(time.time())
        nonce = uuid.uuid4().hex
        body_bytes = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
        signature = self._sign(method, path, body_bytes, nonce, timestamp)
        url = f"{self.bridge_url}{path}"

        headers = {
            "Content-Type": "application/json",
            "X-MSMA-Timestamp": str(timestamp),
            "X-MSMA-Nonce": nonce,
            "X-MSMA-Signature": signature,
        }

        outcome = "ok"
        try:
            async with safe_async_client(timeout=30.0) as client:
                if method.upper() == "GET":
                    resp = await client.get(url, headers=headers)
                else:
                    resp = await client.post(url, content=body_bytes, headers=headers)

            if resp.status_code >= 400:
                outcome = f"http_{resp.status_code}"
                write_audit(
                    actor="msma_bridge",
                    action=path,
                    params=body,
                    outcome=outcome,
                    egress_host="localhost",
                )
                raise BridgeCallError(path, resp.status_code, resp.text)

            data = resp.json()
            write_audit(
                actor="msma_bridge",
                action=path,
                params={k: v for k, v in (body or {}).items() if k != "body"},
                outcome="ok",
                egress_host="localhost",
            )
            return data

        except BridgeCallError:
            raise
        except BridgeNotConfiguredError:
            raise
        except Exception as exc:
            outcome = f"error:{type(exc).__name__}"
            _logger.error(f"Bridge call {method} {path} failed: {exc}")
            write_audit(
                actor="msma_bridge",
                action=path,
                params=body,
                outcome=outcome,
                egress_host="localhost",
            )
            raise BridgeCallError(path, 0, str(exc)) from exc

    # ── Public endpoints ───────────────────────────────────────────────────

    async def health(self) -> dict:
        """GET /health — liveness check for the bridge server."""
        return await self._call("GET", "/health")

    async def create_quote(
        self,
        customer: str,
        items: list,
        notes: str = "",
    ) -> dict:
        """POST /quotes — create a new quote in MSMA Bot."""
        return await self._call("POST", "/quotes", {
            "customer": customer,
            "items": items,
            "notes": notes,
        })

    async def list_open_quotes(self, customer: Optional[str] = None) -> list:
        """GET /quotes/open — list open quotes, optionally filtered by customer."""
        path = "/quotes/open"
        if customer:
            path += f"?customer={customer}"
        result = await self._call("GET", path)
        return result if isinstance(result, list) else result.get("quotes", [])

    async def send_invoice(self, quote_id: str, customer_email: str) -> dict:
        """POST /invoices/send — generate and send invoice for a quote."""
        return await self._call("POST", "/invoices/send", {
            "quote_id": quote_id,
            "customer_email": customer_email,
        })

    async def log_payment(
        self,
        invoice_id: str,
        amount: float,
        method: str,
        ref: str,
    ) -> dict:
        """POST /payments — record a received payment."""
        return await self._call("POST", "/payments", {
            "invoice_id": invoice_id,
            "amount": amount,
            "method": method,
            "ref": ref,
        })

    async def customer_balance(self, customer: str) -> dict:
        """GET /customers/{customer}/balance — outstanding balance."""
        return await self._call("GET", f"/customers/{customer}/balance")

    async def send_email_via_zoho(
        self, to: str, subject: str, body: str
    ) -> dict:
        """POST /email/send — send email through MSMA Bot's Zoho account."""
        return await self._call("POST", "/email/send", {
            "to": to,
            "subject": subject,
            "body": body,
        })

    async def send_quote_to_customer(self, quote_id: str) -> dict:
        """POST /quotes/{quote_id}/send — email quote PDF to customer."""
        return await self._call("POST", f"/quotes/{quote_id}/send")
