"""
Action Orchestrator — decompose complex queries into action steps.

Example:
    "find Zamilfood's last quote, draft a follow-up email"
    → plan: [customer_lookup → email_draft → confirmation gate]

Multi-step plans tracked via parent_task_id in task queue.
"""
import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from jarvis.security.audit import write_audit
from jarvis.intelligence.council import council_decide

_logger = logging.getLogger("jarvis.intelligence.orchestrator")

_DEFAULT_ACTIONS = [
    "email_list_unread", "email_read", "email_draft", "email_send_draft",
    "zoho_list_unread", "zoho_read", "zoho_search",
    "calendar_list_today", "calendar_free_busy", "calendar_create_event",
    "drive_search", "drive_read",
    "telegram_send_self",
    "customer_lookup",
    "speak", "search_memory",
]


@dataclass
class ActionStep:
    action: str
    params: dict = field(default_factory=dict)
    confirmation_required: bool = False
    notes: str = ""


@dataclass
class ActionPlan:
    query: str
    steps: list
    rationale: str = ""
    risk_level: str = "LOW"


def _strip_json(text: str) -> str:
    """Strip markdown fences and extract the outermost JSON object."""
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


async def plan_actions(
    query: str,
    context: str = "",
    available_actions: Optional[list] = None,
) -> ActionPlan:
    """
    Use council to decompose a query into ordered ActionSteps.

    Parameters
    ----------
    query:
        User request to plan.
    context:
        Optional background (customer data, recent emails, etc).
    available_actions:
        Override the default action catalogue.

    Returns
    -------
    ActionPlan — steps=[] and risk_level="HIGH" on parse failure.
    """
    actions = available_actions or _DEFAULT_ACTIONS

    planning_prompt = (
        f"You are a task planner for Jarvis personal AI.\n\n"
        f"Available actions:\n{json.dumps(actions, indent=2)}\n\n"
        f"User query: {query}\n\n"
        f"Context: {context}\n\n"
        "Return ONLY valid JSON (no markdown, no prose):\n"
        "{\n"
        '  "steps": [\n'
        '    {"action": "action_name", "params": {}, "confirmation_required": false, "notes": "why"}\n'
        "  ],\n"
        '  "rationale": "brief explanation",\n'
        '  "risk_level": "LOW|MEDIUM|HIGH"\n'
        "}\n\n"
        "Rules:\n"
        "- Use ONLY actions from the list above\n"
        "- confirmation_required=true for: email_send_draft, calendar_create_event, telegram_send_self\n"
        "- HIGH risk = irreversible; MEDIUM = external API call; LOW = read-only\n"
        "- Minimise steps"
    )

    try:
        result = await council_decide(question=planning_prompt, context="")
        text = _strip_json(result.decision if hasattr(result, "decision") else str(result))
        plan_data = json.loads(text)
        steps = [
            ActionStep(
                action=s["action"],
                params=s.get("params", {}),
                confirmation_required=s.get("confirmation_required", False),
                notes=s.get("notes", ""),
            )
            for s in plan_data.get("steps", [])
        ]
        plan = ActionPlan(
            query=query,
            steps=steps,
            rationale=plan_data.get("rationale", ""),
            risk_level=plan_data.get("risk_level", "MEDIUM"),
        )
    except Exception as exc:
        _logger.error(f"plan_actions parse failed: {exc}")
        plan = ActionPlan(
            query=query,
            steps=[],
            rationale=f"Plan parse failed: {exc}",
            risk_level="HIGH",
        )

    write_audit(
        actor="orchestrator",
        action="plan",
        params={"query": query[:100], "steps": len(plan.steps)},
        outcome="ok",
        notes=f"risk={plan.risk_level}",
    )
    return plan


async def execute_plan(
    plan: ActionPlan,
    action_handlers: dict,
    confirm_callback: Optional[Callable] = None,
) -> list:
    """
    Execute plan steps sequentially.

    Stops on first unconfirmed action or handler exception.

    Parameters
    ----------
    plan:
        ActionPlan from plan_actions().
    action_handlers:
        Mapping of action name → callable (sync or async).
    confirm_callback:
        Async callable(step) → bool. Called before confirmation_required steps.
        If returns False, step is skipped and execution stops.

    Returns
    -------
    list of result dicts, one per executed/skipped step.
    """
    results = []
    for i, step in enumerate(plan.steps):
        if step.confirmation_required and confirm_callback:
            confirmed = await confirm_callback(step)
            if not confirmed:
                results.append({
                    "step": i,
                    "action": step.action,
                    "skipped": "user declined",
                })
                break

        handler = action_handlers.get(step.action)
        if not handler:
            results.append({
                "step": i,
                "action": step.action,
                "error": "no handler",
            })
            continue

        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(**step.params)
            else:
                result = handler(**step.params)
            results.append({"step": i, "action": step.action, "result": result})
        except Exception as exc:
            results.append({"step": i, "action": step.action, "error": str(exc)})
            break

    return results
