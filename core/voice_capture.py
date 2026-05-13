"""Capture voice for N seconds after wake word."""
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
from pathlib import Path
from loguru import logger
from datetime import datetime


class VoiceCapture:
    def __init__(self, duration=5, samplerate=16000):
        self.duration = duration
        self.samplerate = samplerate
        self.captures_dir = Path('logs/captures')
        self.captures_dir.mkdir(parents=True, exist_ok=True)

    def capture(self) -> Path:
        """Record audio, save to WAV, return path."""
        logger.info(f"Recording {self.duration}s...")
        audio = sd.rec(
            int(self.duration * self.samplerate),
            samplerate=self.samplerate,
            channels=1,
            dtype='float32',
        )
        sd.wait()

        audio_int16 = (audio.flatten() * 32767).astype(np.int16)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = self.captures_dir / f'capture_{timestamp}.wav'
        wav.write(str(out_path), self.samplerate, audio_int16)

        logger.success(f"Captured: {out_path}")
        return out_path
