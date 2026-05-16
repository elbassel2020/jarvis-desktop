"""
Council Mode — parallel 3-LLM ensemble with synthesis.

Three voices deliberate concurrently; a 4th synthesis pass produces
a final decision with confidence score.

Voices:
  - claude-sonnet-4-6  (primary reasoning)
  - claude-haiku-4-5   (fast alternative)
  - gemini-2.0-flash-lite (independent perspective)

Usage::
    result = await council_decide(
        question="Should we offer Zamilfood a 5% discount?",
        context="They placed 3 orders this quarter totalling 120k SAR.",
    )
    print(result.decision, result.confidence)
"""
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from jarvis.security.audit import write_audit
from jarvis.security.credential_broker import broker
from jarvis.security.http_guard import safe_async_client

_logger = logging.getLogger("jarvis.intelligence.council")

# ── Model IDs ─────────────────────────────────────────────────────────────
_SONNET_MODEL = "claude-sonnet-4-6"
_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_GEMINI_MODEL = "gemini-2.0-flash-lite"

# ── Endpoints ──────────────────────────────────────────────────────────────
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_GEMINI_URL_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

# ── Cost constants (USD-cents per 1M tokens, approximations) ───────────────
_SONNET_IN_CENTS_PER_1M = 300   # $3 / 1M input tokens
_SONNET_OUT_CENTS_PER_1M = 1500  # $15 / 1M output tokens
_HAIKU_IN_CENTS_PER_1M = 25
_HAIKU_OUT_CENTS_PER_1M = 125
_GEMINI_FLASH_LITE_IN_CENTS_PER_1M = 7
_GEMINI_FLASH_LITE_OUT_CENTS_PER_1M = 30

_SYNTHESIS_PROMPT = """\
You are a synthesis judge. Three AI advisors answered the question below.
Review all three answers and produce a final, unified recommendation.

End your reply with exactly this line (replace X.X with a number 0.0-1.0):
CONFIDENCE: X.X

Question: {question}

ADVISOR 1 (Sonnet):
{voice_1}

ADVISOR 2 (Haiku):
{voice_2}

ADVISOR 3 (Gemini):
{voice_3}

Synthesized decision:"""

# ── Dataclass ──────────────────────────────────────────────────────────────

@dataclass
class CouncilResult:
    """Outcome of a council deliberation."""
    decision: str
    confidence: float
    voices: dict = field(default_factory=dict)   # {"sonnet": ..., "haiku": ..., "gemini": ...}
    synthesis: str = ""
    cost_usd_cents: int = 0
    duration_ms: int = 0


# ── Per-voice callers ──────────────────────────────────────────────────────

