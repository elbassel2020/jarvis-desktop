"""Shopping assistant — search KSA electrical suppliers."""
import os, time
from loguru import logger

SHOP_PROMPT = """You are Jarvis helping Walid (B2B electrical contractor in Jubail, KSA) find products.

Query: "{query}"

Use web search to find:
1. Best 3 options with prices in SAR
2. KSA suppliers (Microless, RS Components, Mepco, Schneider distributors)
3. Lead time + availability
4. Alternative brands if Schneider/ABB unavailable

Return in Arabic, casual conversational, max 80 words. Format:
1. Brand/model — Price SAR — Supplier — Lead time
2. ...
3. ...
+ recommendation"""


class ShoppingAssistant:
    def __init__(self):
        key = os.getenv('ANTHROPIC_API_KEY')
        if key:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=key)
        else:
            self.client = None

    def search(self, query: str) -> dict:
        if not self.client:
            return {'error': 'No key', 'success': False}
        try:
            t0 = time.time()
            response = self.client.messages.create(
                model='claude-sonnet-4-6', max_tokens=500,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                messages=[{"role": "user", "content": SHOP_PROMPT.format(query=query)}]
            )
            text_parts = [b.text for b in response.content if hasattr(b, 'text')]
            results = ' '.join(text_parts).strip()
            elapsed = time.time() - t0
            logger.success(f"Shop: [{elapsed:.1f}s] for '{query[:50]}'")
            return {
                'results': results,
                'query': query,
                'duration_s': elapsed,
                'success': True
            }
        except Exception as e:
            logger.error(f"Shop search: {e}")
            return {'error': str(e), 'success': False}
