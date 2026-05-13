"""Phase 2 regression tests — no mic or Whisper download required."""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_voice_capture_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.voice_capture import VoiceCapture
    vc = VoiceCapture(duration=5)
    assert vc.duration == 5
    assert vc.captures_dir.exists()


def test_intent_screenshot():
    from core.intent_parser import IntentParser
    p = IntentParser()
    r = p.parse("take a screenshot please")
    assert r['intent'] == 'screenshot'


def test_intent_arabic_open():
    from core.intent_parser import IntentParser
    p = IntentParser()
    r = p.parse("افتح كروم")
    assert r['intent'] == 'open_app'


def test_intent_unknown():
    from core.intent_parser import IntentParser
    p = IntentParser()
    r = p.parse("xyz random words 123")
    assert r['intent'] == 'unknown'
    assert r['confidence'] == 0.0


def test_intent_msma_query():
    from core.intent_parser import IntentParser
    p = IntentParser()
    r = p.parse("show me MSMA quote for SMI")
    assert r['intent'] == 'msma_query'


def test_intent_history():
    from core.intent_parser import IntentParser
    p = IntentParser()
    p.parse("what time is it")
    p.parse("take screenshot")
    assert len(p.history) == 2
