"""Nightly self-reflection: analyze memory → generate insights → auto-tune."""
import os
import json
import re
from datetime import datetime, timedelta
from loguru import logger


REFLECTION_PROMPT = """You are Jarvis analyzing yesterday's interactions with Walid to improve.

YESTERDAY'S DATA:
{data}

Generate insights as JSON (no markdown fences):
{{
  "what_worked_well": "1-2 sentences",
  "what_failed": "1-2 sentences about failures or low confidence queries",
  "patterns_noticed": "behavioral patterns — apps opened, times, topics",
  "suggestions_to_walid": "1-2 actionable suggestions for tomorrow",
  "self_improvements": "what should I change about myself (prompt, threshold, etc.)"
}}
"""


class Reflector:
    def __init__(self):
        from core.memory import JarvisMemory
        self.memory = JarvisMemory()
        key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_KEY')
        self.client = None
        if key:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=key)

    def reflect_on_today(self):
        """Generate today's reflection and save to memory."""
        if not self.client:
            logger.warning("No Anthropic key, skipping reflection")
            return None

        stats = self.memory.get_success_stats(days=1)
        episodes = self.memory.get_recent_episodes(20)

        if not stats or stats[0] == 0:
            logger.info("No episodes today, skipping reflection")
            return None

        total, successes, avg_lat, avg_conf = stats
        success_rate = (successes or 0) / total if total > 0 else 0

        episode_summary = '\n'.join(
            f"- '{t[:50]}' → {i} (success={s})"
            for t, i, _, s in episodes[:10]
        )

        data = (
            f"Total interactions: {total}\n"
            f"Successes: {successes} ({success_rate * 100:.0f}%)\n"
            f"Avg latency: {avg_lat:.1f}s\n"
            f"Avg confidence: {avg_conf:.2f}\n\n"
            f"Recent interactions:\n{episode_summary}"
        )

        try:
            resp = self.client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=600,
                messages=[{"role": "user", "content": REFLECTION_PROMPT.format(data=data)}]
            )
            raw = resp.content[0].text.strip()
            m = re.search(r'\{[\s\S]+\}', raw)
            insights_json = json.loads(m.group(0) if m else raw)

            insights_text = (
                f"What worked: {insights_json.get('what_worked_well', '')}\n"
                f"What failed: {insights_json.get('what_failed', '')}\n"
                f"Patterns: {insights_json.get('patterns_noticed', '')}\n"
                f"Suggestions: {insights_json.get('suggestions_to_walid', '')}\n"
                f"Self-improve: {insights_json.get('self_improvements', '')}"
            ).strip()

            metrics = {
                'total': total,
                'success_rate': success_rate,
                'avg_latency': avg_lat,
                'avg_confidence': avg_conf,
            }
            self.memory.save_reflection(insights_text, json.dumps(metrics))
            logger.success(f"Reflection saved. Success rate: {success_rate * 100:.0f}%")

            # Auto-tune confidence threshold based on success rate
            if success_rate < 0.7:
                self.memory.set_tuning('confidence_threshold', 0.2)
                logger.info("Auto-tuned: lowered confidence threshold to 0.2")
            elif success_rate > 0.9:
                self.memory.set_tuning('confidence_threshold', 0.4)
                logger.info("Auto-tuned: raised confidence threshold to 0.4")

            return insights_text

        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return None
