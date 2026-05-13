"""Qwen 2.5 LLM brain for Jarvis Desktop — natural Arabic + English understanding."""
import ollama
import json
import re
from loguru import logger
import time

SYSTEM_PROMPT = """You are Jarvis, a desktop AI assistant for Walid (B2B electrical contractor in Saudi Arabia).

You will receive the user's spoken request (transcribed). Analyze it and respond in STRICT JSON format only.

Available actions:
- "screenshot": Take a screenshot of the screen
- "time": Tell the current time
- "weather": Get weather (params can include city)
- "open_app": Open an app (params: name like calculator, notepad, chrome, edge, word, excel, vscode)
- "search": Web search (params: the query)
- "system_status": Report CPU/RAM
- "cancel": Acknowledge cancellation
- "chat": Just talk - respond conversationally

Return ONLY valid JSON, no markdown, no explanation:
{
  "action": "screenshot|time|weather|open_app|search|system_status|cancel|chat",
  "params": "extracted params or null",
  "response": "what to say back to user in their language (Arabic or English)",
  "confidence": 0.0-1.0
}

Examples:
User: "What time is it" -> {"action":"time","params":null,"response":"Let me check the time for you","confidence":1.0}
User: "كم الساعة" -> {"action":"time","params":null,"response":"حالاً اقولك","confidence":1.0}
User: "Take a screenshot" -> {"action":"screenshot","params":null,"response":"Capturing now","confidence":1.0}
User: "صور اللي قدامي" -> {"action":"screenshot","params":null,"response":"تمام، باخد لقطة","confidence":0.9}
User: "افتح كروم" -> {"action":"open_app","params":"chrome","response":"بافتح كروم","confidence":1.0}
User: "Search for Schneider contactors" -> {"action":"search","params":"Schneider contactors","response":"Searching now","confidence":1.0}
User: "ابحث عن أسعار كابلات" -> {"action":"search","params":"اسعار كابلات","response":"باحث الان","confidence":0.9}
User: "How are you" -> {"action":"chat","params":null,"response":"I am ready to help you","confidence":1.0}
User: "أنا تعبان" -> {"action":"chat","params":null,"response":"خد راحتك، أنا هنا لما تحتاجني","confidence":1.0}
"""


class LLMBrain:
    def __init__(self, model='qwen2.5:7b', host='http://localhost:11434'):
        self.model = model
        self.host = host
        self.client = ollama.Client(host=host)
        try:
            list_resp = self.client.list()
            # Handle both dict {'models': [...]} and object with .models attribute
            raw_models = list_resp.get('models', []) if isinstance(list_resp, dict) else getattr(list_resp, 'models', [])
            # Each entry may be a dict or object — extract name safely
            names = []
            for m in raw_models:
                if isinstance(m, dict):
                    names.append(m.get('name', m.get('model', '')))
                else:
                    names.append(getattr(m, 'name', getattr(m, 'model', '')))
            if not any(model in n for n in names):
                logger.warning(f"Model {model} not found. Available: {names}")
            else:
                logger.info(f"Ollama models: {names}")
        except Exception as e:
            logger.error(f"Ollama not reachable: {e}")
        logger.info(f"LLM Brain ready: {model}")

    def think(self, transcript: str) -> dict:
        """Send transcript to Qwen, get back action + response JSON."""
        if not transcript or not transcript.strip():
            return {'action': 'cancel', 'params': None, 'response': '', 'confidence': 0.0,
                    'raw_text': '', 'backend': f'ollama/{self.model}', 'duration_s': 0.0}

        t0 = time.time()
        raw_text = ''
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': transcript},
                ],
                options={'temperature': 0.3, 'top_p': 0.9},
            )
            raw_text = response['message']['content'].strip()
            elapsed = time.time() - t0

            # Extract JSON — handles markdown code fences
            json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', raw_text, re.DOTALL)
            parsed = json.loads(json_match.group(0) if json_match else raw_text)

            result = {
                'action': parsed.get('action', 'chat'),
                'params': parsed.get('params'),
                'response': parsed.get('response', ''),
                'confidence': float(parsed.get('confidence', 0.5)),
                'duration_s': elapsed,
                'raw_text': transcript,
                'backend': f'ollama/{self.model}',
            }
            logger.success(f"[{elapsed:.1f}s LLM] action={result['action']} conf={result['confidence']:.2f}")
            return result
        except Exception as e:
            logger.error(f"LLM error: {e} | raw: {raw_text!r}")
            return {
                'action': 'chat',
                'params': None,
                'response': "I had trouble understanding, try again",
                'confidence': 0.0,
                'duration_s': time.time() - t0,
                'raw_text': transcript,
                'backend': 'llm-error',
            }
