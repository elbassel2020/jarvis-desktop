"""
MSMA Bridge Client tests — 12 tests, all HTTP mocked.

1.  test_client_init_without_key_graceful
2.  test_signing_deterministic
3.  test_signing_different_nonces_produce_different_sigs
4.  test_create_quote_mocked
5.  test_list_open_quotes_mocked
6.  test_send_invoice_mocked
7.  test_log_payment_mocked
8.  test_customer_balance_mocked
9.  test_send_email_mocked
10. test_health_check_mocked
11. test_audit_log_written_on_call
12. test_handles_non_2xx_gracefully
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from jarvis.bridges.msma_client import (
    MsmaBridgeClient,
    BridgeNotConfiguredError,
    BridgeCallError,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

_TEST_KEY = "test-hmac-key-32-bytes-xxxxxxxxx"


def _make_client() -> MsmaBridgeClient:
    """Client with known key — no broker call needed."""
    return MsmaBridgeClient(bridge_url="http://localhost:9000", hmac_key=_TEST_KEY)


def _mock_http_200(payload: dict):
    """Patch SafeAsyncClient to return a 200 with JSON payload."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.text = ""

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get  = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)

    return patch("jarvis.bridges.msma_client.safe_async_client", return_value=mock_client), mock_client


def _mock_http_error(status: int):
    """Patch SafeAsyncClient to return an error status."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = {"error": "server error"}
    mock_resp.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get  = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)

    return patch("jarvis.bridges.msma_client.safe_async_client", return_value=mock_client)


# ── 1. Init without key ────────────────────────────────────────────────────

def test_client_init_without_key_graceful():
    """Client with no key must be in not-configured mode, not crash."""
    with patch("jarvis.bridges.msma_client.broker.resolve",
               side_effect=Exception("key not found")):
        client = MsmaBridgeClient()

    assert client._configured is False


# ── 2. Signing deterministic ───────────────────────────────────────────────

def test_signing_deterministic():
    """Same inputs → same signature every time."""
    client = _make_client()
    sig1 = client._sign("POST", "/quotes", b'{"x":1}', "nonce123", 1700000000)
    sig2 = client._sign("POST", "/quotes", b'{"x":1}', "nonce123", 1700000000)
    assert sig1 == sig2
    assert len(sig1) == 64   # SHA-256 hex = 64 chars


# ── 3. Different nonces → different sigs ──────────────────────────────────

def test_signing_different_nonces_produce_different_sigs():
    client = _make_client()
    sig1 = client._sign("POST", "/quotes", b"{}", "nonce-aaa", 1700000000)
    sig2 = client._sign("POST", "/quotes", b"{}", "nonce-bbb", 1700000000)
    assert sig1 != sig2


# ── 4. create_quote ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_quote_mocked():
    client = _make_client()
    expected = {"quote_id": "Q-2026-001", "status": "draft"}
    ctx, mock_client = _mock_http_200(expected)
    with ctx, patch("jarvis.bridges.msma_client.write_audit"):
        result = await client.create_quote(
            customer="Zamilfood",
            items=[{"sku": "CB-16A", "qty": 10, "unit_price": 45.0}],
            notes="Urgent",
        )
    assert result["quote_id"] == "Q-2026-001"
    mock_client.post.assert_called_once()
    # Verify HMAC headers sent
    call_kwargs = mock_client.post.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert "X-MSMA-Signature" in headers
    assert "X-MSMA-Timestamp" in headers
    assert "X-MSMA-Nonce" in headers


# ── 5. list_open_quotes ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_open_quotes_mocked():
    client = _make_client()
    expected = [{"quote_id": "Q-001"}, {"quote_id": "Q-002"}]
    ctx, _ = _mock_http_200(expected)
    with ctx, patch("jarvis.bridges.msma_client.write_audit"):
        result = await client.list_open_quotes(customer="Zamilfood")
    assert isinstance(result, list)
    assert len(result) == 2


# ── 6. send_invoice ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_invoice_mocked():
    client = _make_client()
    expected = {"invoice_id": "INV-2026-042", "sent": True}
    ctx, _ = _mock_http_200(expected)
    with ctx, patch("jarvis.bridges.msma_client.write_audit"):
        result = await client.send_invoice("Q-2026-001", "ceo@zamilfood.com")
    assert result["sent"] is True


# ── 7. log_payment ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_payment_mocked():
    client = _make_client()
    expected = {"payment_id": "PAY-999", "recorded": True}
    ctx, _ = _mock_http_200(expected)
    with ctx, patch("jarvis.bridges.msma_client.write_audit"):
        result = await client.log_payment(
            invoice_id="INV-2026-042",
            amount=15000.0,
            method="bank_transfer",
            ref="TXN-ABC123",
        )
    assert result["recorded"] is True


# ── 8. customer_balance ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_customer_balance_mocked():
    client = _make_client()
    expected = {"customer": "Zamilfood", "outstanding_sar": 45000.0}
    ctx, _ = _mock_http_200(expected)
    with ctx, patch("jarvis.bridges.msma_client.write_audit"):
        result = await client.customer_balance("Zamilfood")
    assert result["outstanding_sar"] == 45000.0


# ── 9. send_email ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_email_mocked():
    client = _make_client()
    expected = {"message_id": "MID-123", "sent": True}
    ctx, _ = _mock_http_200(expected)
    with ctx, patch("jarvis.bridges.msma_client.write_audit"):
        result = await client.send_email_via_zoho(
            to="ceo@zamilfood.com",
            subject="Quote Follow-up",
            body="Dear Sir, please find attached...",
        )
    assert result["sent"] is True


# ── 10. health check ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_mocked():
    client = _make_client()
    expected = {"status": "ok", "version": "1.0.0"}
    ctx, mock_client = _mock_http_200(expected)
    with ctx, patch("jarvis.bridges.msma_client.write_audit"):
        result = await client.health()
    assert result["status"] == "ok"
    mock_client.get.assert_called_once()


# ── 11. audit written on call ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_log_written_on_call():
    client = _make_client()
    ctx, _ = _mock_http_200({"status": "ok"})
    with ctx, patch("jarvis.bridges.msma_client.write_audit") as mock_audit:
        await client.health()
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["actor"] == "msma_bridge"
    assert call_kwargs["outcome"] == "ok"


# ── 12. non-2xx raises BridgeCallError ────────────────────────────────────

@pytest.mark.asyncio
async def test_handles_non_2xx_gracefully():
    """503 from bridge server raises BridgeCallError, audit records http_503."""
    client = _make_client()
    err_ctx = _mock_http_error(503)
    with err_ctx, patch("jarvis.bridges.msma_client.write_audit") as mock_audit:
        with pytest.raises(BridgeCallError) as exc_info:
            await client.health()

    assert exc_info.value.status == 503
    # Audit should record the error
    mock_audit.assert_called_once()
    assert "503" in mock_audit.call_args.kwargs["outcome"]
