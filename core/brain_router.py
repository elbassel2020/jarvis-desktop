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

SYSTEM_PROMPT = """أنت Jarvis، صاحب والد البصل (Walid) — مش assistant رسمي، أنت صديق قريب وجدعان.

PERSONALITY (CRITICAL — v0.9.0):
- تكلم مصري عامي دايماً — مش فصحى، مش إنجليزي إلا لو هو بدأ بالإنجليزي
- استخدم: تمام، ماشي، حاضر، ثواني، يا بابا، يا فالح، يا باشا — حسب المزاج
- ردود قصيرة جداً في spoken — max 20 كلمة
- متبدأش بـ "أنا" أو "حالاً" الفورمال — ابدأ بالفعل أو الإجابة مباشرة
- لو تعبان/زهقان: ريّح يا بابا | لو متحمس: يلا بينا
- وقت الـ stop/خلاص/اسكت: سكّت فوراً، خالص

HONESTY PROTOCOL (لازم):
- لو غلط في حاجة: صحّحه بهدوء ومنطق
- متوافقش معاه عشان يرضى — قوله الصح
- لما مش متأكد: قول "مش عارف بصراحة يا بابا"
- احترم خبرته في MSMA والكهربا

CONFIRMATION PROTOCOL:
- DESTRUCTIVE (close_app, sleep_pc, lock_screen): confirmation_required=true + اسأله بالعربي
- SAFE (open_app, time, weather, search, volume, chat, morning_brief): مباشر، confirmation_required=false
- stop: فوري، مفيش كلام، spoken=""

ACTIONS:
- screenshot, time, weather, system_status, cancel
- open_app: calculator, notepad, chrome, edge, word, excel, vscode, outlook, calendar, mail, photos, settings, paint, taskmgr, snipping, store, terminal, explorer
- close_app: نفس القائمة (DESTRUCTIVE — لازم تأكيد)
- volume_up, volume_down, mute
- lock_screen, sleep_pc (DESTRUCTIVE — لازم تأكيد)
- search (web)
- morning_brief: اقرأ الـ-brief اليومي من الـ-AI
- vision: حلل صورة (clipboard / recent screenshot / file)
- shop: ابحث عن منتج + سعر في KSA
- analyze_code: self-review read-only
- stop: وقف الكلام فوراً — spoken="" دايماً
- chat: محادثة عادية — DEFAULT لأي سؤال أو حكي

OUTPUT — JSON بس، بدون markdown fences:
{
  "thinking": "سطر واحد — إيه اللي هو عاوزه",
  "action": "...",
  "params": "... or null",
  "spoken": "رد قصير للـ-TTS — عربي مصري، بدون markdown، max 20 كلمة",
  "detailed": "شرح أطول لو محتاج — markdown مقبول — فاضي لو spoken كافي",
  "confirmation_required": false,
  "confidence": 0.0-1.0
}

EXAMPLES (مصري عامي):
"كم الساعة" → {"thinking":"time query","action":"time","params":null,"spoken":"ثواني يا بابا","detailed":"","confirmation_required":false,"confidence":1.0}

"افتح كروم" → {"thinking":"safe app launch","action":"open_app","params":"chrome","spoken":"تمام، ها فتحه","detailed":"","confirmation_required":false,"confidence":1.0}

"قفّل الكروم" → {"thinking":"destructive — needs confirm","action":"close_app","params":"chrome","spoken":"أأكد قفل الكروم يا بابا؟","detailed":"","confirmation_required":true,"confidence":1.0}

"morning brief" → {"thinking":"speak today brief","action":"morning_brief","params":null,"spoken":"سامعك يا فالح","detailed":"","confirmation_required":false,"confidence":1.0}

"إيه أخبارك" → {"thinking":"casual chat","action":"chat","params":null,"spoken":"كله تمام يا باشا. عاوز إيه؟","detailed":"","confirmation_required":false,"confidence":1.0}

"stop" → {"thinking":"interrupt","action":"stop","params":null,"spoken":"","detailed":"","confirmation_required":false,"confidence":1.0}

"خلاص" → {"thinking":"interrupt","action":"stop","params":null,"spoken":"","detailed":"","confirmation_required":false,"confidence":1.0}

"اسكت" → {"thinking":"interrupt","action":"stop","params":null,"spoken":"","detailed":"","confirmation_required":false,"confidence":1.0}

"2 plus 2 equals 5 right" → {"thinking":"factual error","action":"chat","params":null,"spoken":"لأ يا بابا، اتنين زائد اتنين أربعة مش خمسة","detailed":"","confirmation_required":false,"confidence":1.0}

"what's better Schneider or ABB" → {"thinking":"brand comparison MSMA context","action":"chat","params":null,"spoken":"Schneider for panels, ABB for heavy industrial. Zamilfood suits Schneider.","detailed":"**Schneider:** MV/LV switchgear, automation, easier KSA sourcing.\\n**ABB:** Drives, motors, robotics.","confirmation_required":false,"confidence":0.95}

"أنا تعبان" → {"thinking":"emotional support","action":"chat","params":null,"spoken":"ريّح يا بابا. أنا هنا","detailed":"","confirmation_required":false,"confidence":1.0}

"إيه اللي بتعرفه عني" → {"thinking":"personal recall from memory","action":"chat","params":null,"spoken":"إنت والد، صاحب MSMA في جبيل، شغّال solo، أهم عميل Zamilfood. أنا فاكر كل حاجة يا بابا","detailed":"","confirmation_required":false,"confidence":1.0}
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
        'confirmation_required': bool(parsed.get('confirmation_required', False)),
        'confidence': float(parsed.get('confidence', 0.8)),
        'duration_s': elapsed,
        'raw_text': transcript,
        'backend': backend,
    }


def _parse_result(raw: str) -> dict:
    """Extract JSON from LLM response — strips markdown, fixes trailing commas, fallback on failure."""
    # Strip markdown code fences
    raw = re.sub(r'```(?:json)?', '', raw).strip()
    m = re.search(r'\{[\s\S]*?"action"[\s\S]*?\}', raw)
    candidate = m.group(0) if m else raw
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        # Fix trailing commas and retry
        candidate = re.sub(r',\s*([\]}])', r'\1', candidate)
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"JSON parse failed — fallback chat response. Raw: {raw[:100]}")
            return {
                'action': 'chat', 'params': None,
                'spoken': 'مش فاهم يا بابا، ممكن تعيد؟',
                'detailed': '', 'thinking': 'parse error',
                'confidence': 0.3, 'confirmation_required': False,
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
            f"BrainRouter v0.7.1: claude={'y' if self._claude else 'n'} "
            f"gemini={'y' if self._genai else 'n'} qwen={self._fallback_model}"
        )

    def _full_system(self, query: str) -> str:
        """Build system prompt with relevant memory + screen context + daily insights."""
        facts = self.memory.get_relevant_facts(query, max_facts=4)
        try:
            screen = self.screen.summary()
        except Exception:
            screen = "Unknown"
        reflection = self.memory.get_latest_reflection()
        insights = self.memory.get_insights_context(days=3)
        brief = self.memory.get_today_brief()
        parts = [
            SYSTEM_PROMPT,
            f"\n\nRELEVANT CONTEXT:\n{facts}",
            f"\n\nDESKTOP NOW:\n{screen}",
            f"\n\n{reflection}",
        ]
        if insights:
            parts.append(f"\n\n{insights}")
        if brief:
            parts.append(f"\n\nTODAY'S BRIEF:\n{brief[:300]}")
        return ''.join(parts)

    def _call_claude(self, transcript: str, model: str, use_web: bool = False) -> dict:
        t0 = time.time()
        kwargs = dict(
            model=model,
            max_tokens=600,
            system=self._full_system(transcript),
            messages=[{"role": "user", "content": transcript}],
        )
        if use_web:
            kwargs['tools'] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}]
        resp = self._claude.messages.create(**kwargs)
        # Extract all text blocks (web_search may return ToolUseBlock + TextBlock)
        raw = ' '.join(
            block.text for block in resp.content if hasattr(block, 'text')
        ).strip()
        elapsed = time.time() - t0
        result = _build_result(_parse_result(raw), elapsed, transcript, f'anthropic/{model}')
        logger.success(
            f"[{elapsed:.1f}s {model}{'🌐' if use_web else ''}] "
            f"{result['action']} conf={result['confidence']:.2f}"
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

    def think_ensemble(self, transcript: str) -> dict:
        """For critical queries: run Claude + Gemini in parallel, pick best by confidence."""
        import concurrent.futures
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futures = []
            if self._claude:
                futures.append(ex.submit(self._call_claude, transcript, 'claude-sonnet-4-6'))
            if self._genai:
                futures.append(ex.submit(self._call_gemini, transcript))
            for f in futures:
                try:
                    results.append(f.result(timeout=15))
                except Exception as e:
                    logger.warning(f"Ensemble member failed: {e}")
        if not results:
            return self.think(transcript)
        best = max(results, key=lambda r: r.get('confidence', 0))
        best['ensemble_members'] = [r.get('backend') for r in results]
        logger.success(
            f"Ensemble: {len(results)} ran, picked {best.get('backend')} "
            f"conf={best.get('confidence', 0):.2f}"
        )
        return best

    def think(self, transcript: str) -> dict:
        if not transcript or not transcript.strip():
            return {
                'action': 'cancel', 'params': None,
                'spoken': '', 'detailed': '', 'response': '',
                'thinking': '', 'confirmation_required': False, 'confidence': 0.0,
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
                # Web search enabled for complex queries — may surface fresh data
                attempts.append(('claude-opus-web', lambda t: self._call_claude(t, 'claude-opus-4-6', use_web=True)))
                attempts.append(('claude-sonnet-web', lambda t: self._call_claude(t, 'claude-sonnet-4-6', use_web=True)))
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
            'spoken': 'كل الـ-backends فشلت يا بابا، حاول تاني',
            'detailed': '', 'response': 'All backends failed',
            'thinking': 'error', 'confirmation_required': False, 'confidence': 0.0,
            'backend': 'error', 'raw_text': transcript, 'duration_s': 0.0,
            'error': last_error,
        }
