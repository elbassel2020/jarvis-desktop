"""
Council Mode tests — all LLM calls mocked.

Tests:
1. council_decide returns CouncilResult with required fields
2. confidence parsed correctly from synthesis text
3. voice failure handled gracefully (one LLM fails, others succeed)
4. all voices fail → result still has decision from fallback
"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from jarvis.intelligence.council import (
    CouncilResult,
    council_decide,
    _parse_confidence,
    _ask_sonnet,
    _ask_haiku,
    _ask_gemini,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _mock_voice(text: str, in_tok: int = 50, out_tok: int = 80) -> dict:
    return {"text": text, "input_tokens": in_tok, "output_tokens": out_tok}


_SONNET_RESP = _mock_voice("Sonnet says: Yes, offer the discount.")
_HAIKU_RESP  = _mock_voice("Haiku says: Discount is justified given loyalty.")
_GEMINI_RESP = _mock_voice("Gemini says: A 5% discount is reasonable.")
_SYNTH_RESP  = _mock_voice(
    "All three advisors agree. Offer the discount.\nCONFIDENCE: 0.87"
)


# ── Test 1: happy path returns CouncilResult ───────────────────────────────

@pytest.mark.asyncio
async def test_council_decide_returns_result():
    with (
        patch("jarvis.intelligence.council._ask_sonnet",
              side_effect=[_SONNET_RESP, _SYNTH_RESP]) as mock_sonnet,
        patch("jarvis.intelligence.council._ask_haiku",
              return_value=_HAIKU_RESP),
        patch("jarvis.intelligence.council._ask_gemini",
              return_value=_GEMINI_RESP),
        patch("jarvis.intelligence.council.write_audit"),
    ):
        result = await council_decide(
            question="Should we offer a 5% discount?",
            context="Customer ordered 120k SAR this quarter.",
        )

    assert isinstance(result, CouncilResult)
    assert isinstance(result.decision, str)
    assert len(result.decision) > 0
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0
    assert "sonnet" in result.voices
    assert "haiku" in result.voices
    assert "gemini" in result.voices
    assert result.duration_ms >= 0


# ── Test 2: confidence parsing ─────────────────────────────────────────────

def test_parse_confidence_extracts_value():
    assert _parse_confidence("Some text\nCONFIDENCE: 0.92") == pytest.approx(0.92)
    assert _parse_confidence("CONFIDENCE: 1.0") == pytest.approx(1.0)
    assert _parse_confidence("CONFIDENCE: 0.0") == pytest.approx(0.0)


def test_parse_confidence_clamps_to_range():
    # Values > 1.0 are clamped to 1.0
    assert _parse_confidence("CONFIDENCE: 1.5") == pytest.approx(1.0)
    assert _parse_confidence("CONFIDENCE: 99") == pytest.approx(1.0)
    # Negative strings don't match regex → return default 0.5
    assert _parse_confidence("CONFIDENCE: -0.3") == pytest.approx(0.5)


def test_parse_confidence_missing_returns_default():
    assert _parse_confidence("No confidence line here.") == pytest.approx(0.5)


# ── Test 3: one voice fails, others succeed ────────────────────────────────

@pytest.mark.asyncio
async def test_council_handles_one_voice_failure():
    with (
        patch("jarvis.intelligence.council._ask_sonnet",
              side_effect=[_SONNET_RESP, _SYNTH_RESP]),
        patch("jarvis.intelligence.council._ask_haiku",
              side_effect=Exception("Haiku timeout")),
        patch("jarvis.intelligence.council._ask_gemini",
              return_value=_GEMINI_RESP),
        patch("jarvis.intelligence.council.write_audit"),
    ):
        result = await council_decide("Test question?")

    assert isinstance(result, CouncilResult)
    assert result.voices["haiku"] == "[failed]"
    # decision still populated from synthesis
    assert len(result.decision) > 0


# ── Test 4: all voices fail → synthesis still runs on fallback ─────────────

@pytest.mark.asyncio
async def test_council_all_voices_fail():
    with (
        patch("jarvis.intelligence.council._ask_sonnet",
              side_effect=Exception("API down")),
        patch("jarvis.intelligence.council._ask_haiku",
              side_effect=Exception("API down")),
        patch("jarvis.intelligence.council._ask_gemini",
              side_effect=Exception("API down")),
        patch("jarvis.intelligence.council.write_audit"),
    ):
        result = await council_decide("Fallback test?")

    assert isinstance(result, CouncilResult)
    # All voices recorded as failed
    assert result.voices["sonnet"] == "[failed]"
    assert result.voices["haiku"] == "[failed]"
    assert result.voices["gemini"] == "[failed]"


# ── Test 5: gemini skipped when include_gemini=False ──────────────────────

@pytest.mark.asyncio
async def test_council_skip_gemini():
    with (
        patch("jarvis.intelligence.council._ask_sonnet",
              side_effect=[_SONNET_RESP, _SYNTH_RESP]),
        patch("jarvis.intelligence.council._ask_haiku",
              return_value=_HAIKU_RESP),
        patch("jarvis.intelligence.council._ask_gemini") as mock_gemini,
        patch("jarvis.intelligence.council.write_audit"),
    ):
        result = await council_decide("Gemini skip test?", include_gemini=False)

    mock_gemini.assert_not_called()
    assert result.voices["gemini"] == "[skipped]"
    assert isinstance(result, CouncilResult)


# ── Test 6: cost_usd_cents is non-negative int ─────────────────────────────

@pytest.mark.asyncio
async def test_council_cost_is_non_negative():
    with (
        patch("jarvis.intelligence.council._ask_sonnet",
              side_effect=[_SONNET_RESP, _SYNTH_RESP]),
        patch("jarvis.intelligence.council._ask_haiku",
              return_value=_HAIKU_RESP),
        patch("jarvis.intelligence.council._ask_gemini",
              return_value=_GEMINI_RESP),
        patch("jarvis.intelligence.council.write_audit"),
    ):
        result = await council_decide("Cost test?")

    assert isinstance(result.cost_usd_cents, int)
    assert result.cost_usd_cents >= 0
