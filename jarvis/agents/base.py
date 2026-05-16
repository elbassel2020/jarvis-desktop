"""
BaseAgent — shared async respond() implementation.

All specialist agents inherit from this. Each agent supplies a system prompt;
BaseAgent handles the Anthropic API call, audit logging, and returns a typed
AgentResponse.
"""
import logging
import time
from dataclasses import dataclass, field

from jarvis.security.audit import write_audit
from jarvis.security.credential_broker import broker
from jarvis.security.http_guard import safe_async_client

_logger = logging.getLogger("jarvis.agents.base")

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 600


@dataclass
class AgentResponse:
    """Typed return value from any specialist agent."""
    agent: str
    text: str
    model: str = _DEFAULT_MODEL
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_cents: int = 0
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)


# Cost constants (USD-cents per 1M tokens)
_SONNET_IN_CENTS_PER_1M = 300
_SONNET_OUT_CENTS_PER_1M = 1500


def _cost_cents(in_tok: int, out_tok: int) -> int:
    return (in_tok * _SONNET_IN_CENTS_PER_1M + out_tok * _SONNET_OUT_CENTS_PER_1M) // 1_000_000


class BaseAgent:
    """
    Specialist agent base class.

    Subclasses must define:
        name: str           — used in audit log actor field
        system_prompt: str  — injected as system role
    """
    name: str = "base"
    system_prompt: str = "You are a helpful assistant."

    async def respond(
        self,
        query: str,
        context: str = "",
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        model: str = _DEFAULT_MODEL,
    ) -> AgentResponse:
        """
        Call Anthropic with system + user message.

        Parameters
        ----------
        query:
            User question / task.
        context:
            Optional background (e.g. customer deepdive, email thread).
        max_tokens:
            Hard cap on response length.
        model:
            Anthropic model ID override.

        Returns
        -------
        AgentResponse
        """
        t0 = time.monotonic()
        api_key = broker.resolve("cred://anthropic/default")

        user_content = query
        if context:
            user_content = f"Context:\n{context}\n\nQuery: {query}"

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }

        try:
            async with safe_async_client(timeout=30.0) as client:
                resp = await client.post(
                    _ANTHROPIC_URL,
                    json=payload,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                )
                resp.raise_for_status()

            data = resp.json()
            text = data["content"][0]["text"] if data.get("content") else ""
            usage = data.get("usage", {})
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            cost = _cost_cents(in_tok, out_tok)
            duration_ms = int((time.monotonic() - t0) * 1000)

            write_audit(
                actor=f"agent:{self.name}",
                action="respond",
                params={"query": query[:100]},
                outcome="ok",
                egress_host="api.anthropic.com",
                cost_usd_cents=cost,
                tokens=in_tok + out_tok,
                duration_ms=duration_ms,
            )

            return AgentResponse(
                agent=self.name,
                text=text,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd_cents=cost,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            _logger.error(f"[{self.name}] respond() failed: {exc}")
            write_audit(
                actor=f"agent:{self.name}",
                action="respond",
                params={"query": query[:100]},
                outcome=f"error:{type(exc).__name__}",
                duration_ms=duration_ms,
            )
            raise
