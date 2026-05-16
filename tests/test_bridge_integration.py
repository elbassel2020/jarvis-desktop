"""
Bridge integration tests — real HTTP against mock server.

Fixture starts mock server on random port, creates client pointed at it.
All four tests run real HMAC signing and real HTTP.

Tests:
1. test_client_against_mock_server_create_quote
2. test_client_against_mock_server_handles_wrong_hmac
3. test_client_against_mock_server_list_quotes
4. test_full_workflow_quote_to_payment
"""
import sys
import time
import socket
import pytest
from pathlib import Path

# Make sure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.mock_msma_bridge import start_mock_server, stop_mock_server, DEFAULT_HMAC_KEY

from jarvis.bridges.msma_client import MsmaBridgeClient, BridgeCallError


# ── Fixtures ───────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Find a free TCP port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def bridge():
    """Start mock server, yield (client, server), stop server after test."""
    port = _free_port()
    server = start_mock_server(port=port, hmac_key=DEFAULT_HMAC_KEY)
    time.sleep(0.05)   # brief startup pause
    client = MsmaBridgeClient(
        bridge_url=f"http://127.0.0.1:{port}",
        hmac_key=DEFAULT_HMAC_KEY,
    )
    yield client, server
    stop_mock_server(server)


# ── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_client_against_mock_server_create_quote(bridge):
    """Create quote against mock; verify returned quote_id and status."""
    client, _ = bridge
    result = await client.create_quote(
        customer="Zamilfood",
        items=[{"sku": "CB-16A", "qty": 5, "unit_price": 45.0}],
        notes="Integration test",
    )
    assert "quote_id" in result
    assert result["quote_id"].startswith("Q-MOCK-")
    assert result["status"] == "draft"
    assert result["customer"] == "Zamilfood"


@pytest.mark.asyncio
async def test_client_against_mock_server_handles_wrong_hmac(bridge):
    """Client with wrong HMAC key gets 401 → BridgeCallError."""
    _, server = bridge
    # Get the port from the server address
    port = server.server_address[1]
    bad_client = MsmaBridgeClient(
        bridge_url=f"http://127.0.0.1:{port}",
        hmac_key="wrong-key-completely-different",
    )
    with pytest.raises(BridgeCallError) as exc_info:
        await bad_client.health()
    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_client_against_mock_server_list_quotes(bridge):
    """Create 2 quotes then list_open_quotes; expect both returned."""
    client, _ = bridge
    await client.create_quote("Alpha Corp", [{"sku": "X1", "qty": 1}])
    await client.create_quote("Beta Ltd",  [{"sku": "X2", "qty": 2}])
    quotes = await client.list_open_quotes()
    assert len(quotes) >= 2
    customers = [q["customer"] for q in quotes]
    assert "Alpha Corp" in customers
    assert "Beta Ltd"   in customers


@pytest.mark.asyncio
async def test_full_workflow_quote_to_payment(bridge):
    """Full lifecycle: create quote → send invoice → log payment."""
    client, _ = bridge

    # Step 1: create quote
    quote = await client.create_quote(
        customer="Zamilfood",
        items=[{"sku": "MCB-32A", "qty": 20, "unit_price": 120.0}],
        notes="Monthly order",
    )
    quote_id = quote["quote_id"]
    assert quote_id

    # Step 2: send invoice
    invoice = await client.send_invoice(quote_id, "finance@zamilfood.com")
    assert invoice["sent"] is True
    invoice_id = invoice["invoice_id"]

    # Step 3: log payment
    payment = await client.log_payment(
        invoice_id=invoice_id,
        amount=2400.0,
        method="bank_transfer",
        ref="TXN-TEST-001",
    )
    assert payment["recorded"] is True
    assert payment["amount"] == 2400.0
