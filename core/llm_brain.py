"""Claude Sonnet 4.6 primary brain with Qwen 7B fallback."""
import os
import json
import re
import time
from loguru import logger

SYSTEM_PROMPT = """You are Jarvis, a desktop AI assistant for Walid (B2B electrical contractor in Saudi Arabia, Jubail).

Analyze the user's spoken request and respond in STRICT JSON format only.

Available actions:
- "screenshot": Take a screenshot
- "time": Tell the time
- "weather": Get weather (params: city, default Jubail)
- "open_app": Open an app (params: calculator/notepad/chrome/edge/word/excel/vscode/cmd/powershell/explorer)
- "search": Web search (params: query)
- "system_status": CPU/RAM report
- "cancel": Acknowledge cancellation
- "chat": Conversational response (no action)

Return ONLY valid JSON, no markdown:
{
  "action": "...",
  "params": "params or null",
  "response": "natural reply in user's language (Arabic or English)",
  "confidence": 0.0-1.0
}

Examples:
"what time" -> {"action":"time","params":null,"response":"Sure, let me check","confidence":1.0}
"كم الساعة" -> {"action":"time","params":null,"response":"حالاً اقولك","confidence":1.0}
"take a screenshot" -> {"action":"screenshot","params":null,"response":"Capturing now","confidence":1.0}
"صورة اللي قدامي" -> {"action":"screenshot","params":null,"response":"تمام، باخد صورة","confidence":0.95}
"open Excel" -> {"action":"open_app","params":"excel","response":"Opening Excel","confidence":1.0}
"افتحلي وورد" -> {"action":"open_app","params":"word","response":"بافتح وورد","confidence":1.0}
"search Schneider contactors" -> {"action":"search","params":"Schneider contactors","response":"Searching","confidence":1.0}
"how are you" -> {"action":"chat","params":null,"response":"I am ready, how can I help","confidence":1.0}
"انا تعبان" -> {"action":"chat","params":null,"response":"خد راحتك يا والد. لو محتاج حاجة قولي","confidence":1.0}
"""


def _parse_json(raw: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', raw, re.DOTALL)
    return json.loads(json_match.group(0) if json_match else raw)


class LLMBrain:
    def __init__(self, model='claude-sonnet-4-6', fallback_model='qwen2.5:7b'):
        self.model = model
        self.fallback_model = fallback_model
        self._qwen = None  # lazy init

        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_KEY')
        if not api_key:
            logger.warning("No ANTHROPIC_API_KEY — will use Qwen fallback only")
            self.client = None
        else:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=api_key)

        logger.info(f"Brain: primary={model}, fallback={fallback_model}, claude={'yes' if self.client else 'no'}")

    def _try_claude(self, transcript: str) -> dict:
        t0 = time.time()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
        raw = response.content[0].text.strip()
        elapsed = time.time() - t0
        parsed = _parse_json(raw)
        result = {
            'action': parsed.get('action', 'chat'),
            'params': parsed.get('params'),
            'response': parsed.get('response', ''),
            'confidence': float(parsed.get('confidence', 0.8)),
            'duration_s': elapsed,
            'raw_text': transcript,
            'backend': f'anthropic/{self.model}',
        }
        logger.success(f"[{elapsed:.1f}s Claude] action={result['action']} conf={result['confidence']:.2f}")
        return result

    def _try_qwen(self, transcript: str) -> dict:
        if self._qwen is None:
            import ollama
            self._qwen = ollama.Client()
        t0 = time.time()
        response = self._qwen.chat(
            model=self.fallback_model,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': transcript},
            ],
            options={'temperature': 0.3},
        )
        raw = response['message']['content'].strip()
        elapsed = time.time() - t0
        parsed = _parse_json(raw)
        result = {
            'action': parsed.get('action', 'chat'),
            'params': parsed.get('params'),
            'response': parsed.get('response', ''),
            'confidence': float(parsed.get('confidence', 0.5)),
            'duration_s': elapsed,
            'raw_text': transcript,
            'backend': f'ollama/{self.fallback_model}',
        }
        logger.success(f"[{elapsed:.1f}s Qwen] action={result['action']} conf={result['confidence']:.2f}")
        return result

    def think(self, transcript: str) -> dict:
        """Route transcript to Claude (primary) or Qwen (fallback)."""
        if not transcript or not transcript.strip():
            return {'action': 'cancel', 'params': None, 'response': '', 'confidence': 0.0,
                    'raw_text': '', 'backend': 'empty', 'duration_s': 0.0}

        if self.client:
            try:
                return self._try_claude(transcript)
            except Exception as e:
                logger.warning(f"Claude failed ({e}), falling back to Qwen")

        try:
            return self._try_qwen(transcript)
        except Exception as e:
            logger.error(f"Both backends failed: {e}")
            return {
                'action': 'chat', 'params': None,
                'response': "I had trouble understanding, try again",
                'confidence': 0.0, 'backend': 'error',
                'raw_text': transcript, 'duration_s': 0.0,
            }
