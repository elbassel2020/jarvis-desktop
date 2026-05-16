"""
Orchestrator tests — council mocked throughout.

Tests:
1. plan_actions parses valid JSON response
2. plan handles markdown fences around JSON
3. execute_plan calls async handler correctly
4. execute_plan calls sync handler correctly
5. execute_plan stops when user denies confirmation
6. execute_plan proceeds when user approves confirmation
7. plan handles invalid / non-JSON response (risk_level=HIGH, steps=[])
8. execute_plan logs error for missing handler and continues
9. execute_plan stops on handler exception
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from jarvis.intelligence.orchestrator import (
    plan_actions, execute_plan, ActionPlan, ActionStep,
)


def _council_mock(decision: str):
    m = MagicMock()
    m.decision = decision
    return m


# ── Plan parsing ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_actions_parses_json():
    payload = '{"steps": [{"action": "email_list_unread", "params": {"limit": 5}}], "rationale": "list emails", "risk_level": "LOW"}'
    with (
        patch("jarvis.intelligence.orchestrator.council_decide",
              new=AsyncMock(return_value=_council_mock(payload))),
        patch("jarvis.intelligence.orchestrator.write_audit"),
    ):
        plan = await plan_actions("show my unread emails")

    assert len(plan.steps) == 1
    assert plan.steps[0].action == "email_list_unread"
    assert plan.steps[0].params == {"limit": 5}
    assert plan.risk_level == "LOW"
    assert "list emails" in plan.rationale


@pytest.mark.asyncio
async def test_plan_handles_markdown_fences():
    payload = '```json\n{"steps": [], "rationale": "noop", "risk_level": "LOW"}\n```'
    with (
        patch("jarvis.intelligence.orchestrator.council_decide",
              new=AsyncMock(return_value=_council_mock(payload))),
        patch("jarvis.intelligence.orchestrator.write_audit"),
    ):
        plan = await plan_actions("test")

    assert isinstance(plan, ActionPlan)
    assert plan.steps == []
    assert plan.risk_level == "LOW"


@pytest.mark.asyncio
async def test_plan_handles_invalid_json():
    with (
        patch("jarvis.intelligence.orchestrator.council_decide",
              new=AsyncMock(return_value=_council_mock("this is not json at all"))),
        patch("jarvis.intelligence.orchestrator.write_audit"),
    ):
        plan = await plan_actions("test query")

    assert plan.risk_level == "HIGH"
    assert plan.steps == []
    assert "failed" in plan.rationale.lower()


# ── Execute plan ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_plan_calls_async_handler():
    plan = ActionPlan(
        query="test",
        steps=[ActionStep(action="test_action", params={"x": 1})],
    )

    async def handler(x):
        return {"result": x * 2}

    results = await execute_plan(plan, action_handlers={"test_action": handler})
    assert len(results) == 1
    assert results[0]["result"] == {"result": 2}


@pytest.mark.asyncio
async def test_execute_plan_calls_sync_handler():
    plan = ActionPlan(
        query="test",
        steps=[ActionStep(action="sync_action", params={"x": 3})],
    )

    def handler(x):
        return x + 10

    results = await execute_plan(plan, action_handlers={"sync_action": handler})
    assert results[0]["result"] == 13


@pytest.mark.asyncio
async def test_execute_plan_respects_confirmation_deny():
    plan = ActionPlan(
        query="dangerous",
        steps=[ActionStep(action="delete_all", confirmation_required=True)],
    )

    async def deny(step):
        return False

    results = await execute_plan(
        plan,
        action_handlers={"delete_all": lambda: None},
        confirm_callback=deny,
    )
    assert "skipped" in results[0]
    assert results[0]["skipped"] == "user declined"


@pytest.mark.asyncio
async def test_execute_plan_respects_confirmation_approve():
    plan = ActionPlan(
        query="careful",
        steps=[ActionStep(
            action="email_send_draft",
            params={"draft_id": "abc"},
            confirmation_required=True,
        )],
    )

    async def approve(step):
        return True

    results = await execute_plan(
        plan,
        action_handlers={"email_send_draft": lambda draft_id: {"sent": True}},
        confirm_callback=approve,
    )
    assert results[0]["result"]["sent"] is True


@pytest.mark.asyncio
async def test_execute_plan_handles_missing_handler():
    plan = ActionPlan(
        query="test",
        steps=[ActionStep(action="undefined_action")],
    )
    results = await execute_plan(plan, action_handlers={})
    assert "error" in results[0]
    assert "no handler" in results[0]["error"]


@pytest.mark.asyncio
async def test_execute_plan_stops_on_handler_exception():
    plan = ActionPlan(
        query="test",
        steps=[
            ActionStep(action="bad"),
            ActionStep(action="good"),   # must NOT execute
        ],
    )

    def bad_handler():
        raise ValueError("intentional failure")

    results = await execute_plan(
        plan,
        action_handlers={"bad": bad_handler, "good": lambda: "ok"},
    )
    assert len(results) == 1
    assert "error" in results[0]
    assert "intentional failure" in results[0]["error"]