async def _ask_anthropic(model: str, prompt: str, max_tokens: int = 512) -> dict:
    """Call Anthropic Messages API. Returns {text, input_tokens, output_tokens}."""
    api_key = broker.resolve("cred://anthropic/default")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
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
    return {
        "text": text,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


async def _ask_sonnet(prompt: str) -> dict:
    return await _ask_anthropic(_SONNET_MODEL, prompt)


async def _ask_haiku(prompt: str) -> dict:
    return await _ask_anthropic(_HAIKU_MODEL, prompt)


async def _ask_gemini(prompt: str, max_tokens: int = 512) -> dict:
    """Call Gemini generateContent REST API."""
    api_key = broker.resolve("cred://gemini/default")
    url = _GEMINI_URL_TMPL.format(model=_GEMINI_MODEL, key=api_key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    async with safe_async_client(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    text = ""
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
    usage = data.get("usageMetadata", {})
    return {
        "text": text,
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
    }


# ── Cost helpers ───────────────────────────────────────────────────────────

def _cost_cents(in_tok: int, out_tok: int, in_rate: int, out_rate: int) -> int:
    return (in_tok * in_rate + out_tok * out_rate) // 1_000_000


# ── Confidence parser ──────────────────────────────────────────────────────

def _parse_confidence(text: str) -> float:
    """Extract CONFIDENCE: X.X from synthesis output. Default 0.5."""
    m = re.search(r"CONFIDENCE:\s*([0-9]+(?:\.[0-9]+)?)", text)
    if m:
        val = float(m.group(1))
        return max(0.0, min(1.0, val))
    return 0.5


# ── Public API ─────────────────────────────────────────────────────────────

async def council_decide(
    question: str,
    context: str = "",
    max_tokens_per_voice: int = 400,
    include_gemini: bool = True,
) -> CouncilResult:
    """
    Run three LLMs in parallel, then synthesise into one decision.

    Parameters
    ----------
    question:
        The question or task for the council to decide.
    context:
        Optional background context prepended to the prompt.
    max_tokens_per_voice:
        Token budget per voice (synthesis uses 2× this).
    include_gemini:
        Set False to skip Gemini (e.g. if API key not provisioned).

    Returns
    -------
    CouncilResult
    """
    t0 = time.monotonic()
    ctx_block = f"\nContext:\n{context}\n" if context else ""
    voice_prompt = (
        f"{ctx_block}\nQuestion: {question}\n\n"
        "Give a concise, direct answer in 2-4 sentences."
    )

    # ── Phase 1: parallel deliberation ────────────────────────────────────
    tasks: list = [_ask_sonnet(voice_prompt), _ask_haiku(voice_prompt)]
    if include_gemini:
        tasks.append(_ask_gemini(voice_prompt, max_tokens=max_tokens_per_voice))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    sonnet_r = results[0] if not isinstance(results[0], Exception) else None
    haiku_r  = results[1] if not isinstance(results[1], Exception) else None
    gemini_r = results[2] if (include_gemini and len(results) > 2
                              and not isinstance(results[2], Exception)) else None

    if isinstance(results[0], Exception):
        _logger.warning(f"Sonnet failed: {results[0]}")
    if isinstance(results[1], Exception):
        _logger.warning(f"Haiku failed: {results[1]}")
    if include_gemini and len(results) > 2 and isinstance(results[2], Exception):
        _logger.warning(f"Gemini failed: {results[2]}")

    voices = {
        "sonnet": sonnet_r["text"] if sonnet_r else "[failed]",
        "haiku":  haiku_r["text"]  if haiku_r  else "[failed]",
        "gemini": gemini_r["text"] if gemini_r  else ("[failed]" if include_gemini else "[skipped]"),
    }

    # ── Cost so far ────────────────────────────────────────────────────────
    total_cents = 0
    if sonnet_r:
        total_cents += _cost_cents(
            sonnet_r["input_tokens"], sonnet_r["output_tokens"],
            _SONNET_IN_CENTS_PER_1M, _SONNET_OUT_CENTS_PER_1M,
        )
    if haiku_r:
        total_cents += _cost_cents(
            haiku_r["input_tokens"], haiku_r["output_tokens"],
            _HAIKU_IN_CENTS_PER_1M, _HAIKU_OUT_CENTS_PER_1M,
        )
    if gemini_r:
        total_cents += _cost_cents(
            gemini_r["input_tokens"], gemini_r["output_tokens"],
            _GEMINI_FLASH_LITE_IN_CENTS_PER_1M, _GEMINI_FLASH_LITE_OUT_CENTS_PER_1M,
        )

    # ── Phase 2: synthesis ─────────────────────────────────────────────────
    synthesis_prompt = _SYNTHESIS_PROMPT.format(
        question=question,
        voice_1=voices["sonnet"],
        voice_2=voices["haiku"],
        voice_3=voices["gemini"],
    )
    try:
        synth_r = await _ask_sonnet(synthesis_prompt)
        synthesis_text = synth_r["text"]
        total_cents += _cost_cents(
            synth_r["input_tokens"], synth_r["output_tokens"],
            _SONNET_IN_CENTS_PER_1M, _SONNET_OUT_CENTS_PER_1M,
        )
    except Exception as exc:
        _logger.warning(f"Synthesis failed: {exc}")
        synthesis_text = voices["sonnet"]  # fallback to primary voice

    confidence = _parse_confidence(synthesis_text)
    duration_ms = int((time.monotonic() - t0) * 1000)

    write_audit(
        actor="council",
        action="council_decide",
        params={"question": question[:120]},
        outcome="ok",
        egress_host="api.anthropic.com",
        cost_usd_cents=total_cents,
        duration_ms=duration_ms,
    )

    return CouncilResult(
        decision=synthesis_text,
        confidence=confidence,
        voices=voices,
        synthesis=synthesis_text,
        cost_usd_cents=total_cents,
        duration_ms=duration_ms,
    )
