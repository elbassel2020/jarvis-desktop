"""Groq Whisper-Large-v3-Turbo (~300ms hosted) with faster-whisper local fallback."""
import os
import time
from pathlib import Path
from loguru import logger


class Transcriber:
    def __init__(self, model_name='whisper-large-v3-turbo', fallback_local='medium'):
        key = os.getenv('GROQ_API_KEY')
        if not key:
            raise RuntimeError("GROQ_API_KEY not set in config/.env")
        from groq import Groq
        self.groq = Groq(api_key=key)
        self.model_name = model_name
        self.fallback_local_name = fallback_local
        self._local = None  # lazy-loaded on first fallback use
        logger.info(f"Transcriber: Groq {model_name} primary + faster-whisper-{fallback_local} fallback")

    def _try_groq(self, audio_path, language=None):
        t0 = time.time()
        with open(audio_path, 'rb') as f:
            response = self.groq.audio.transcriptions.create(
                file=f,
                model=self.model_name,
                language=language,       # 'en', 'ar', or None for auto-detect
                response_format='verbose_json',
                temperature=0.0,
            )
        elapsed = time.time() - t0
        return {
            'text': response.text.strip(),
            'language': getattr(response, 'language', 'unknown'),
            'duration_s': elapsed,
            'audio_file': str(audio_path),
            'backend': f'groq/{self.model_name}',
        }

    def _load_local(self):
        if self._local is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper {self.fallback_local_name} (fallback)...")
            self._local = WhisperModel(
                self.fallback_local_name,
                device='cpu',
                compute_type='int8',
                num_workers=4,
                cpu_threads=4,
            )
        return self._local

    def _try_local(self, audio_path, language=None):
        t0 = time.time()
        model = self._load_local()
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = ''.join(s.text for s in segments).strip()
        return {
            'text': text,
            'language': info.language,
            'duration_s': time.time() - t0,
            'audio_file': str(audio_path),
            'backend': f'faster-whisper-{self.fallback_local_name}-local',
        }

    def transcribe(self, audio_path, language=None):
        try:
            result = self._try_groq(audio_path, language)
            logger.success(
                f"[{result['duration_s']*1000:.0f}ms GROQ] '{result['text']}' ({result['language']})"
            )
            return result
        except Exception as e:
            logger.warning(f"Groq STT failed, falling to local: {str(e)[:100]}")
        result = self._try_local(audio_path, language)
        logger.success(
            f"[{result['duration_s']*1000:.0f}ms LOCAL] '{result['text']}' ({result['language']})"
        )
        return result
