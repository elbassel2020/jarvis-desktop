"""Multi-LLM router with personality, memory, and screen awareness (v0.7.0)."""
import os
import json
import re
import time
from loguru import logger

from core.llm_brain import _parse_json
from core.memory import JarvisMemory
from core.screen_awareness import ScreenAwareness

# Complexity thresholds (word count — kept for test compatibility)
_SIMPLE_MAX = 6
_MEDIUM_MAX = 15

SYSTEM_PROMPT_BASE = """You are Jarvis, Walid's personal AI companion and friend.

PERSONALITY:
- Warm, supportive, witty — like a trusted brilliant friend
- LANGUAGE MATCHING (critical):
  - Walid speaks Arabic (Egyptian dialect) AND English, often mixed
  - If he speaks Arabic → respond in Arabic naturally (Egyptian dialect)
  - If he speaks English → respond in English
  - If mixed → mix freely
- Direct, practical (Walid hates fluff)
- Use his name (Walid / والد) occasionally to feel personal
- Acknowledge tiredness, celebrate wins, give honest feedback
- Reference past conversations and desktop state when relevant

ACTIONS available:
- screenshot, time, weather, system_status, cancel
- open_app: calculator, notepad, chrome, edge, word, excel, vscode, outlook, calendar, mail, photos, settings, paint, taskmgr, snipping, store, terminal, explorer
- search (web)
- chat (free conversation for everything else — questions, advice, casual talk)

OUTPUT — STRICT JSON ONLY (no markdown fences):
{"action":"...", "params":"... or null", "response":"natural reply in user's language", "confidence":0.0-1.0}

EXAMPLES:
"كم الساعة" → {"action":"time","params":null,"response":"حالاً يا والد، خليني اشوف","confidence":1.0}
"افتحلي اكسيل" → {"action":"open_app","params":"excel","response":"تمام، بافتح اكسيل","confidence":1.0}
"أنا تعبان" → {"action":"chat","params":null,"response":"خد راحتك يا والد. عملت كتير اليوم، تستحق استراحة","confidence":1.0}
"ايه فاتح عندي" → {"action":"chat","params":null,"response":"شايف عندك [from DESKTOP STATE below]","confidence":1.0}
"احكيلي عن نفسي" → {"action":"chat","params":null,"response":"أنت والد البصل، مهندس MSMA في جبيل. شغّال solo، أهم عملاء Zamilfood كاش و SMI","confidence":1.0}
"what do you think about Schneider" → {"action":"chat","params":null,"response":"Schneider Electric is solid for industrial control — your go-to for Jubail clients","confidence":1.0}
"""


def classify_complexity(text: str) -> str:
    """Word-count heuristic (preserved for test compatibility)."""
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
        self.memory = JarvisMemory()
        self.screen = ScreenAwareness()
        self._claude = None
        self._genai_client = None
        self._genai = None
        self._qwen = None  # lazy
        self._fallback_model = os.getenv('LLM_FALLBACK', 'qwen2.5:7b')

        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_KEY')
        if api_key:
            from anthropic import Anthropic
            try:
                self._claude = Anthropic(api_key=api_key)
                logger.info("✓ Anthropic ready")
            except Exception as e:
                logger.warning(f"Anthropic init: {e}")

        gemini_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if gemini_key:
            from google import genai
            try:
                self._genai_client = genai.Client(api_key=gemini_key)
                self._genai = True
                logger.info("✓ Gemini ready")
            except Exception as e:
                logger.warning(f"Gemini init: {e}")

        logger.info(
            f"BrainRouter v0.7.0: claude={'y' if self._claude else 'n'} "
            f"gemini={'y' if self._genai else 'n'} qwen={self._fallback_model}"
        )

    def _full_system(self) -> str:
        """Build system prompt with live memory + screen context."""
        ctx = self.memory.get_context_for_prompt()
        try:
            screen = self.screen.summary()
            usage = self.memory.get_daily_summary()
            typical = self.memory.get_typical_apps()
            typ_str = ', '.join(f'{a}({n})' for a, n in typical) if typical else 'none yet'
            ctx += (
                f"\n\nDESKTOP STATE:\n{screen}"
                f"\n\nUSAGE PATTERNS:\n{usage}\nUsual this hour: {typ_str}"
            )
        except Exception as e:
            logger.debug(f"context build error: {e}")
        return SYSTEM_PROMPT_BASE + ctx

    def _call_claude(self, transcript: str, model: str) -> dict:
        t0 = time.time()
        resp = self._claude.messages.create(
            model=model,
            max_tokens=400,
            system=self._full_system(),
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
                system_instruction=self._full_system(),
                max_output_tokens=400,
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
                {'role': 'system', 'content': self._full_system()},
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

    def think(self, transcript: str) -> dict:
        if not transcript or not transcript.strip():
            return {
                'action': 'cancel', 'params': None, 'response': '',
                'confidence': 0.0, 'raw_text': '', 'backend': 'empty', 'duration_s': 0.0,
            }

        complexity = classify_complexity(transcript)
        logger.info(f"Complexity={complexity} for: '{transcript[:50]}'")

        attempts = []
        if complexity == 'simple':
            if self._genai:
                attempts.append(('gemini', self._call_gemini))
            if self._claude:
                attempts.append(('claude-sonnet', lambda t: self._call_claude(t, 'claude-sonnet-4-6')))
        elif complexity == 'medium':
            if self._claude:
                attempts.append(('claude-sonnet', lambda t: self._call_claude(t, 'claude-sonnet-4-6')))
            if self._genai:
                attempts.append(('gemini', self._call_gemini))
        elif complexity == 'complex':
            if self._claude:
                attempts.append(('claude-opus', lambda t: self._call_claude(t, 'claude-opus-4-6')))
                attempts.append(('claude-sonnet', lambda t: self._call_claude(t, 'claude-sonnet-4-6')))
            if self._genai:
                attempts.append(('gemini', self._call_gemini))

        attempts.append(('qwen', self._call_qwen))

        last_error = None
        for name, fn in attempts:
            try:
                result = fn(transcript)
                result['complexity'] = complexity
                return result
            except Exception as e:
                last_error = str(e)[:200]
                logger.warning(f"{name} failed: {last_error[:100]}, trying next")

        return {
            'action': 'chat', 'params': None,
            'response': "I had trouble understanding, try again",
            'confidence': 0.0, 'backend': 'error',
            'raw_text': transcript, 'duration_s': 0.0,
            'error': last_error,
        }
