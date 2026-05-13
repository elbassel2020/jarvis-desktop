"""v0.6.0 Multi-LLM Router — Claude Opus/Sonnet + Gemini 2.5 Flash + Qwen fallback."""
import os
import json
import re
import time
from loguru import logger

from core.llm_brain import SYSTEM_PROMPT, _parse_json

# Complexity thresholds (word count)
_SIMPLE_MAX = 6
_MEDIUM_MAX = 15


def classify_complexity(text: str) -> str:
    """Simple heuristic: word count + question complexity."""
    words = text.split()
    n = len(words)
    if n <= _SIMPLE_MAX:
        return 'simple'
    if n <= _MEDIUM_MAX:
        return 'medium'
    return 'complex'


def _build_result(parsed: dict, elapsed: float, transcript: str, backend: str) -> dict:
    return {
        'action': parsed.get('action', 'chat'),
        'params': parsed.get('params'),
        'response': parsed.get('response', ''),
        'confidence': float(parsed.get('confidence', 0.8)),
        'duration_s': elapsed,
        'raw_text': transcript,
        'backend': backend,
    }


class BrainRouter:
    def __init__(self):
        self._qwen = None  # lazy

        # Anthropic
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_KEY')
        if api_key:
            from anthropic import Anthropic
            self._claude = Anthropic(api_key=api_key)
        else:
            self._claude = None
            logger.warning("No ANTHROPIC_API_KEY — Claude unavailable")

        # Gemini
        gemini_key = os.getenv('GEMINI_API_KEY')
        if gemini_key:
            from google import genai
            self._genai_client = genai.Client(api_key=gemini_key)
            self._genai = True
        else:
            self._genai_client = None
            self._genai = None
            logger.warning("No GEMINI_API_KEY — Gemini unavailable")

        fallback = os.getenv('LLM_FALLBACK', 'qwen2.5:7b')
        self._fallback_model = fallback

        logger.info(
            f"BrainRouter: claude={'yes' if self._claude else 'no'} "
            f"gemini={'yes' if self._genai else 'no'} "
            f"qwen={fallback}"
        )

    # ------------------------------------------------------------------ #
    #  Backend callers                                                     #
    # ------------------------------------------------------------------ #

    def _call_claude(self, transcript: str, model: str) -> dict:
        t0 = time.time()
        resp = self._claude.messages.create(
            model=model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
        raw = resp.content[0].text.strip()
        elapsed = time.time() - t0
        parsed = _parse_json(raw)
        result = _build_result(parsed, elapsed, transcript, f'anthropic/{model}')
        logger.success(f"[{elapsed:.1f}s {model}] {result['action']} conf={result['confidence']:.2f}")
        return result

    def _call_gemini(self, transcript: str) -> dict:
        from google.genai import types
        t0 = time.time()
        resp = self._genai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=transcript,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=300,
                temperature=0.3,
            ),
        )
        raw = resp.text.strip()
        elapsed = time.time() - t0
        parsed = _parse_json(raw)
        result = _build_result(parsed, elapsed, transcript, 'google/gemini-2.5-flash')
        logger.success(f"[{elapsed:.1f}s Gemini] {result['action']} conf={result['confidence']:.2f}")
        return result

    def _call_qwen(self, transcript: str) -> dict:
        if self._qwen is None:
            import ollama
            self._qwen = ollama.Client(host=os.getenv('OLLAMA_HOST', 'http://localhost:11434'))
        t0 = time.time()
        resp = self._qwen.chat(
            model=self._fallback_model,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': transcript},
            ],
            options={'temperature': 0.3},
        )
        raw = resp['message']['content'].strip()
        elapsed = time.time() - t0
        parsed = _parse_json(raw)
        result = _build_result(parsed, elapsed, transcript, f'ollama/{self._fallback_model}')
        result['confidence'] = float(parsed.get('confidence', 0.5))
        logger.success(f"[{elapsed:.1f}s Qwen] {result['action']} conf={result['confidence']:.2f}")
        return result

    # ------------------------------------------------------------------ #
    #  Routing logic                                                       #
    # ------------------------------------------------------------------ #

    def think(self, transcript: str) -> dict:
        if not transcript or not transcript.strip():
            return {
                'action': 'cancel', 'params': None, 'response': '',
                'confidence': 0.0, 'raw_text': '', 'backend': 'empty', 'duration_s': 0.0,
            }

        complexity = classify_complexity(transcript)
        logger.info(f"Complexity={complexity} for: '{transcript[:50]}'")

        # Route by complexity
        # simple  → Gemini 2.5 Flash (fast + cheap)
        # medium  → Claude Sonnet 4.6
        # complex → Claude Opus 4.6
        attempts = []

        if complexity == 'simple' and self._genai:
            attempts.append(('gemini', None))
        elif complexity == 'medium' and self._claude:
            attempts.append(('claude', 'claude-sonnet-4-6'))
        elif complexity == 'complex' and self._claude:
            attempts.append(('claude', 'claude-opus-4-6'))

        # Always add Qwen as final fallback
        attempts.append(('qwen', None))

        for backend, model in attempts:
            try:
                if backend == 'gemini':
                    return self._call_gemini(transcript)
                elif backend == 'claude':
                    return self._call_claude(transcript, model)
                else:
                    return self._call_qwen(transcript)
            except Exception as e:
                logger.warning(f"{backend} failed ({e}), trying next")

        return {
            'action': 'chat', 'params': None,
            'response': "I had trouble understanding, try again",
            'confidence': 0.0, 'backend': 'error',
            'raw_text': transcript, 'duration_s': 0.0,
        }
