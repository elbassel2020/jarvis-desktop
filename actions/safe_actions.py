"""Safe actions only — Phase 3. No file ops, no system control."""
from pathlib import Path
from datetime import datetime
from loguru import logger
import subprocess
import webbrowser
import requests
from PIL import ImageGrab
import asyncio
import edge_tts
import os


class SafeActions:
    def __init__(self):
        self.screenshots_dir = Path('logs/screenshots')
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.tts_dir = Path('logs/tts')
        self.tts_dir.mkdir(parents=True, exist_ok=True)

        # WHITELIST — only these apps can be launched
        self.allowed_apps = {
            'calculator': 'calc.exe',
            'notepad': 'notepad.exe',
            'chrome': 'chrome.exe',
            'edge': 'msedge.exe',
            'explorer': 'explorer.exe',
            'cmd': 'cmd.exe',
            'powershell': 'powershell.exe',
            'vscode': 'code.exe',
        }

    async def _speak_async(self, text: str, voice='en-US-AriaNeural'):
        timestamp = datetime.now().strftime('%H%M%S')
        out_path = self.tts_dir / f'speech_{timestamp}.mp3'
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
        os.startfile(str(out_path))
        return out_path

    def speak_sync(self, text: str, voice='en-US-AriaNeural'):
        """Synthesize and play speech via edge-tts."""
        try:
            asyncio.run(self._speak_async(text, voice))
        except Exception as e:
            logger.warning(f"TTS failed: {e}")

    def screenshot(self, transcript=None) -> dict:
        """Take screenshot of primary screen."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = self.screenshots_dir / f'screenshot_{timestamp}.png'
        img = ImageGrab.grab()
        img.save(str(path))
        logger.success(f"Screenshot: {path}")
        self.speak_sync("Screenshot saved")
        return {'action': 'screenshot', 'path': str(path), 'success': True}

    def time(self, transcript=None) -> dict:
        """Speak current time."""
        now = datetime.now()
        text = now.strftime("The time is %I:%M %p")
        logger.info(f"Time: {text}")
        self.speak_sync(text)
        return {'action': 'time', 'value': now.isoformat(), 'success': True}

    def weather(self, transcript=None, city='Jubail') -> dict:
        """Get weather via free wttr.in API."""
        try:
            r = requests.get(f'https://wttr.in/{city}?format=3', timeout=5)
            text = r.text.strip()
            logger.info(f"Weather: {text}")
            self.speak_sync(text)
            return {'action': 'weather', 'value': text, 'success': True}
        except Exception as e:
            logger.error(f"Weather failed: {e}")
            return {'action': 'weather', 'error': str(e), 'success': False}

    def open_app(self, transcript=None) -> dict:
        """Open whitelisted app from transcript."""
        if not transcript:
            return {'action': 'open_app', 'error': 'no transcript', 'success': False}

        text_lower = transcript.lower()
        matched_app = None
        for app_name, exe in self.allowed_apps.items():
            if app_name in text_lower:
                matched_app = (app_name, exe)
                break

        if not matched_app:
            self.speak_sync("App not in whitelist")
            return {'action': 'open_app', 'error': 'not whitelisted', 'success': False}

        app_name, exe = matched_app
        try:
            subprocess.Popen(exe, shell=True)
            logger.success(f"Opened: {app_name}")
            self.speak_sync(f"Opening {app_name}")
            return {'action': 'open_app', 'app': app_name, 'success': True}
        except Exception as e:
            logger.error(f"Open failed: {e}")
            return {'action': 'open_app', 'error': str(e), 'success': False}

    def search(self, transcript=None) -> dict:
        """Open web search in browser."""
        if not transcript:
            return {'action': 'search', 'error': 'no transcript', 'success': False}
        query = transcript.lower()
        for w in ['search for', 'search', 'google', 'find', 'ابحث', 'دور على', 'دور']:
            query = query.replace(w, '').strip()
        url = f'https://www.google.com/search?q={query.replace(" ", "+")}'
        webbrowser.open(url)
        logger.info(f"Search: {query}")
        self.speak_sync(f"Searching for {query}")
        return {'action': 'search', 'query': query, 'success': True}

    def cancel(self, transcript=None) -> dict:
        """Acknowledge cancel."""
        self.speak_sync("Cancelled")
        return {'action': 'cancel', 'success': True}

    def system_status(self, transcript=None) -> dict:
        """Report basic CPU + memory status."""
        import psutil
        text = f"CPU at {psutil.cpu_percent()} percent, memory at {psutil.virtual_memory().percent} percent"
        logger.info(f"Status: {text}")
        self.speak_sync(text)
        return {'action': 'system_status', 'value': text, 'success': True}


# Intent -> action method name mapping
ACTION_MAP = {
    'screenshot': 'screenshot',
    'time': 'time',
    'weather': 'weather',
    'open_app': 'open_app',
    'search': 'search',
    'cancel': 'cancel',
    'system_status': 'system_status',
}


def execute(intent_result: dict, actions: SafeActions = None) -> dict:
    """Dispatch intent to safe action handler."""
    actions = actions or SafeActions()
    intent = intent_result.get('intent', 'unknown')
    raw = intent_result.get('raw_text', '')

    if intent not in ACTION_MAP:
        return {'action': 'unknown', 'success': False, 'reason': f'No handler for {intent}'}

    handler = getattr(actions, ACTION_MAP[intent])
    return handler(transcript=raw)
