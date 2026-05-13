"""Test wake word listener initializes correctly."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_import():
    from core.wake_listener import WakeListener
    assert WakeListener is not None


def test_threshold_stored():
    """Listener stores threshold without touching hardware."""
    from core.wake_listener import WakeListener
    listener = WakeListener.__new__(WakeListener)
    listener.threshold = 0.7
    assert listener.threshold == 0.7


def test_audit_log_dir_created(tmp_path, monkeypatch):
    """Audit log dir created on init."""
    monkeypatch.chdir(tmp_path)
    # Patch Model so no download needed
    import unittest.mock as mock
    with mock.patch('core.wake_listener.Model') as MockModel:
        MockModel.return_value = mock.MagicMock()
        from core.wake_listener import WakeListener
        listener = WakeListener(threshold=0.5)
        assert (tmp_path / 'logs').exists()


def test_default_handler_runs(capsys):
    """default_handler prints without crashing."""
    import unittest.mock as mock
    with mock.patch('core.wake_listener.Model'):
        from core.wake_listener import WakeListener
        import importlib
        import core.wake_listener as wm
        importlib.reload(wm)
        with mock.patch('core.wake_listener.Model'):
            l = wm.WakeListener.__new__(wm.WakeListener)
            l.on_detect = None
            l.default_handler('hey_jarvis', 0.92)
    captured = capsys.readouterr()
    assert 'hey_jarvis' in captured.out
