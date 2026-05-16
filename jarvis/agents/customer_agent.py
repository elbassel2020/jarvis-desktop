"""
CustomerAgent — context-enriched customer intelligence.

Enriches every query with the customer's deep-dive summary from
jarvis.tasks.customer_deepdive before calling the LLM. Falls back
gracefully when no deepdive exists or MSMA DB is unavailable.
"""
import logging

from jarvis.agents.base import BaseAgent, AgentResponse
from jarvis.tasks.customer_deepdive import get_deepdive

_logger = logging.getLogger("jarvis.agents.customer")

_SYSTEM = """\
You are a customer relationship intelligence assistant for Walid Al-Bassel \
(MSMA Group, Jubail, KSA). You have access to historical order data, quote \
activity, and email patterns for MSMA customers.

Your role:
- Summarise a customer's relationship status with MSMA.
- Identify cross-sell / upsell signals from purchase history.
- Flag at-risk accounts (no orders in 90+ days, overdue payments).
- Recommend personalised engagement actions.

Language: match query language (Arabic or English).
Keep answers factual and tied to the provided customer data.
If no data is available for a customer, say so explicitly.
"""


class CustomerAgent(BaseAgent):
    name = "customer"
    system_prompt = _SYSTEM

    async def respond(
        self,
        query: str,
        context: str = "",
        company_name: str = "",
        max_tokens: int = 600,
        **kwargs,
    ) -> AgentResponse:
        """
        Respond to a customer-related query.

        If `company_name` is provided, fetches the deepdive summary from
        jarvis DB and prepends it to context before calling the LLM.

        Parameters
        ----------
        query:
            User question about the customer.
        context:
            Optional additional context (e.g. recent email thread).
        company_name:
            Customer name to look up in deepdive cache.
        """
        enriched_context = context

        if company_name:
            deepdive = get_deepdive(company_name)
            if deepdive:
                enriched_context = f"[Customer Profile — {company_name}]\n{deepdive}"
                if context:
                    enriched_context += f"\n\n[Additional Context]\n{context}"
                _logger.debug(f"Enriched context with deepdive for '{company_name}'")
            else:
                _logger.info(f"No deepdive cached for '{company_name}' — proceeding without")
                if not context:
                    enriched_context = (
                        f"No historical data found for customer '{company_name}' "
                        f"in the MSMA system."
                    )

        return await super().respond(
            query=query,
            context=enriched_context,
            max_tokens=max_tokens,
            **kwargs,
        )
