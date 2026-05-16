"""
Agent Router — keyword-based routing to specialist agents.

detect_agent(query) → agent name string
route_to_agent(query, context, agent_name) → AgentResponse

Routing priority: explicit agent_name > keyword scoring > default "sales"
"""
import logging
from typing import Optional

from jarvis.agents.base import AgentResponse
from jarvis.agents.sales_agent import SalesAgent
from jarvis.agents.research_agent import ResearchAgent
from jarvis.agents.email_agent import EmailAgent
from jarvis.agents.customer_agent import CustomerAgent

_logger = logging.getLogger("jarvis.agents.router")

# ── Keyword scoring table ──────────────────────────────────────────────────
# Each entry: (agent_name, [keywords], weight_per_match)
_ROUTING_TABLE = [
    ("email", [
        "email", "draft", "write", "compose", "reply", "follow-up", "follow up",
        "message", "letter", "إيميل", "رسالة", "كتابة", "رد",
    ], 2),
    ("research", [
        "zatca", "vat", "ضريبة", "vision 2030", "nidlp", "saso", "regulation",
        "law", "قانون", "aramco tender", "sabic", "market", "competitor",
        "import duty", "tariff", "certification", "research", "بحث", "تنظيم",
    ], 2),
    ("customer", [
        "customer", "client", "account", "deepdive", "deep dive", "profile",
        "history", "orders", "relationship", "عميل", "حساب", "تاريخ",
        "zamilfood", "kfip", "sec", "siemens",
    ], 2),
    ("sales", [
        "quote", "price", "discount", "deal", "offer", "proposal", "margin",
        "win", "close", "pipeline", "سعر", "عرض", "خصم", "صفقة",
        "revenue", "order", "purchase", "طلب", "شراء",
    ], 2),
]

_AGENTS: dict[str, type] = {
    "sales":    SalesAgent,
    "research": ResearchAgent,
    "email":    EmailAgent,
    "customer": CustomerAgent,
}

_DEFAULT_AGENT = "sales"


def detect_agent(query: str) -> str:
    """
    Score query against keyword table and return best-matching agent name.

    Falls back to "sales" when scores are tied or all zero.

    Parameters
    ----------
    query:
        Raw user query string (any language).

    Returns
    -------
    str — one of: "sales", "research", "email", "customer"
    """
    q = query.lower()
    scores: dict[str, int] = {name: 0 for name in _AGENTS}

    for agent_name, keywords, weight in _ROUTING_TABLE:
        for kw in keywords:
            if kw in q:
                scores[agent_name] += weight

    best_score = max(scores.values())
    if best_score == 0:
        return _DEFAULT_AGENT

    # If tied, prefer in priority order: email > research > customer > sales
    priority = ["email", "research", "customer", "sales"]
    best_agents = [a for a in priority if scores[a] == best_score]
    return best_agents[0]


async def route_to_agent(
    query: str,
    context: str = "",
    agent_name: Optional[str] = None,
    company_name: str = "",
    **kwargs,
) -> AgentResponse:
    """
    Route query to the appropriate specialist agent and return its response.

    Parameters
    ----------
    query:
        User query.
    context:
        Optional background context.
    agent_name:
        Force a specific agent (skips keyword detection).
    company_name:
        Passed to CustomerAgent for deepdive enrichment.

    Returns
    -------
    AgentResponse from the selected agent.
    """
    selected = agent_name if agent_name in _AGENTS else detect_agent(query)
    _logger.info(f"Routing to agent='{selected}' (explicit={agent_name is not None})")

    agent_cls = _AGENTS[selected]
    agent = agent_cls()

    if selected == "customer":
        return await agent.respond(
            query=query,
            context=context,
            company_name=company_name,
            **kwargs,
        )

    return await agent.respond(query=query, context=context, **kwargs)
