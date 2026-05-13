"""Phase 4 LLM brain tests — requires Ollama + qwen2.5:7b running."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_brain_import():
    from core.llm_brain import LLMBrain
    assert LLMBrain is not None


def test_brain_init():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    assert b.model == 'qwen2.5:7b'


def test_brain_time_en():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    r = b.think('what time is it')
    assert r['action'] == 'time', f"Expected 'time', got {r['action']}"
    assert r['confidence'] > 0


def test_brain_screenshot_ar():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    r = b.think('خد لقطة شاشة')
    assert r['action'] == 'screenshot', f"Expected 'screenshot', got {r['action']}"


def test_brain_search_en():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    r = b.think('search for Schneider contactors')
    assert r['action'] == 'search', f"Expected 'search', got {r['action']}"
    assert r['params'] is not None


def test_brain_open_app():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    r = b.think('open calculator')
    assert r['action'] == 'open_app', f"Expected 'open_app', got {r['action']}"


def test_brain_arabic_open():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    r = b.think('افتح كروم')
    assert r['action'] == 'open_app', f"Expected 'open_app', got {r['action']}"


def test_brain_chat():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    r = b.think('how are you')
    assert r['action'] == 'chat'
    assert len(r['response']) > 0


def test_brain_empty():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    r = b.think('')
    assert r['action'] in ('cancel', 'chat')
