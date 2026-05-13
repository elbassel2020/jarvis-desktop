"""Local Whisper — large-v3 for best accuracy, no API dependency."""
import whisper
import time
import numpy as np
import scipy.io.wavfile as wav
from pathlib import Path
from loguru import logger


class Transcriber:
    def __init__(self, model_name='large-v3', fallback_local=False):
        logger.info(f"Loading Whisper {model_name}...")
        t0 = time.time()
        self.model = whisper.load_model(model_name)
        self.model_name = model_name
        logger.info(f"Whisper {model_name} loaded in {time.time() - t0:.1f}s")

    def _load_audio(self, path: Path) -> np.ndarray:
        """Load WAV via scipy, return float32 mono 16kHz for Whisper."""
        sr, audio = wav.read(str(path))
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        else:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            from scipy.signal import resample
            audio = resample(audio, int(len(audio) * 16000 / sr)).astype(np.float32)
        return audio

    def transcribe(self, audio_path: Path, language=None) -> dict:
        """Transcribe WAV without FFmpeg. Returns {text, language, duration_s, backend}."""
        t0 = time.time()
        audio = self._load_audio(audio_path)
        result = self.model.transcribe(audio, language=language, fp16=False)
        elapsed = time.time() - t0
        out = {
            'text': result['text'].strip(),
            'language': result['language'],
            'duration_s': elapsed,
            'audio_file': str(audio_path),
            'backend': f'whisper-{self.model_name}-local',
        }
        logger.success(f"[{elapsed:.1f}s] '{out['text']}' ({out['language']})")
        return out
