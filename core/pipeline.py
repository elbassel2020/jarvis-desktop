"""Phase 2 pipeline: wake word -> record -> Whisper STT -> intent (no execution)."""
from core.wake_listener import WakeListener
from core.voice_capture import VoiceCapture
from core.transcriber import Transcriber
from core.intent_parser import IntentParser
from loguru import logger
from pathlib import Path
import json
from datetime import datetime


class JarvisPipeline:
    def __init__(self, capture_duration=5, whisper_model='small'):
        self.capture = VoiceCapture(duration=capture_duration)
        self.transcriber = Transcriber(model_name=whisper_model)
        self.parser = IntentParser()
        self.audit_log = Path('logs/pipeline.jsonl')
        self.audit_log.parent.mkdir(exist_ok=True)
        self.listener = WakeListener(on_detect=self.on_wake_detected)

    def on_wake_detected(self, wake_word, score):
        """Called when wake word detected — record, transcribe, parse."""
        logger.warning(f"WAKE [{score:.2f}] — recording...")
        try:
            audio_path = self.capture.capture()
            transcript = self.transcriber.transcribe(audio_path)
            intent = self.parser.parse(transcript['text'])

            entry = {
                'timestamp': datetime.now().isoformat(),
                'event': 'pipeline_complete',
                'wake_confidence': float(score),
                'transcript': transcript,
                'intent': intent,
            }
            with open(self.audit_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

            print(f"\n  Heard: '{transcript['text']}'")
            print(f"  Intent: {intent['intent']} ({intent['confidence']:.2f})")
            print(f"  (Phase 2: parse only — no execution)\n")
        except Exception as e:
            logger.error(f"Pipeline error: {e}")

    def run(self):
        self.listener.listen_forever()


if __name__ == '__main__':
    JarvisPipeline().run()
