"""Agent-based brain: Planner → Executor with spoken/detailed split (v0.7.1)."""
import os
import json
import re
import time
from loguru import logger

from core.llm_brain import _parse_json
from core.memory import JarvisMemory
from core.screen_awareness import ScreenAwareness

# Complexity thresholds (word count — preserved for test compatibility)
_SIMPLE_MAX = 6
_MEDIUM_MAX = 15

SYSTEM_PROMPT = """You are Jarvis, Walid's personal AI companion (B2B electrical contractor, Jubail KSA).

PERSONALITY:
- Warm, witty, supportive friend
- Match Walid's language exactly: Arabic (Egyptian dialect) / English / mixed
- Direct, practical — no fluff
- Use "Walid" / "والد" occasionally
- Reference desktop state + memory when relevant
- Honest, no sycophancy

ACTIONS:
- screenshot, time, weather, system_status, cancel
- open_app: calculator, notepad, chrome, edge, word, excel, vscode, outlook, calendar, mail, photos, settings, paint, taskmgr, snipping, store, terminal, explorer
- close_app: same list as open_app
- search (web)
- chat (free conversation — DEFAULT for questions, advice, casual)

CRITICAL OUTPUT — STRICT JSON ONLY, NO markdown fences:
{
  "thinking": "1-sentence internal reasoning about what user wants",
  "action": "...",
  "params": "... or null",
  "spoken": "SHORT 1-3 sentences for TTS — natural, NO markdown, NO asterisks, NO headers, max 50 words",
  "detailed": "Longer explanation with markdown OK for screen display — empty string if spoken is sufficient",
  "confidence": 0.0-1.0
}

EXAMPLES:
"كم الساعة" → {"thinking":"simple time query","action":"time","params":null,"spoken":"حالاً اقولك يا والد","detailed":"","confidence":1.0}

"close calendar" → {"thinking":"close action requested","action":"close_app","params":"calendar","spoken":"تمام، باقفل الكالندر","detailed":"","confidence":1.0}

"what's better Schneider or ABB" → {"thinking":"brand comparison, electrical, relevant to MSMA","action":"chat","params":null,"spoken":"Schneider for panels and buildings, ABB for heavy industrial and drives. Your Zamilfood work suits Schneider.","detailed":"**Schneider Electric:** MV/LV switchgear, building automation, easier KSA sourcing.\\n**ABB:** Drives, motors, heavy industrial, robotics.\\nMatch to use case — Schneider wins for your current clients.","confidence":0.95}

"انا تعبان شويه" → {"thinking":"emotional check-in, needs support","action":"chat","params":null,"spoken":"خد راحتك يا والد. عملت كتير اليوم، تستحق استراحة","detailed":"","confidence":1.0}

"ايه فاتح عندي" → {"thinking":"asking about desktop state","action":"chat","params":null,"spoken":"شايف عندك Excel وChrome مفتوحين. عاوز حاجة؟","detailed":"","confidence":1.0}
"""


def classify_complexity(text: str) -> str:
    """Word-count heuristic — preserved for test compatibility."""
    words = text.split()
    n = len(words)
    if n <= _SIMPLE_MAX:
        return 'simple'
    if n <= _MEDIUM_MAX:
        return 'medium'
    return 'complex'


def _build_result(parsed: dict, elapsed: float, transcript: str, backend: str) -> dict:
    """Normalize parsed dict into standard result format."""
    spoken = parsed.get('spoken') or parsed.get('response', '')
    detailed = parsed.get('detailed', '')
    return {
        'action': parsed.get('action', 'chat'),
        'params': parsed.get('params'),
        'spoken': spoken,
        'detailed': detailed,
        'response': spoken,           # backward compat for tests + TTS
        'thinking': parsed.get('thinking', ''),
        'confidence': float(parsed.get('confidence', 0.8)),
        'duration_s': elapsed,
        'raw_text': transcript,
        'backend': backend,
    }


