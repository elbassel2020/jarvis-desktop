"""LLM brain — thin wrapper over BrainRouter (v0.6.0)."""
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
    """Thin wrapper — delegates to BrainRouter for multi-LLM routing (v0.6.0)."""

    def __init__(self, model='qwen2.5:7b', fallback_model='qwen2.5:7b'):
        self.model = model
        self.fallback_model = fallback_model
        from core.brain_router import BrainRouter
        self._router = BrainRouter()

    def think(self, transcript: str) -> dict:
        """Route transcript through BrainRouter (Gemini/Claude/Qwen by complexity)."""
        return self._router.think(transcript)
