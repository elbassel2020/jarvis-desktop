"""Shopping assistant — search KSA electrical suppliers."""
import os, time
from loguru import logger

SHOP_PROMPT = """أنت Jarvis، بتساعد والد (Walid) — B2B electrical contractor في جبيل، KSA.
والد بيشتغل مع Zamilfood (أهم عميل، cash)، SMI، Olayan، BHIG.
Preferred brands: Schneider > ABB > Siemens.

طلب البحث: "{query}"

استخدم web search وقدّم:

**Option 1:** [Brand/model] — السعر SAR — المورد في KSA — وقت التوصيل
**Option 2:** [brand أرخص أو بديل] — السعر — المورد — التوصيل
**Option 3:** [backup option] — السعر — المورد — التوصيل

**فرق الجودة:** جملة واحدة بتفرق بين الخيارات

**توصيتي:** قول رأيك بصراحة — إيه الأنسب لـ Walid وليه

**سؤال follow-up:** سؤال واحد عملي (الميزانية؟ الكمية؟ للمشروع ده أو حاجة ثانية؟)

ردك بالعربي العامي المصري — casual، max 120 كلمة — مش فصحى."""


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
