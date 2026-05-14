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
_ELEVEN_MODEL = 'eleven_flash_v2_5'


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


    def volume_up(self, transcript=None) -> dict:
        # Single PowerShell process, 5 volume-up keypresses
        subprocess.run(
            ['powershell', '-Command',
             '$sh=New-Object -ComObject WScript.Shell; 1..5|%{$sh.SendKeys([char]175)}'],
            capture_output=True
        )
        self.speak('Volume up')
        return {'action': 'volume_up', 'success': True}

    def volume_down(self, transcript=None) -> dict:
        subprocess.run(
            ['powershell', '-Command',
             '$sh=New-Object -ComObject WScript.Shell; 1..5|%{$sh.SendKeys([char]174)}'],
            capture_output=True
        )
        self.speak('Volume down')
        return {'action': 'volume_down', 'success': True}

    def mute(self, transcript=None) -> dict:
        subprocess.run(
            ['powershell', '-Command',
             '(New-Object -ComObject WScript.Shell).SendKeys([char]173)'],
            capture_output=True
        )
        self.speak('Muted')
        return {'action': 'mute', 'success': True}

    def lock_screen(self, transcript=None) -> dict:
        self.speak('Locking now')
        subprocess.run(['rundll32.exe', 'user32.dll,LockWorkStation'])
        return {'action': 'lock_screen', 'success': True}

    def sleep_pc(self, transcript=None) -> dict:
        self.speak('Going to sleep')
        subprocess.run(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'])
        return {'action': 'sleep_pc', 'success': True}

    def stop(self, transcript=None) -> dict:
        """Immediate interrupt — stop TTS, clear nothing, stay silent."""
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        return {'action': 'stop', 'success': True}

    def morning_brief(self, transcript=None) -> dict:
        try:
            from core.memory import JarvisMemory
            mem = JarvisMemory()
            brief = mem.get_today_brief()
            if brief:
                self.speak(brief)
                return {'action': 'morning_brief', 'brief': brief, 'success': True}
            else:
                self.speak("No brief yet for today. Learning runs at 6 AM يابابا.")
                return {'action': 'morning_brief', 'brief': '', 'success': True}
        except Exception as e:
            logger.error(f"morning_brief failed: {e}")
            return {'action': 'morning_brief', 'error': str(e), 'success': False}


    def vision(self, transcript=None) -> dict:
        """Analyze an image — clipboard first, then most recent screenshot."""
        from core.vision import JarvisVision
        v = JarvisVision()
        img = v.from_clipboard()
        if not img:
            img = v.find_recent_image()
        if not img:
            self.speak('مفيش صورة لقيتها')
            return {'action': 'vision', 'error': 'no image', 'success': False}
        result = v.analyze(img)
        if result.get('success'):
            self.speak(result['description'])
            return {'action': 'vision', 'description': result['description'], 'image': str(img), 'success': True}
        self.speak('حصل مشكلة في التحليل')
        return {'action': 'vision', 'error': result.get('error'), 'success': False}

    def shop(self, transcript=None) -> dict:
        """Search KSA suppliers for electrical products."""
        from core.shopping import ShoppingAssistant
        query = transcript or ''
        for w in ['shop', 'shopping', 'buy', 'search for', 'اشتري', 'دور على', 'هات', 'سعر']:
            query = query.replace(w, '').strip()
        if not query:
            self.speak('قولي اسم المنتج')
            return {'action': 'shop', 'error': 'no query', 'success': False}
        result = ShoppingAssistant().search(query)
        if result.get('success'):
            self.speak(result['results'][:300])
            return {'action': 'shop', 'results': result['results'], 'success': True}
        self.speak('مش لاقي معلومات دلوقتي')
        return {'action': 'shop', 'error': result.get('error'), 'success': False}

    def analyze_code(self, transcript=None) -> dict:
        """Read-only self-review of all core/ files."""
        from core.self_analyze import SelfAnalyzer
        self.speak('بحلل الكود بتاعي، استنى ثواني')
        result = SelfAnalyzer().analyze_self()
        if result.get('success'):
            self.speak(f'حللت {result["files_analyzed"]} files. الـ report في audits folder')
            return {'action': 'analyze_code', 'report': result['report_file'], 'success': True}
        return {'action': 'analyze_code', 'error': 'failed', 'success': False}

    def msma_help(self, transcript=None) -> dict:
        """Look up MSMA Bot command from semantic memory."""
        from core.memory import JarvisMemory
        m = JarvisMemory()
        cur = m.conn.cursor()
        text = (transcript or '').lower().replace('/', '')
        cur.execute("SELECT key, value FROM semantic WHERE category='msma_commands'")
        all_cmds = cur.fetchall()
        best_match = None
        for key, value in all_cmds:
            cmd_name = key.replace('msma_cmd_', '')
            if cmd_name in text:
                best_match = value
                break
        if best_match:
            self.speak(best_match[:200])
            return {'action': 'msma_help', 'info': best_match, 'success': True}
        self.speak(f'عندي {len(all_cmds)} command في الـ-MSMA Bot. قول اسم الـ-command')
        return {'action': 'msma_help', 'count': len(all_cmds), 'success': True}


ACTION_MAP = {
    'screenshot': 'screenshot',
    'time': 'time',
    'weather': 'weather',
    'open_app': 'open_app',
    'close_app': 'close_app',
    'volume_up': 'volume_up',
    'volume_down': 'volume_down',
    'mute': 'mute',
    'lock_screen': 'lock_screen',
    'sleep_pc': 'sleep_pc',
    'search': 'search',
    'cancel': 'cancel',
    'system_status': 'system_status',
    'morning_brief': 'morning_brief',
    'stop': 'stop',
    'vision': 'vision',
    'shop': 'shop',
    'analyze_code': 'analyze_code',
    'msma_help': 'msma_help',
}


def execute(intent_result: dict, actions: SafeActions = None) -> dict:
    actions = actions or SafeActions()
    intent = intent_result.get('intent', 'unknown')
    raw = intent_result.get('raw_text', '')
    if intent not in ACTION_MAP:
        return {'action': 'unknown', 'success': False, 'reason': f'No handler for {intent}'}
    return getattr(actions, ACTION_MAP[intent])(transcript=raw)
