"""VAD-based voice capture — stops on silence, fixed-duration fallback."""
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
from pathlib import Path
from loguru import logger
from datetime import datetime


class VoiceCapture:
    def __init__(self, duration=5, samplerate=16000, use_vad=True,
                 silence_duration=1.2, silence_threshold=0.012):
        self.duration = duration
        self.samplerate = samplerate
        self.use_vad = use_vad
        self.silence_duration = silence_duration
        self.silence_threshold = silence_threshold
        self.captures_dir = Path('logs/captures')
        self.captures_dir.mkdir(parents=True, exist_ok=True)

    def capture(self) -> Path:
        """Record audio with optional VAD, save to WAV, return path."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = self.captures_dir / f'capture_{timestamp}.wav'

        if not self.use_vad:
            logger.info(f"Recording {self.duration}s fixed...")
            audio = sd.rec(
                int(self.duration * self.samplerate),
                samplerate=self.samplerate,
                channels=1,
                dtype='float32',
            )
            sd.wait()
            audio_int16 = (audio.flatten() * 32767).astype(np.int16)
        else:
            logger.info(f"Recording up to {self.duration}s (VAD)...")
            chunk_size = int(0.1 * self.samplerate)   # 100ms chunks
            max_chunks = int(self.duration / 0.1)
            silence_needed = int(self.silence_duration / 0.1)  # chunks of silence to stop
            chunks = []
            silence_count = 0
            speech_seen = False

            with sd.InputStream(samplerate=self.samplerate, channels=1, dtype='int16') as stream:
                for i in range(max_chunks):
                    chunk, _ = stream.read(chunk_size)
                    chunks.append(chunk.copy())
                    rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 32768.0
                    if rms > self.silence_threshold:
                        speech_seen = True
                        silence_count = 0
                    elif speech_seen:
                        silence_count += 1
                        if silence_count >= silence_needed and i > 10:
                            logger.info(f"Silence detected at {i * 0.1:.1f}s — stopping")
                            break

            audio_int16 = np.concatenate(chunks).flatten().astype(np.int16)

        wav.write(str(out_path), self.samplerate, audio_int16)
        actual_s = len(audio_int16) / self.samplerate
        logger.success(f"Captured ({actual_s:.1f}s): {out_path.name}")
        return out_path
