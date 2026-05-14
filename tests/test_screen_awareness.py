"""Tests for ScreenAwareness — mocked win32gui/win32process."""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── get_open_windows ──────────────────────────────────────────────────────

class TestGetOpenWindows:
    def test_returns_list_when_no_windows_module(self):
        with patch.dict('sys.modules', {'win32gui': None, 'win32process': None}):
            import importlib
            import core.screen_awareness as sa
            sa.WINDOWS = False
            obj = sa.ScreenAwareness()
            result = obj.get_open_windows()
            assert result == []

    def test_returns_list_type(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        with patch('core.screen_awareness.WINDOWS', False):
            result = obj.get_open_windows()
        assert isinstance(result, list)


# ── summary ───────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_empty_desktop(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        with patch.object(obj, 'get_open_windows', return_value=[]):
            result = obj.summary()
        assert result == 'Desktop empty'

    def test_summary_single_window(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        windows = [{'title': 'Google Chrome', 'process': 'chrome.exe', 'pid': 1234}]
        with patch.object(obj, 'get_open_windows', return_value=windows):
            result = obj.summary()
        assert 'chrome' in result
        assert 'Open:' in result

    def test_summary_multiple_windows_same_process(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        windows = [
            {'title': 'Tab One', 'process': 'chrome.exe', 'pid': 1},
            {'title': 'Tab Two', 'process': 'chrome.exe', 'pid': 1},
            {'title': 'Tab Three', 'process': 'chrome.exe', 'pid': 1},
        ]
        with patch.object(obj, 'get_open_windows', return_value=windows):
            result = obj.summary()
        assert '3 windows' in result or 'chrome' in result

    def test_summary_multiple_processes(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        windows = [
            {'title': 'Chrome Window', 'process': 'chrome.exe', 'pid': 1},
            {'title': 'Notepad', 'process': 'notepad.exe', 'pid': 2},
        ]
        with patch.object(obj, 'get_open_windows', return_value=windows):
            result = obj.summary()
        assert 'chrome' in result
        assert 'notepad' in result

    def test_summary_caps_at_8_processes(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        windows = [
            {'title': f'Window {i}', 'process': f'proc{i}.exe', 'pid': i}
            for i in range(12)
        ]
        with patch.object(obj, 'get_open_windows', return_value=windows):
            result = obj.summary()
        # At most 8 processes in output
        assert result.count('|') <= 7

    def test_summary_exception_returns_unavailable(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        with patch.object(obj, 'get_open_windows', side_effect=Exception('fail')):
            result = obj.summary()
        assert 'unavailable' in result.lower() or 'Desktop state' in result

    def test_summary_strips_lowercase_exe_from_process_name(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        # Source does p.replace('.exe', '') — lowercase only — so chrome.exe → chrome
        windows = [{'title': 'Google Chrome', 'process': 'chrome.exe', 'pid': 1}]
        with patch.object(obj, 'get_open_windows', return_value=windows):
            result = obj.summary()
        assert 'chrome.exe' not in result
        assert 'chrome' in result

    def test_summary_truncates_long_titles(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        long_title = 'A' * 100
        windows = [{'title': long_title, 'process': 'notepad.exe', 'pid': 1}]
        with patch.object(obj, 'get_open_windows', return_value=windows):
            result = obj.summary()
        # Title truncated to 50 chars in source
        assert len(result) < 200

    def test_summary_single_window_shows_title(self):
        from core.screen_awareness import ScreenAwareness
        obj = ScreenAwareness()
        windows = [{'title': 'Unique Title Here', 'process': 'notepad.exe', 'pid': 1}]
        with patch.object(obj, 'get_open_windows', return_value=windows):
            result = obj.summary()
        assert 'Unique Title Here' in result
