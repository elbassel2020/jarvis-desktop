"""Whisper-based speech-to-text — FFmpeg-free WAV loading via scipy."""
import whisper
import numpy as np
import scipy.io.wavfile as wav
from scipy.signal import resample
from pathlib import Path
from loguru import logger
import time


class Transcriber:
    def __init__(self, model_name='small'):
        logger.info(f"Loading Whisper '{model_name}'...")
        t0 = time.time()
        self.model = whisper.load_model(model_name)
        logger.info(f"Loaded in {time.time() - t0:.1f}s")

    def _load_audio(self, path: Path) -> np.ndarray:
        """Load WAV via scipy, return float32 mono 16kHz array for Whisper."""
        sr, audio = wav.read(str(path))
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.int32:
            audio = audio.astype(np.float32) / 2147483648.0
        else:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            audio = resample(audio, int(len(audio) * 16000 / sr)).astype(np.float32)
        return audio

    def transcribe(self, audio_path: Path, language=None) -> dict:
        """Transcribe WAV file without FFmpeg. Returns {text, language, duration_s}."""
        t0 = time.time()
        audio = self._load_audio(audio_path)
        result = self.model.transcribe(audio, language=language, fp16=False)
        elapsed = time.time() - t0

        out = {
            'text': result['text'].strip(),
            'language': result['language'],
            'duration_s': elapsed,
            'audio_file': str(audio_path),
        }
        logger.success(f"[{elapsed:.1f}s] '{out['text']}' ({out['language']})")
        return out
