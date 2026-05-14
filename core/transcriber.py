"""faster-whisper transcriber — CTranslate2 optimized, 5x faster on CPU."""
from faster_whisper import WhisperModel
from pathlib import Path
import time
from loguru import logger

class Transcriber:
    def __init__(self, model_name='medium', fallback_local=False):
        logger.info(f"Loading faster-whisper {model_name} (CPU int8)...")
        t0 = time.time()
        # CPU-optimized config: int8 quantization + threading
        self.model = WhisperModel(
            model_name,
            device='cpu',
            compute_type='int8',
            num_workers=4,
            cpu_threads=4
        )
        self.model_name = model_name
        logger.info(f"faster-whisper {model_name} loaded in {time.time()-t0:.1f}s")

    def transcribe(self, audio_path, language='en'):
        t0 = time.time()
        segments, info = self.model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,  # voice activity detection
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        text = ''.join(seg.text for seg in segments).strip()
        elapsed = time.time() - t0
        out = {
            'text': text,
            'language': info.language,
            'duration_s': elapsed,
            'audio_file': str(audio_path),
            'backend': f'faster-whisper-{self.model_name}',
        }
        logger.success(f"[{elapsed:.1f}s] '{text}' ({info.language})")
        return out
