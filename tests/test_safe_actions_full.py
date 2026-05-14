"""Comprehensive tests for SafeActions — all methods mocked."""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def mock_pygame():
    with patch('pygame.mixer.init'), \
         patch('pygame.mixer.music') as m:
        yield m


@pytest.fixture
def actions(tmp_path):
    with patch('actions.safe_actions.Path') as mock_path:
        mock_path.return_value.mkdir = MagicMock()
        from actions.safe_actions import SafeActions
        sa = SafeActions.__new__(SafeActions)
        sa.screenshots_dir = tmp_path / 'screenshots'
        sa.screenshots_dir.mkdir()
        sa.tts_dir = tmp_path / 'tts'
        sa.tts_dir.mkdir()
        sa.allowed_apps = {
            'calculator': 'calc.exe', 'calc': 'calc.exe',
            'notepad': 'notepad.exe',
            'chrome': 'chrome.exe',
            'edge': 'msedge.exe',
            'explorer': 'explorer.exe', 'files': 'explorer.exe',
            'cmd': 'cmd.exe',
            'terminal': 'wt.exe',
            'powershell': 'powershell.exe',
            'vscode': 'code.exe', 'code': 'code.exe',
            'word': 'winword.exe',
            'excel': 'excel.exe',
            'outlook': 'outlook.exe',
            'paint': 'mspaint.exe',
            'taskmgr': 'taskmgr.exe',
            'settings': 'ms-settings:',
            'calendar': 'outlookcal:',
            'mail': 'outlookmail:',
            'photos': 'ms-photos:',
            'store': 'ms-windows-store:',
            'snipping': 'snippingtool.exe',
        }
        return sa


# ── speak ─────────────────────────────────────────────────────────────────

class TestSpeak:
    def test_speak_uses_elevenlabs_when_key_present(self, actions):
        with patch.object(actions, '_speak_elevenlabs', return_value=Path('/tmp/x.mp3')) as el, \
             patch('os.getenv', return_value='fake-eleven-key'), \
             patch('pygame.mixer.music.load'), \
             patch('pygame.mixer.music.play'), \
             patch('pygame.mixer.music.get_busy', return_value=False):
            actions.speak('hello')
        el.assert_called_once_with('hello')

    def test_speak_falls_back_to_edge_tts_on_elevenlabs_fail(self, actions):
        with patch.object(actions, '_speak_elevenlabs', side_effect=Exception('no key')), \
             patch.object(actions, '_speak_edge_async') as edge, \
             patch('asyncio.run', return_value=Path('/tmp/x.mp3')), \
             patch('pygame.mixer.music.load'), \
             patch('pygame.mixer.music.play'), \
             patch('pygame.mixer.music.get_busy', return_value=False):
            actions.speak('test')

    def test_speak_returns_none_on_total_failure(self, actions):
        with patch.object(actions, '_speak_elevenlabs', side_effect=Exception('fail')), \
             patch('asyncio.run', side_effect=Exception('fail')):
            result = actions.speak('test')
        assert result is None

    def test_speak_no_elevenlabs_key_skips_to_edge(self, actions):
        with patch.dict(os.environ, {}, clear=True), \
             patch('os.getenv', return_value=None), \
             patch('asyncio.run', return_value=Path('/tmp/x.mp3')), \
             patch('pygame.mixer.music.load'), \
             patch('pygame.mixer.music.play'), \
             patch('pygame.mixer.music.get_busy', return_value=False):
            actions.speak('hello')  # should not raise


# ── time ──────────────────────────────────────────────────────────────────

