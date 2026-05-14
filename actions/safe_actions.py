"""Safe actions — v0.6.0 (ElevenLabs TTS primary, edge-tts fallback, stamped screenshots)."""
from pathlib import Path
from datetime import datetime
from loguru import logger
import subprocess
import webbrowser
import requests
import asyncio
import edge_tts
import os
import pygame

pygame.mixer.init()

# ElevenLabs config
# Brian (nPczCjzI2devNBz1zQrb) — warm, friendly; Turbo model = faster
_ELEVEN_VOICE_ID = 'nPczCjzI2devNBz1zQrb'  # Brian — warm friendly voice
_ELEVEN_MODEL = 'eleven_turbo_v2_5'


class SafeActions:
    def __init__(self):
        self.screenshots_dir = Path('logs/screenshots')
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.tts_dir = Path('logs/tts')
        self.tts_dir.mkdir(parents=True, exist_ok=True)

        self.allowed_apps = {
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

    def _speak_elevenlabs(self, text: str) -> Path:
        """ElevenLabs TTS → mp3 via streaming API."""
        from elevenlabs.client import ElevenLabs
        from elevenlabs import VoiceSettings
        api_key = os.getenv('ELEVENLABS_API_KEY')
        client = ElevenLabs(api_key=api_key)
        timestamp = datetime.now().strftime('%H%M%S')
        out_path = self.tts_dir / f'speech_{timestamp}.mp3'
        audio = client.text_to_speech.convert(
            voice_id=_ELEVEN_VOICE_ID,
            text=text,
            model_id=_ELEVEN_MODEL,
            voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.75),
        )
        with open(str(out_path), 'wb') as f:
            for chunk in audio:
                f.write(chunk)
        return out_path

    async def _speak_edge_async(self, text: str, voice='en-US-AriaNeural') -> Path:
        timestamp = datetime.now().strftime('%H%M%S')
        out_path = self.tts_dir / f'speech_{timestamp}.mp3'
        await edge_tts.Communicate(text, voice).save(str(out_path))
        return out_path

    def speak(self, text: str, voice='en-US-AriaNeural'):
        """ElevenLabs primary TTS, edge-tts fallback. Plays blocking via pygame."""
        eleven_key = os.getenv('ELEVENLABS_API_KEY')
        out_path = None

        if eleven_key:
            try:
                out_path = self._speak_elevenlabs(text)
                logger.debug("TTS: ElevenLabs")
            except Exception as e:
                logger.warning(f"ElevenLabs TTS failed ({e}), falling back to edge-tts")

        if out_path is None:
            try:
                out_path = asyncio.run(self._speak_edge_async(text, voice))
                logger.debug("TTS: edge-tts")
            except Exception as e:
                logger.error(f"TTS failed entirely: {e}")
                return None

        try:
            pygame.mixer.music.load(str(out_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            logger.error(f"Pygame playback failed: {e}")
        return out_path

    def speak_sync(self, text: str, voice='en-US-AriaNeural'):
        return self.speak(text, voice)

    def screenshot(self, transcript=None) -> dict:
        """Take screenshot with timestamp watermark, open it."""
        from PIL import ImageGrab, ImageDraw, ImageFont
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        readable = datetime.now().strftime('%H:%M:%S')
        path = self.screenshots_dir / f'screenshot_{timestamp}.png'

        try:
            img = ImageGrab.grab(all_screens=True)
        except TypeError:
            img = ImageGrab.grab()

        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except Exception:
            font = ImageFont.load_default()

        label = f"Jarvis | {readable}"
        bbox = draw.textbbox((0, 0), label, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = img.width - w - 20, img.height - h - 20
        draw.rectangle([x - 10, y - 5, x + w + 10, y + h + 10], fill=(0, 0, 0))
        draw.text((x, y), label, fill=(255, 255, 255), font=font)

        img.save(str(path), 'PNG', optimize=True)
        logger.success(f"Screenshot ({img.width}x{img.height}): {path}")
        os.startfile(str(path))
        self.speak("Screenshot captured")
        return {'action': 'screenshot', 'path': str(path), 'size': f'{img.width}x{img.height}', 'success': True}

    def time(self, transcript=None) -> dict:
        now = datetime.now()
        text = now.strftime("The time is %I:%M %p")
        self.speak(text)
        return {'action': 'time', 'value': now.isoformat(), 'success': True}

    def weather(self, transcript=None, city='Jubail') -> dict:
        try:
            r = requests.get(f'https://wttr.in/{city}?format=3', timeout=5)
            text = r.text.strip()
            self.speak(text)
            return {'action': 'weather', 'value': text, 'success': True}
        except Exception as e:
            logger.error(f"Weather failed: {e}")
            return {'action': 'weather', 'error': str(e), 'success': False}

    def open_app(self, transcript=None) -> dict:
        if not transcript:
            return {'action': 'open_app', 'error': 'no transcript', 'success': False}
        text_lower = transcript.lower()
        matched = None
        for name, exe in self.allowed_apps.items():
            if name in text_lower:
                matched = (name, exe)
                break
        if not matched:
            self.speak("App not in whitelist")
            return {'action': 'open_app', 'error': 'not whitelisted', 'success': False}
        app, exe = matched
        try:
            if exe.startswith('ms-') or exe.endswith(':'):
                os.startfile(exe)
            else:
                subprocess.Popen(exe, shell=True)
            try:
                from core.memory import JarvisMemory
                JarvisMemory().log_app_open(app)
            except Exception:
                pass
            self.speak(f"Opening {app}")
            return {'action': 'open_app', 'app': app, 'success': True}
        except Exception as e:
            return {'action': 'open_app', 'error': str(e), 'success': False}

    def search(self, transcript=None) -> dict:
        if not transcript:
            return {'action': 'search', 'error': 'no transcript', 'success': False}
        query = transcript.lower()
        for w in ['search for', 'search', 'google', 'find', 'ابحث', 'دور على', 'دور']:
            query = query.replace(w, '').strip()
        webbrowser.open(f'https://www.google.com/search?q={query.replace(" ", "+")}')
        self.speak(f"Searching for {query}")
        return {'action': 'search', 'query': query, 'success': True}

    def cancel(self, transcript=None) -> dict:
        self.speak("Cancelled")
        return {'action': 'cancel', 'success': True}

    def system_status(self, transcript=None) -> dict:
        import psutil
        text = f"CPU at {psutil.cpu_percent()} percent, memory at {psutil.virtual_memory().percent} percent"
        logger.info(f"Status: {text}")
        self.speak(text)
        return {'action': 'system_status', 'value': text, 'success': True}


    def close_app(self, transcript=None) -> dict:
        if not transcript:
            return {'action': 'close_app', 'error': 'no transcript', 'success': False}
        text_lower = transcript.lower()
        process_map = {
            'chrome': 'chrome.exe',
            'edge': 'msedge.exe',
            'notepad': 'notepad.exe',
            'calculator': 'CalculatorApp.exe', 'calc': 'CalculatorApp.exe',
            'word': 'WINWORD.EXE',
            'excel': 'EXCEL.EXE',
            'outlook': 'OUTLOOK.EXE',
            'paint': 'mspaint.exe',
            'photos': 'Microsoft.Photos.exe',
            'calendar': 'HxOutlook.exe',
            'mail': 'HxOutlook.exe',
            'snipping': 'SnippingTool.exe',
            'taskmgr': 'Taskmgr.exe',
            'vscode': 'Code.exe', 'code': 'Code.exe',
            'explorer': 'explorer.exe',
            'terminal': 'WindowsTerminal.exe',
        }
        target = None
        for name, exe in process_map.items():
            if name in text_lower:
                target = (name, exe)
                break
        if not target:
            self.speak("I don't know which app to close")
            return {'action': 'close_app', 'error': 'no match', 'success': False}
        name, exe = target
        try:
            import subprocess
            subprocess.run(['taskkill', '/F', '/IM', exe], capture_output=True)
            self.speak(f"Closed {name}")
            return {'action': 'close_app', 'app': name, 'success': True}
        except Exception as e:
            return {'action': 'close_app', 'error': str(e), 'success': False}


ACTION_MAP = {
    'screenshot': 'screenshot',
    'time': 'time',
    'weather': 'weather',
    'open_app': 'open_app',
    'close_app': 'close_app',
    'search': 'search',
    'cancel': 'cancel',
    'system_status': 'system_status',
}


def execute(intent_result: dict, actions: SafeActions = None) -> dict:
    actions = actions or SafeActions()
    intent = intent_result.get('intent', 'unknown')
    raw = intent_result.get('raw_text', '')
    if intent not in ACTION_MAP:
        return {'action': 'unknown', 'success': False, 'reason': f'No handler for {intent}'}
    return getattr(actions, ACTION_MAP[intent])(transcript=raw)
