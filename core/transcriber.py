"""OpenAI hosted STT — whisper-1 or gpt-4o-transcribe. Local Whisper fallback."""
import os
from pathlib import Path
from loguru import logger
import time
from openai import OpenAI


class Transcriber:
    def __init__(self, model_name='whisper-1', fallback_local=True):
        """Use OpenAI hosted STT.
        model_name: 'whisper-1' (cheaper) or 'gpt-4o-transcribe' (better)
        fallback_local: fall back to local Whisper small if API fails
        """
        api_key = os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_KEY')
        if not api_key:
            raise RuntimeError("Set OPENAI_API_KEY in config/.env")

        self.client = OpenAI(api_key=api_key)
        self.model = model_name
        self.fallback_local = fallback_local
        self._local_model = None  # lazy-loaded only if needed
        logger.info(f"OpenAI Transcriber ready: {model_name}")

    def transcribe(self, audio_path: Path, language=None) -> dict:
        """Transcribe via OpenAI API. Falls back to local Whisper on error if enabled."""
        t0 = time.time()
        try:
            with open(audio_path, 'rb') as f:
                response = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=f,
                    language=language,  # 'en', 'ar', or None for auto-detect
                    response_format='verbose_json',
                )
            elapsed = time.time() - t0
            out = {
                'text': response.text.strip(),
                'language': getattr(response, 'language', 'unknown'),
                'duration_s': elapsed,
                'audio_file': str(audio_path),
                'backend': f'openai/{self.model}',
            }
            logger.success(f"[{elapsed:.1f}s OpenAI] '{out['text']}' ({out['language']})")
            return out
        except Exception as e:
            logger.error(f"OpenAI STT failed: {e}")
            if self.fallback_local:
                logger.warning("Falling back to local Whisper...")
                return self._transcribe_local(audio_path, language)
            raise

    def _transcribe_local(self, audio_path: Path, language=None) -> dict:
        """Local Whisper small fallback — no FFmpeg required."""
        if self._local_model is None:
            import whisper
            self._local_model = whisper.load_model('small')
        import scipy.io.wavfile as wav
        import numpy as np
        sr, audio = wav.read(str(audio_path))
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        else:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        t0 = time.time()
        result = self._local_model.transcribe(audio, language=language, fp16=False)
        return {
            'text': result['text'].strip(),
            'language': result['language'],
            'duration_s': time.time() - t0,
            'audio_file': str(audio_path),
            'backend': 'whisper-small-local-fallback',
        }