class TestTime:
    def test_time_returns_dict(self, actions):
        with patch.object(actions, 'speak'):
            result = actions.time()
        assert isinstance(result, dict)

    def test_time_action_key(self, actions):
        with patch.object(actions, 'speak'):
            result = actions.time()
        assert result['action'] == 'time'

    def test_time_success_true(self, actions):
        with patch.object(actions, 'speak'):
            result = actions.time()
        assert result['success'] is True

    def test_time_value_is_iso(self, actions):
        with patch.object(actions, 'speak'):
            result = actions.time()
        assert 'T' in result['value'] or ':' in result['value']

    def test_time_speaks_time_string(self, actions):
        spoken = []
        with patch.object(actions, 'speak', side_effect=lambda t: spoken.append(t)):
            actions.time()
        assert len(spoken) == 1
        assert 'time' in spoken[0].lower() or ':' in spoken[0]


# ── weather ───────────────────────────────────────────────────────────────

class TestWeather:
    def test_weather_success(self, actions):
        mock_resp = MagicMock()
        mock_resp.text = 'Jubail: ☀️ +35°C'
        with patch('requests.get', return_value=mock_resp), \
             patch.object(actions, 'speak'):
            result = actions.weather()
        assert result['success'] is True

    def test_weather_action_key(self, actions):
        mock_resp = MagicMock()
        mock_resp.text = 'Jubail: ☀️ +35°C'
        with patch('requests.get', return_value=mock_resp), \
             patch.object(actions, 'speak'):
            result = actions.weather()
        assert result['action'] == 'weather'

    def test_weather_failure_returns_false(self, actions):
        with patch('requests.get', side_effect=Exception('timeout')):
            result = actions.weather()
        assert result['success'] is False

    def test_weather_failure_has_error_key(self, actions):
        with patch('requests.get', side_effect=Exception('timeout')):
            result = actions.weather()
        assert 'error' in result


# ── open_app ──────────────────────────────────────────────────────────────

class TestOpenApp:
    def test_open_app_no_transcript(self, actions):
        result = actions.open_app(None)
        assert result['success'] is False

    def test_open_app_unknown_app(self, actions):
        with patch.object(actions, 'speak'):
            result = actions.open_app('open foobar unknown')
        assert result['success'] is False
        assert 'not whitelisted' in result.get('error', '')

    def test_open_app_calculator(self, actions):
        with patch('subprocess.Popen') as mock_popen, \
             patch.object(actions, 'speak'), \
             patch('core.memory.JarvisMemory', side_effect=Exception('no db')):
            result = actions.open_app('open calculator')
        assert result['success'] is True
        assert result['app'] == 'calculator'

    def test_open_app_chrome(self, actions):
        with patch('subprocess.Popen'), \
             patch.object(actions, 'speak'), \
             patch('core.memory.JarvisMemory', side_effect=Exception('no db')):
            result = actions.open_app('open chrome browser')
        assert result['success'] is True
        assert result['app'] == 'chrome'

    def test_open_app_ms_uri(self, actions):
        with patch('os.startfile') as mock_sf, \
             patch.object(actions, 'speak'), \
             patch('core.memory.JarvisMemory', side_effect=Exception('no db')):
            result = actions.open_app('open settings')
        mock_sf.assert_called_once()
        assert result['success'] is True

    def test_open_app_excel(self, actions):
        with patch('subprocess.Popen'), \
             patch.object(actions, 'speak'), \
             patch('core.memory.JarvisMemory', side_effect=Exception('no db')):
            result = actions.open_app('افتحلي excel')
        assert result['success'] is True

    def test_open_app_logs_to_memory_on_success(self, actions):
        mock_mem = MagicMock()
        with patch('subprocess.Popen'), \
             patch.object(actions, 'speak'), \
             patch('core.memory.JarvisMemory', return_value=mock_mem):
            actions.open_app('open notepad')
        mock_mem.log_app_open.assert_called_once()


# ── close_app ─────────────────────────────────────────────────────────────

