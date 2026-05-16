"""
Mock MSMA Bridge Server — local testing only.

Implements the same 7 endpoints as the real bridge.
Validates HMAC-SHA256 signatures. Returns realistic mock data.

Usage::
    python scripts/mock_msma_bridge.py           # runs on port 9000
    python scripts/mock_msma_bridge.py --port 9001

Programmatic (in tests)::
    from scripts.mock_msma_bridge import start_mock_server, stop_mock_server
    server = start_mock_server(port=9001, hmac_key="test-key")
    # ... run tests ...
    stop_mock_server(server)
"""
import argparse
import hashlib
import hmac
import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
_logger = logging.getLogger("mock_msma_bridge")

# ── Default test key ───────────────────────────────────────────────────────
DEFAULT_HMAC_KEY = "test-hmac-key-32-bytes-xxxxxxxxx"

# Shared state for mock: overridable per test
_HMAC_KEY: str = DEFAULT_HMAC_KEY

# ── Mock data ──────────────────────────────────────────────────────────────
_QUOTES: dict = {}
_PAYMENTS: list = []


def _verify_hmac(method: str, path: str, body: bytes, headers: dict) -> bool:
    """Verify HMAC-SHA256 signature from request headers."""
    timestamp = headers.get("X-MSMA-Timestamp", headers.get("x-msma-timestamp", ""))
    nonce     = headers.get("X-MSMA-Nonce",     headers.get("x-msma-nonce",     ""))
    signature = headers.get("X-MSMA-Signature", headers.get("x-msma-signature", ""))

    if not all([timestamp, nonce, signature]):
        return False

    body_hash = hashlib.sha256(body).hexdigest()
    # Strip query string from path for signing
    path_no_qs = urlparse(path).path
    message = f"{method.upper()}\n{path_no_qs}\n{body_hash}\n{timestamp}\n{nonce}"
    expected = hmac.new(
        _HMAC_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


class MockBridgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for mock MSMA bridge."""

    def log_message(self, fmt, *args):
        _logger.info(fmt % args)

    def _send_json(self, status: int, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length > 0 else b"{}"

    def _get_headers(self) -> dict:
        return {k: v for k, v in self.headers.items()}

    def _check_auth(self, body: bytes) -> bool:
        return _verify_hmac(
            self.command, self.path, body, self._get_headers()
        )

    # ── Routing ───────────────────────────────────────────────────────────

    def do_GET(self):
        body = b"{}"
        if not self._check_auth(body):
            self._send_json(401, {"error": "invalid signature"})
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json(200, {"status": "ok", "version": "mock-1.0"})
        elif path == "/quotes/open":
            qs = parse_qs(parsed.query)
            customer = qs.get("customer", [None])[0]
            quotes = list(_QUOTES.values())
            if customer:
                quotes = [q for q in quotes if q.get("customer") == customer]
            self._send_json(200, quotes)
        elif path.startswith("/customers/") and path.endswith("/balance"):
            customer = path.split("/")[2]
            self._send_json(200, {
                "customer": customer,
                "outstanding_sar": 45000.0,
                "currency": "SAR",
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_body()
        if not self._check_auth(body):
            self._send_json(401, {"error": "invalid signature"})
            return

        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}

        if path == "/quotes":
            quote_id = f"Q-MOCK-{len(_QUOTES) + 1:03d}"
            _QUOTES[quote_id] = {
                "quote_id": quote_id,
                "customer": payload.get("customer", "?"),
                "items": payload.get("items", []),
                "notes": payload.get("notes", ""),
                "status": "draft",
            }
            self._send_json(201, _QUOTES[quote_id])

        elif path == "/invoices/send":
            quote_id = payload.get("quote_id", "?")
            self._send_json(200, {
                "invoice_id": f"INV-MOCK-{quote_id}",
                "quote_id": quote_id,
                "sent": True,
                "email": payload.get("customer_email"),
            })

        elif path == "/payments":
            _PAYMENTS.append(payload)
            self._send_json(200, {
                "payment_id": f"PAY-MOCK-{len(_PAYMENTS):03d}",
                "recorded": True,
                "amount": payload.get("amount"),
            })

        elif path == "/email/send":
            self._send_json(200, {
                "message_id": "MID-MOCK-001",
                "sent": True,
                "to": payload.get("to"),
            })

        elif path.startswith("/quotes/") and path.endswith("/send"):
            quote_id = path.split("/")[2]
            self._send_json(200, {
                "quote_id": quote_id,
                "sent_to_customer": True,
            })

        else:
            self._send_json(404, {"error": "not found"})


# ── Server lifecycle ───────────────────────────────────────────────────────

def start_mock_server(port: int = 9001, hmac_key: str = DEFAULT_HMAC_KEY) -> HTTPServer:
    """Start mock server in a daemon thread. Returns the server instance."""
    global _HMAC_KEY, _QUOTES, _PAYMENTS
    _HMAC_KEY = hmac_key
    _QUOTES = {}
    _PAYMENTS = []

    server = HTTPServer(("127.0.0.1", port), MockBridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _logger.info(f"Mock MSMA bridge started on port {port}")
    return server


def stop_mock_server(server: HTTPServer):
    """Shut down the mock server."""
    server.shutdown()
    _logger.info("Mock MSMA bridge stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock MSMA bridge server")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--key", default=DEFAULT_HMAC_KEY)
    args = parser.parse_args()

    print(f"Starting mock MSMA bridge on port {args.port} (Ctrl+C to stop)")
    srv = start_mock_server(port=args.port, hmac_key=args.key)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop_mock_server(srv)
        print("Stopped.")
