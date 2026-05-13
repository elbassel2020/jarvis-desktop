"""Classify voice command intent from transcribed text."""
from loguru import logger

INTENT_KEYWORDS = {
    'system_status': ['status', 'health', 'check', 'حالة', 'الوضع'],
    'screenshot':    ['screenshot', 'screen', 'كاب', 'لقطة', 'صورة شاشة'],
    'time':          ['time', 'what time', 'الساعة', 'وقت'],
    'weather':       ['weather', 'الجو', 'الطقس'],
    'open_app':      ['open', 'launch', 'start', 'افتح', 'شغل'],
    'msma_query':    ['msma', 'quote', 'customer', 'rfq', 'عرض سعر', 'عميل'],
    'msma_email':    ['send email', 'reply', 'ابعت ايميل', 'رد'],
    'memory_recall': ['remember', 'recall', 'last', 'فاكر', 'تذكر'],
    'search':        ['search', 'google', 'find', 'ابحث', 'دور'],
    'cancel':        ['cancel', 'stop', 'never mind', 'الغي', 'مش عاوز'],
}


class IntentParser:
    def __init__(self):
        self.history = []

    def parse(self, text: str) -> dict:
        """Match text against intent keywords. Returns {intent, confidence, raw_text, all_scores}."""
        text_lower = text.lower().strip()

        scores = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent] = score

        if scores:
            top_intent = max(scores, key=scores.get)
            confidence = min(scores[top_intent] / 2.0, 1.0)
        else:
            top_intent = 'unknown'
            confidence = 0.0

        result = {
            'intent': top_intent,
            'confidence': confidence,
            'raw_text': text,
            'all_scores': scores,
        }
        self.history.append(result)
        logger.info(f"Intent: {top_intent} ({confidence:.2f})")
        return result