class TestCloseApp:
    def test_close_app_no_transcript(self, actions):
        result = actions.close_app(None)
        assert result['success'] is False

    def test_close_app_unknown(self, actions):
        with patch.object(actions, 'speak'):
            result = actions.close_app('close unknownapp123')
        assert result['success'] is False
        assert 'no match' in result.get('error', '')

    def test_close_app_chrome(self, actions):
        with patch('subprocess.run'), \
             patch.object(actions, 'speak'):
            result = actions.close_app('close chrome')
        assert result['success'] is True
        assert result['app'] == 'chrome'

    def test_close_app_excel(self, actions):
        with patch('subprocess.run'), \
             patch.object(actions, 'speak'):
            result = actions.close_app('close excel')
        assert result['success'] is True

    def test_close_app_calls_taskkill(self, actions):
        with patch('subprocess.run') as mock_run, \
             patch.object(actions, 'speak'):
            actions.close_app('close notepad')
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert 'taskkill' in args


# ── volume controls ───────────────────────────────────────────────────────

class TestVolumeControls:
    def test_volume_up_success(self, actions):
        with patch('subprocess.run'), \
             patch.object(actions, 'speak'):
            result = actions.volume_up()
        assert result['success'] is True
        assert result['action'] == 'volume_up'

    def test_volume_down_success(self, actions):
        with patch('subprocess.run'), \
             patch.object(actions, 'speak'):
            result = actions.volume_down()
        assert result['success'] is True
        assert result['action'] == 'volume_down'

    def test_mute_success(self, actions):
        with patch('subprocess.run'), \
             patch.object(actions, 'speak'):
            result = actions.mute()
        assert result['success'] is True
        assert result['action'] == 'mute'

    def test_volume_up_calls_powershell(self, actions):
        with patch('subprocess.run') as mock_run, \
             patch.object(actions, 'speak'):
            actions.volume_up()
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert 'powershell' in cmd[0].lower()

    def test_volume_down_calls_powershell(self, actions):
        with patch('subprocess.run') as mock_run, \
             patch.object(actions, 'speak'):
            actions.volume_down()
        assert mock_run.called


# ── lock/sleep ────────────────────────────────────────────────────────────

class TestLockSleep:
    def test_lock_screen_success(self, actions):
        with patch('subprocess.run'), \
             patch.object(actions, 'speak'):
            result = actions.lock_screen()
        assert result['success'] is True
        assert result['action'] == 'lock_screen'

    def test_sleep_pc_success(self, actions):
        with patch('subprocess.run'), \
             patch.object(actions, 'speak'):
            result = actions.sleep_pc()
        assert result['success'] is True
        assert result['action'] == 'sleep_pc'

    def test_lock_screen_calls_rundll32(self, actions):
        with patch('subprocess.run') as mock_run, \
             patch.object(actions, 'speak'):
            actions.lock_screen()
        cmd = mock_run.call_args[0][0]
        assert 'rundll32' in cmd[0].lower() or 'rundll32' in ' '.join(cmd).lower()

    def test_sleep_pc_calls_powrprof(self, actions):
        with patch('subprocess.run') as mock_run, \
             patch.object(actions, 'speak'):
            actions.sleep_pc()
        cmd = mock_run.call_args[0][0]
        assert 'powrprof' in ' '.join(cmd).lower()


# ── search ────────────────────────────────────────────────────────────────

class TestSearch:
    def test_search_no_transcript(self, actions):
        result = actions.search(None)
        assert result['success'] is False

    def test_search_opens_browser(self, actions):
        with patch('webbrowser.open') as mock_wb, \
             patch.object(actions, 'speak'):
            result = actions.search('search for Schneider contactors')
        mock_wb.assert_called_once()
        assert result['success'] is True

    def test_search_strips_keyword(self, actions):
        with patch('webbrowser.open') as mock_wb, \
             patch.object(actions, 'speak'):
            result = actions.search('search for Schneider MCB')
        assert result['query']
        assert 'search for' not in result['query']

    def test_search_action_key(self, actions):
        with patch('webbrowser.open'), \
             patch.object(actions, 'speak'):
            result = actions.search('google something')
        assert result['action'] == 'search'


