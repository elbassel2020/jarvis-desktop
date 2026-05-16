"""
Voice wiring tests — all intelligence calls mocked.

Tests:
1. test_council_action_routes_to_intelligence
2. test_brief_action_returns_cached_or_generates
3. test_ask_agent_routes_to_specialist
4. test_health_action_returns_status
5. test_plan_action_returns_plan
"""
import sys
from unittest.mock import MagicMock

# Stub heavy optional deps before importing safe_actions
for _mod in ("pygame", "pygame.mixer", "edge_tts"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from unittest.mock import patch, AsyncMock

from actions.safe_actions import SafeActions


def _make_actions() -> SafeActions:
    a = SafeActions()
    a.speak = MagicMock()      # suppress TTS
    return a


# ── Test 1: council voice command ──────────────────────────────────────────

def test_council_action_routes_to_intelligence():
    from jarvis.intelligence.council import CouncilResult
    mock_result = CouncilResult(
        decision="Yes, offer the 5% discount.",
        confidence=0.85,
        voices={},
        synthesis="",
        cost_usd_cents=3,
        duration_ms=1500,
    )
    actions = _make_actions()
    with patch("jarvis.intelligence.council.council_decide",
               new=AsyncMock(return_value=mock_result)):
        result = actions.council_action(transcript="Should I offer a 5% discount to Zamilfood?")

    assert result["success"] is True
    assert "5%" in result["decision"] or "discount" in result["decision"].lower()
    assert result["confidence"] == pytest.approx(0.85)
    actions.speak.assert_called_once()


# ── Test 2: brief returns cached or generates ──────────────────────────────

def test_brief_action_returns_cached_brief():
    actions = _make_actions()
    with patch("jarvis.tasks.daily_brief.get_brief", return_value="Today: 3 emails, 2 meetings."):
        result = actions.council_brief(transcript="")

    assert result["success"] is True
    assert "emails" in result["brief"] or len(result["brief"]) > 0
    actions.speak.assert_called_once()


def test_brief_action_generates_when_not_cached():
    actions = _make_actions()
    with (
        patch("jarvis.tasks.daily_brief.get_brief", return_value=""),
        patch("jarvis.tasks.daily_brief.generate_brief",
              new=AsyncMock(return_value={"content": "Generated brief content."})),
    ):
        result = actions.council_brief(transcript="")

    assert result["success"] is True


# ── Test 3: ask_agent routes to specialist ─────────────────────────────────

def test_ask_agent_routes_to_specialist():
    from jarvis.agents.base import AgentResponse
    mock_resp = AgentResponse(
        agent="sales",
        text="Offer a 10% discount given the order volume.",
        input_tokens=40,
        output_tokens=60,
    )
    actions = _make_actions()
    with patch("jarvis.agents.router.route_to_agent",
               new=AsyncMock(return_value=mock_resp)):
        result = actions.ask_agent(transcript="What discount should I give for large orders?")

    assert result["success"] is True
    assert result["agent"] == "sales"
    assert "discount" in result["text"].lower()
    actions.speak.assert_called_once()


# ── Test 4: health_check reports integration count ─────────────────────────

def test_health_action_returns_status():
    mock_status = {
        "timestamp": "2026-05-17T07:00:00",
        "integrations": {
            "gmail": "configured",
            "zoho": "configured",
            "telegram": "configured",
            "anthropic": "configured",
            "gemini": "missing",
        },
        "task_queue": {"pending": 0, "completed": 10},
        "audit_today": {},
        "memory": {"semantic": 315},
    }
    actions = _make_actions()
    with patch("jarvis.dashboard.get_health_status", return_value=mock_status):
        result = actions.health_check(transcript="")

    assert result["success"] is True
    assert "status" in result
    # speak should mention "4 of 5"
    spoken = actions.speak.call_args[0][0]
    assert "4" in spoken and "5" in spoken


# ── Test 5: plan_action returns plan summary ───────────────────────────────

def test_plan_action_returns_plan():
    from jarvis.intelligence.orchestrator import ActionPlan, ActionStep
    mock_plan = ActionPlan(
        query="find Zamilfood's quote and draft a follow-up",
        steps=[
            ActionStep(action="customer_lookup"),
            ActionStep(action="email_draft"),
        ],
        rationale="Look up customer, then draft email.",
        risk_level="MEDIUM",
    )
    actions = _make_actions()
    with patch("jarvis.intelligence.orchestrator.plan_actions",
               new=AsyncMock(return_value=mock_plan)):
        result = actions.plan_action(
            transcript="find Zamilfood's quote and draft a follow-up"
        )

    assert result["success"] is True
    assert result["steps"] == 2
    assert result["risk_level"] == "MEDIUM"
    spoken = actions.speak.call_args[0][0]
    assert "2" in spoken
    assert "MEDIUM" in spoken
