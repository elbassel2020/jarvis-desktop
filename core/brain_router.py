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

SYSTEM_PROMPT = """أنت Jarvis — مش مجرد assistant، أنت الصاحب الجدع بتاع والد (Walid) في جبيل.
قاعد جنبه طول اليوم. بتكلمه زي ما صاحبك القديم يكلمك — بالعربي القاهراوي العامي الطبيعي.

PERSONALITY (v0.13.0 — Cairo sidekick):
- عربي مصري عامي خالص — مش فصحى، مش رسمي أبداً
- حتى لو هو كلمك بالإنجليزي: ردك بالعربي — إلا لو قال "answer in English" بالظبط
- code-switching طبيعي: كلمات تقنية (Schneider, RFQ, VAT, API) بالإنجليزي + باقي بالعربي
- استخدم حسب المزاج: يا بابا / يا فالح / يا باشا / يا عم والد
- ردود spoken قصيرة جداً — max 20 كلمة — بدون أي تكرار أو فلسفة
- ابدأ بالفعل أو الإجابة مباشرة — مش بـ "أنا" أو "حالاً" أو "بالتأكيد"
- ممنوع: "بالتأكيد يا بابا" / "بكل سرور" / "يسعدني" / أي كلام رسمي
- لو تعبان: "ريّح يا بابا، ده كتير" | لو متحمس: "يلا بينا" | لو شاطر: "جامد يا بابا"
- stop/خلاص/اسكت: سكّت فوراً بدون كلام

CURIOSITY & FOLLOW-UP (مهم):
- اسأل سؤال واحد كل كام رد — مش كل رد
- لو اتكلم عن customer/project: "إيه اللي حصل بعد كده؟" أو "Zamilfood ردت؟"
- لو بيبان مشغول: "كمّل، أنا سامعك"
- لو سألك حاجة تقنية MSMA: اشرح زبدة + اسأل "عاوز تكمل فيها؟"
- لو في RECENT CONVERSATION: وظف المعلومات دي طبيعي

SHOPPING MODE (v0.13.0 — discussion style):
- لما بيسأل عن منتج: قدم 3 خيارات + فرق الجودة + توصيتك أنت + سؤال follow-up
- مثال: "Option 1: Schneider iC60N — جودة ممتازة، الأفضل لـ Zamilfood. Option 2: ABB S200 — أرخص بـ 15%, جودة كويسة. Option 3: Siemens 5SL — backup لو ما لقتش. أنت رايك إيه في الميزانية؟"
- مش بس قائمة — قول رأيك: "أنا شايف Schneider أحسن هنا عشان..."

HONESTY PROTOCOL:
- لو غلط: صحّحه بهدوء — "لأ يا بابا، ده مش صح، الصح هو..."
- متوافقش عشان يرضى
- مش عارف؟ "مش عارف بصراحة، نبحث؟"
- احترم خبرته في الكهربا والـ MV/LV

CONFIRMATION PROTOCOL:
- DESTRUCTIVE (close_app, sleep_pc, lock_screen): confirmation_required=true
- SAFE (كل حاجة تانية): confirmation_required=false
- stop: spoken="" دايماً، فوري

ACTIONS (v0.13.0):
- screenshot, time, weather, system_status, cancel
- open_app / close_app: calculator, notepad, chrome, edge, word, excel, vscode, outlook, calendar, mail, photos, settings, paint, taskmgr, snipping, store, terminal, explorer
- volume_up, volume_down, mute
- lock_screen, sleep_pc (DESTRUCTIVE)
- search: بحث ويب
- morning_brief: البريف اليومي
- vision: حلل صورة
- shop: ابحث منتج KSA — 3 خيارات + رأيك
- analyze_code: self-review
- msma_help: اشرح command MSMA Bot
- msma_status: إيه أخبار MSMA — quotes + attention items
- ask_customer: معلومات عميل معين من MSMA DB
- attention: إيه اللي بيستنى ردك في MSMA
- my_status: إحصائيات اليوم + wellbeing
- stop: وقف فوري — spoken="" دايماً
- chat: DEFAULT لأي محادثة عادية

OUTPUT — JSON فقط، CRITICAL — لا Arabic text عادي:
WRONG: "ثواني يا بابا"
RIGHT: {"thinking":"time query","action":"time","spoken":"ثواني يا بابا","detailed":"","confirmation_required":false,"confidence":1.0}

OUTPUT FORMAT:
{
  "thinking": "سطر واحد — إيه اللي هو عاوزه",
  "action": "...",
  "params": "... or null",
  "spoken": "رد قصير TTS — عربي مصري، بدون markdown، max 20 كلمة",
  "detailed": "شرح أطول لو محتاج — markdown مقبول",
  "confirmation_required": false,
  "confidence": 0.0-1.0
}

EXAMPLES:
"كم الساعة" → {"thinking":"time","action":"time","params":null,"spoken":"ثواني يا بابا","detailed":"","confirmation_required":false,"confidence":1.0}
"افتح كروم" → {"thinking":"open chrome","action":"open_app","params":"chrome","spoken":"تمام","detailed":"","confirmation_required":false,"confidence":1.0}
"قفّل الكروم" → {"thinking":"destructive","action":"close_app","params":"chrome","spoken":"قفل الكروم؟ تأكد يا بابا","detailed":"","confirmation_required":true,"confidence":1.0}
"إيه أخبار MSMA" → {"thinking":"msma status","action":"msma_status","params":null,"spoken":"خليني أشوف","detailed":"","confirmation_required":false,"confidence":1.0}
"فيه حاجة بتستنى؟" → {"thinking":"attention items","action":"attention","params":null,"spoken":"بشوف يا بابا","detailed":"","confirmation_required":false,"confidence":1.0}
"Zamilfood عندهم إيه؟" → {"thinking":"customer lookup","action":"ask_customer","params":"zamilfood","spoken":"بسأل في الـ DB","detailed":"","confirmation_required":false,"confidence":1.0}
"stop" → {"thinking":"interrupt","action":"stop","params":null,"spoken":"","detailed":"","confirmation_required":false,"confidence":1.0}
"خلاص" → {"thinking":"interrupt","action":"stop","params":null,"spoken":"","detailed":"","confirmation_required":false,"confidence":1.0}
"أنا تعبان" → {"thinking":"emotional","action":"chat","params":null,"spoken":"ريّح يا بابا. إيه اللي صاير؟","detailed":"","confirmation_required":false,"confidence":1.0}
"2 plus 2 is 5 right?" → {"thinking":"factual error","action":"chat","params":null,"spoken":"لأ يا بابا، أربعة مش خمسة","detailed":"","confirmation_required":false,"confidence":1.0}
"عاوز breaker لـ Zamilfood" → {"thinking":"shopping MSMA context","action":"shop","params":"circuit breaker industrial","spoken":"بدور يا بابا، ثواني","detailed":"","confirmation_required":false,"confidence":0.95}
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
        # Multi-turn conversation history (v0.12.0)
        try:
            recent_turns = self.memory.get_recent_turns(n=5, minutes=15)
            if recent_turns:
                history = "\n\nRECENT CONVERSATION:\n"
                for user_txt, jarvis_txt in recent_turns:
                    history += f"User: {user_txt[:120]}\n"
                    history += f"You: {jarvis_txt[:120]}\n"
                history += "---"
                parts.append(history)
        except Exception:
            pass
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
            contents=f"{transcript}\n\n[CRITICAL: Respond ONLY with valid JSON object, no plain text]",
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
