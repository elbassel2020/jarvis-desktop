"""Daily self-learning: 6 AM web search → insights → morning brief."""
import os
import json
import time
from datetime import datetime
from loguru import logger
import anthropic

LEARNING_QUERIES = [
    ('electrical_standards', 'Saudi Arabia IEC electrical standards updates 2025 2026'),
    ('zatca', 'ZATCA e-invoicing Phase 2 updates penalties 2025 2026'),
    ('schneider', 'Schneider Electric Saudi Arabia distributor price update 2025'),
    ('energy_prices', 'Saudi Arabia electricity tariff industrial 2025'),
    ('procurement', 'B2B procurement electrical contractor Saudi Arabia tips'),
    ('currency', 'USD SAR exchange rate trend 2025'),
    ('business_news', 'Jubail industrial city business news contracts 2025'),
]

BRIEF_PROMPT = """You are Jarvis, personal AI for Walid Al-Bassel (electrical contractor, Jubail KSA).
Given the following learning insights gathered today, write a concise morning brief (max 150 words).
Focus on anything actionable for his B2B electrical contracting business (MSMA Group).
Mention ZATCA, pricing, or procurement news if present. Be direct, no fluff.

INSIGHTS:
{insights}

Write the brief in mixed Arabic/English like Walid speaks. Start with a greeting like "صباح الخير يابابا"."""


class DailyLearner:
    def __init__(self, memory=None):
        self._client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        if memory is None:
            from core.memory import JarvisMemory
            self.memory = JarvisMemory()
        else:
            self.memory = memory

    def _search_one(self, category: str, query: str) -> dict | None:
        """Run a single web search via Claude with web_search tool."""
        try:
            resp = self._client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=400,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
                messages=[{
                    "role": "user",
                    "content": (
                        f"Search for: {query}\n"
                        "Summarize the most relevant finding in 2-3 sentences. "
                        "Include the source URL if available."
                    )
                }],
            )
            # Extract text blocks (may follow ToolUseBlock)
            summary = ''
            source_url = ''
            for block in resp.content:
                if hasattr(block, 'text'):
                    summary += block.text
                elif hasattr(block, 'type') and block.type == 'tool_result':
                    pass
            summary = summary.strip()
            if not summary:
                return None
            # Best-effort URL extraction
            import re
            urls = re.findall(r'https?://[^\s\)\"\']+', summary)
            source_url = urls[0] if urls else ''
            return {'category': category, 'query': query, 'summary': summary, 'source_url': source_url}
        except Exception as e:
            logger.warning(f"Learning search failed [{category}]: {e}")
            return None

    def run(self):
        logger.info("Daily learning started")
        gathered = []
        for category, query in LEARNING_QUERIES:
            result = self._search_one(category, query)
            if result:
                self.memory.add_insight(
                    category=result['category'],
                    query=result['query'],
                    summary=result['summary'],
                    source_url=result['source_url'],
                )
                gathered.append(result)
                logger.info(f"  Learned [{category}]: {result['summary'][:80]}...")
            time.sleep(2)  # polite pacing

        if not gathered:
            logger.warning("No insights gathered today")
            return

        # Generate morning brief
        try:
            insights_text = '\n'.join(
                f"[{r['category']}] {r['summary']}" for r in gathered
            )
            resp = self._client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": BRIEF_PROMPT.format(insights=insights_text)
                }]
            )
            brief = resp.content[0].text.strip()
            self.memory.save_morning_brief(brief)
            logger.info(f"Morning brief saved ({len(brief)} chars)")
        except Exception as e:
            logger.error(f"Brief generation failed: {e}")


if __name__ == '__main__':
    DailyLearner().run()