# ── system_status ─────────────────────────────────────────────────────────

class TestSystemStatus:
    def test_system_status_success(self, actions):
        with patch('psutil.cpu_percent', return_value=45.0), \
             patch('psutil.virtual_memory') as mock_vm, \
             patch.object(actions, 'speak'):
            mock_vm.return_value.percent = 60.0
            result = actions.system_status()
        assert result['success'] is True
        assert result['action'] == 'system_status'

    def test_system_status_contains_cpu(self, actions):
        with patch('psutil.cpu_percent', return_value=23.0), \
             patch('psutil.virtual_memory') as mock_vm, \
             patch.object(actions, 'speak'):
            mock_vm.return_value.percent = 50.0
            result = actions.system_status()
        assert '23' in result['value']


# ── morning_brief ─────────────────────────────────────────────────────────

class TestMorningBrief:
    def test_morning_brief_no_brief_today(self, actions):
        mock_mem = MagicMock()
        mock_mem.get_today_brief.return_value = ''
        with patch('core.memory.JarvisMemory', return_value=mock_mem), \
             patch.object(actions, 'speak'):
            result = actions.morning_brief()
        assert result['success'] is True
        assert result['brief'] == ''

    def test_morning_brief_with_brief(self, actions):
        mock_mem = MagicMock()
        mock_mem.get_today_brief.return_value = 'صباح الخير يابابا. Today news...'
        with patch('core.memory.JarvisMemory', return_value=mock_mem), \
             patch.object(actions, 'speak') as mock_speak:
            result = actions.morning_brief()
        assert result['success'] is True
        assert 'صباح' in result['brief']
        mock_speak.assert_called_once()

    def test_morning_brief_exception_returns_false(self, actions):
        with patch('core.memory.JarvisMemory', side_effect=Exception('db error')):
            result = actions.morning_brief()
        assert result['success'] is False
        assert 'error' in result


# ── cancel ────────────────────────────────────────────────────────────────

class TestCancel:
    def test_cancel_success(self, actions):
        with patch.object(actions, 'speak'):
            result = actions.cancel()
        assert result['success'] is True
        assert result['action'] == 'cancel'


# ── ACTION_MAP ────────────────────────────────────────────────────────────

class TestActionMap:
    def test_action_map_has_all_required_actions(self):
        from actions.safe_actions import ACTION_MAP
        required = [
            'screenshot', 'time', 'weather', 'open_app', 'close_app',
            'volume_up', 'volume_down', 'mute', 'lock_screen', 'sleep_pc',
            'search', 'cancel', 'system_status', 'morning_brief',
        ]
        for action in required:
            assert action in ACTION_MAP, f"Missing from ACTION_MAP: {action}"

    def test_action_map_values_are_strings(self):
        from actions.safe_actions import ACTION_MAP
        for k, v in ACTION_MAP.items():
            assert isinstance(v, str)


# ── execute function ──────────────────────────────────────────────────────

class TestExecuteFunction:
    def test_execute_unknown_intent(self):
        from actions.safe_actions import execute, SafeActions
        sa = MagicMock(spec=SafeActions)
        result = execute({'intent': 'nonexistent_action', 'raw_text': ''}, sa)
        assert result['success'] is False

    def test_execute_time_intent(self):
        from actions.safe_actions import execute, SafeActions
        sa = MagicMock(spec=SafeActions)
        sa.time.return_value = {'action': 'time', 'success': True, 'value': '10:00'}
        result = execute({'intent': 'time', 'raw_text': ''}, sa)
        sa.time.assert_called_once()
        assert result['success'] is True

    def test_execute_passes_transcript(self):
        from actions.safe_actions import execute, SafeActions
        sa = MagicMock(spec=SafeActions)
        sa.open_app.return_value = {'action': 'open_app', 'success': True}
        execute({'intent': 'open_app', 'raw_text': 'open excel'}, sa)
        sa.open_app.assert_called_once_with(transcript='open excel')
