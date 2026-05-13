"""Phase 3 regression tests — no mic, no TTS, no network."""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_actions_import():
    from actions.safe_actions import SafeActions, execute, ACTION_MAP
    assert SafeActions is not None
    assert 'screenshot' in ACTION_MAP
    assert 'time' in ACTION_MAP
    assert 'open_app' in ACTION_MAP
    assert 'search' in ACTION_MAP
    assert 'cancel' in ACTION_MAP
    assert 'system_status' in ACTION_MAP


def test_screenshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from actions.safe_actions import SafeActions
    actions = SafeActions()
    actions.speak_sync = lambda *a, **kw: None  # silence TTS
    result = actions.screenshot()
    assert result['success'] is True
    assert Path(result['path']).exists()


def test_time_action():
    from actions.safe_actions import SafeActions
    actions = SafeActions()
    actions.speak_sync = lambda *a, **kw: None
    result = actions.time()
    assert result['success'] is True
    assert result['action'] == 'time'
    assert 'value' in result


def test_open_app_whitelisted():
    from actions.safe_actions import SafeActions
    import unittest.mock as mock
    actions = SafeActions()
    actions.speak_sync = lambda *a, **kw: None
    with mock.patch('subprocess.Popen') as mock_popen:
        result = actions.open_app(transcript='open calculator')
    assert result['success'] is True
    assert result['app'] == 'calculator'


def test_open_app_not_whitelisted():
    from actions.safe_actions import SafeActions
    actions = SafeActions()
    actions.speak_sync = lambda *a, **kw: None
    result = actions.open_app(transcript='open malware.exe')
    assert result['success'] is False
    assert result['error'] == 'not whitelisted'


def test_execute_dispatch_time():
    from actions.safe_actions import execute, SafeActions
    actions = SafeActions()
    actions.speak_sync = lambda *a, **kw: None
    intent = {'intent': 'time', 'confidence': 0.5, 'raw_text': 'what time is it'}
    result = execute(intent, actions)
    assert result['action'] == 'time'
    assert result['success'] is True


def test_execute_unknown_blocked():
    from actions.safe_actions import execute, SafeActions
    actions = SafeActions()
    intent = {'intent': 'unknown', 'confidence': 0.0, 'raw_text': 'xyz'}
    result = execute(intent, actions)
    assert result['success'] is False


def test_cancel():
    from actions.safe_actions import SafeActions
    actions = SafeActions()
    actions.speak_sync = lambda *a, **kw: None
    result = actions.cancel()
    assert result['success'] is True
    assert result['action'] == 'cancel'