def _parse_result(raw: str) -> dict:
    """Extract JSON from LLM response, tolerating markdown fences and trailing commas."""
    m = re.search(r'\{[\s\S]*?"action"[\s\S]*?\}', raw)
    candidate = m.group(0) if m else raw
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Fix trailing commas
        candidate = re.sub(r',\s*([\]}])', r'\1', candidate)
        return json.loads(candidate)


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
            f"BrainRouter v0.7.1: claude={'y' if self._claude else 'n'} "
            f"gemini={'y' if self._genai else 'n'} qwen={self._fallback_model}"
        )

    def _full_system(self, query: str) -> str:
        """Build system prompt with relevant memory + screen context."""
        facts = self.memory.get_relevant_facts(query, max_facts=4)
        try:
            screen = self.screen.summary()
        except Exception:
            screen = "Unknown"
        reflection = self.memory.get_latest_reflection()
        return (
            SYSTEM_PROMPT
            + f"\n\nRELEVANT CONTEXT:\n{facts}"
            + f"\n\nDESKTOP NOW:\n{screen}"
            + f"\n\n{reflection}"
        )

    def _call_claude(self, transcript: str, model: str) -> dict:
        t0 = time.time()
        resp = self._claude.messages.create(
            model=model,
            max_tokens=600,
            system=self._full_system(transcript),
            messages=[{"role": "user", "content": transcript}],
        )
        raw = resp.content[0].text.strip()
        elapsed = time.time() - t0
        result = _build_result(_parse_result(raw), elapsed, transcript, f'anthropic/{model}')
        logger.success(
            f"[{elapsed:.1f}s {model}] {result['action']} conf={result['confidence']:.2f}"
        )
        if result['thinking']:
            logger.info(f"  💭 {result['thinking']}")
        return result

    def _call_gemini(self, transcript: str) -> dict:
        from google.genai import types
        t0 = time.time()
        resp = self._genai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=transcript,
            config=types.GenerateContentConfig(
                system_instruction=self._full_system(transcript),
                max_output_tokens=600,
                temperature=0.3,
            ),
        )
        raw = resp.text.strip()
        elapsed = time.time() - t0
        result = _build_result(_parse_result(raw), elapsed, transcript, 'google/gemini-2.5-flash')
        logger.success(
            f"[{elapsed:.1f}s Gemini] {result['action']} conf={result['confidence']:.2f}"
        )
        if result['thinking']:
            logger.info(f"  💭 {result['thinking']}")
        return result

    def _call_qwen(self, transcript: str) -> dict:
        if self._qwen is None:
            import ollama
            self._qwen = ollama.Client(host=os.getenv('OLLAMA_HOST', 'http://localhost:11434'))
        t0 = time.time()
        resp = self._qwen.chat(
            model=self._fallback_model,
            messages=[
                {'role': 'system', 'content': self._full_system(transcript)},
                {'role': 'user', 'content': transcript},
            ],
            options={'temperature': 0.3},
        )
        raw = resp['message']['content'].strip()
        elapsed = time.time() - t0
        result = _build_result(_parse_result(raw), elapsed, transcript, f'ollama/{self._fallback_model}')
        result['confidence'] = float(_parse_result(raw).get('confidence', 0.5))
        logger.success(
            f"[{elapsed:.1f}s Qwen] {result['action']} conf={result['confidence']:.2f}"
        )
        return result

    def think(self, transcript: str) -> dict:
        if not transcript or not transcript.strip():
            return {
                'action': 'cancel', 'params': None,
                'spoken': '', 'detailed': '', 'response': '',
                'thinking': '', 'confidence': 0.0,
                'backend': 'empty', 'raw_text': '', 'duration_s': 0.0,
            }

        complexity = classify_complexity(transcript)
        logger.info(f"Complexity={complexity} for: '{transcript[:60]}'")

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
                logger.warning(f"{name} failed: {last_error[:80]}, trying next")

        return {
            'action': 'chat', 'params': None,
            'spoken': 'كل الـ-backends فشلت يا والد، حاول تاني',
            'detailed': '', 'response': 'All backends failed',
            'thinking': 'error', 'confidence': 0.0,
            'backend': 'error', 'raw_text': transcript, 'duration_s': 0.0,
            'error': last_error,
        }
