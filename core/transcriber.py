"""Whisper-based speech-to-text."""
import whisper
from pathlib import Path
from loguru import logger
import time


class Transcriber:
    def __init__(self, model_name='small'):
        logger.info(f"Loading Whisper '{model_name}'...")
        t0 = time.time()
        self.model = whisper.load_model(model_name)
        logger.info(f"Loaded in {time.time() - t0:.1f}s")

    def transcribe(self, audio_path: Path, language=None) -> dict:
        """Transcribe audio file. Returns dict with text, language, duration."""
        t0 = time.time()
        result = self.model.transcribe(
            str(audio_path),
            language=language,  # None = auto-detect (Arabic + English)
            fp16=False,         # CPU mode
        )
        elapsed = time.time() - t0

        out = {
            'text': result['text'].strip(),
            'language': result['language'],
            'duration_s': elapsed,
            'audio_file': str(audio_path),
        }
        logger.success(f"[{elapsed:.1f}s] '{out['text']}' ({out['language']})")
        return out
