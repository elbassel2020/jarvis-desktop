"""Wake word detector using openWakeWord."""
import sounddevice as sd
import numpy as np
from openwakeword.model import Model
import time
from loguru import logger
from pathlib import Path
import json
from datetime import datetime


class WakeListener:
    def __init__(self, wake_word='hey_jarvis', threshold=0.35, on_detect=None,
                 always_on_check=None, always_on_rms=250):
        self.threshold = threshold
        self.on_detect = on_detect or self.default_handler
        self.always_on_check = always_on_check   # callable() -> bool
        self.always_on_rms = always_on_rms       # int16 RMS threshold
        self.model = Model(wakeword_models=[wake_word], inference_framework='onnx')
        self.chunk_size = 1280  # 80ms at 16kHz
        self.audit_log = Path('logs/audit.jsonl')
        self.audit_log.parent.mkdir(exist_ok=True)
        logger.info(f"Wake listener initialized: '{wake_word}' threshold={threshold}")

    def audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio chunk."""
        if status:
            logger.warning(f"Audio: {status}")
        audio = (indata[:, 0] * 32767).astype(np.int16)

        # Always-on bypass: fire on speech energy without wake word
        if self.always_on_check and self.always_on_check():
            rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
            if rms > self.always_on_rms:
                self.on_detect('always_on', 1.0)
            return  # skip wake word model during always-on

        prediction = self.model.predict(audio)

        for word, score in prediction.items():
            if score >= self.threshold:
                self.log_detection(word, score)
                self.on_detect(word, score)

    def log_detection(self, wake_word, score):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'event': 'wake_detected',
            'wake_word': wake_word,
            'confidence': float(score),
        }
        with open(self.audit_log, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        logger.success(f"WAKE: {wake_word} ({score:.2f})")

    def default_handler(self, wake_word, score):
        print(f"\nHeard: {wake_word} (confidence: {score:.2f})")

    def listen_forever(self):
        logger.info("Starting always-on listener... (Ctrl+C to stop)")
        with sd.InputStream(
            channels=1,
            samplerate=16000,
            blocksize=self.chunk_size,
            callback=self.audio_callback,
            dtype='float32',
        ):
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                logger.info("Listener stopped")


if __name__ == '__main__':
    listener = WakeListener()
    listener.listen_forever()
