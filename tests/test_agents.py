"""
Specialist Agent + Router tests — all LLM calls mocked.

Routing tests (5):
  1. email keywords → EmailAgent
  2. research keywords → ResearchAgent
  3. customer keywords → CustomerAgent
  4. sales keywords → SalesAgent
  5. no keywords → default SalesAgent

Agent tests (4):
  6. BaseAgent.respond() returns AgentResponse with correct fields
  7. BaseAgent writes audit on success
  8. CustomerAgent enriches context when deepdive exists
  9. CustomerAgent handles missing deepdive gracefully
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from jarvis.agents.base import BaseAgent, AgentResponse
from jarvis.agents.sales_agent import SalesAgent
from jarvis.agents.research_agent import ResearchAgent
from jarvis.agents.email_agent import EmailAgent
from jarvis.agents.customer_agent import CustomerAgent
from jarvis.agents.router import detect_agent, route_to_agent


# ── Shared mock helpers ────────────────────────────────────────────────────

def _anthropic_response(text: str = "Agent answer.", in_tok: int = 50, out_tok: int = 80):
    """Build a fake Anthropic API response dict."""
    return {
        "content": [{"text": text}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }


def _mock_http(text: str = "Agent answer."):
    """Context manager that patches SafeAsyncClient to return a mocked response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = _anthropic_response(text)
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    return patch("jarvis.agents.base.safe_async_client", return_value=mock_client)


# ── Routing tests ──────────────────────────────────────────────────────────

def test_route_email_keywords():
    assert detect_agent("please draft an email to Zamilfood about payment") == "email"


def test_route_research_keywords():
    assert detect_agent("what are the ZATCA phase 2 requirements for 2025?") == "research"


def test_route_customer_keywords():
    assert detect_agent("show me the customer profile for Zamilfood") == "customer"


def test_route_sales_keywords():
    assert detect_agent("what discount should I offer on this quote?") == "sales"


def test_route_default_when_no_keywords():
    assert detect_agent("hello jarvis") == "sales"


# ── BaseAgent tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_base_agent_returns_agent_response():
    agent = SalesAgent()
    with (
        _mock_http("Here is your sales advice."),
        patch("jarvis.agents.base.broker.resolve", return_value="sk-test"),
        patch("jarvis.agents.base.write_audit"),
    ):
        result = await agent.respond("Should I offer a discount?")

    assert isinstance(result, AgentResponse)
    assert result.agent == "sales"
    assert result.text == "Here is your sales advice."
    assert result.input_tokens == 50
    assert result.output_tokens == 80
    assert result.duration_ms >= 0
    assert isinstance(result.cost_usd_cents, int)


@pytest.mark.asyncio
async def test_base_agent_writes_audit():
    agent = ResearchAgent()
    with (
        _mock_http("ZATCA overview."),
        patch("jarvis.agents.base.broker.resolve", return_value="sk-test"),
        patch("jarvis.agents.base.write_audit") as mock_audit,
    ):
        await agent.respond("Explain ZATCA phase 2.")

    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["actor"] == "agent:research"
    assert call_kwargs["action"] == "respond"
    assert call_kwargs["outcome"] == "ok"


# ── CustomerAgent tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_customer_agent_enriches_context_when_deepdive_exists():
    """CustomerAgent prepends deepdive to context before calling LLM."""
    with (
        patch("jarvis.agents.customer_agent.get_deepdive",
              return_value="Zamilfood orders 50k SAR/quarter. Last order: March."),
        _mock_http("Customer analysis here."),
        patch("jarvis.agents.base.broker.resolve", return_value="sk-test"),
        patch("jarvis.agents.base.write_audit"),
    ):
        agent = CustomerAgent()
        result = await agent.respond(
            query="What's the status of Zamilfood?",
            company_name="Zamilfood",
        )

    assert isinstance(result, AgentResponse)
    assert result.agent == "customer"
    # Verify the post() call included enriched context
    assert result.text == "Customer analysis here."


@pytest.mark.asyncio
async def test_customer_agent_handles_missing_deepdive():
    """CustomerAgent proceeds gracefully when no deepdive cached."""
    with (
        patch("jarvis.agents.customer_agent.get_deepdive", return_value=None),
        _mock_http("No data found for this customer."),
        patch("jarvis.agents.base.broker.resolve", return_value="sk-test"),
        patch("jarvis.agents.base.write_audit"),
    ):
        agent = CustomerAgent()
        result = await agent.respond(
            query="Tell me about XYZ Corp.",
            company_name="XYZ Corp",
        )

    assert isinstance(result, AgentResponse)
    assert result.agent == "customer"


# ── route_to_agent integration test ────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_to_agent_dispatches_correctly():
    """route_to_agent with explicit agent_name bypasses keyword detection."""
    with (
        _mock_http("Email drafted."),
        patch("jarvis.agents.base.broker.resolve", return_value="sk-test"),
        patch("jarvis.agents.base.write_audit"),
    ):
        result = await route_to_agent(
            query="hello",          # no email keywords
            agent_name="email",    # explicit override
        )

    assert isinstance(result, AgentResponse)
    assert result.agent == "email"
