"""Phase 3 pipeline: wake -> record -> STT -> intent -> SAFE EXECUTION."""
from core.wake_listener import WakeListener
from core.voice_capture import VoiceCapture
from core.transcriber import Transcriber
from core.intent_parser import IntentParser
from actions.safe_actions import SafeActions, execute as execute_action
from loguru import logger
from pathlib import Path
import json
from datetime import datetime
import os


class JarvisPipeline:
    def __init__(self, capture_duration=5, whisper_model='small', wake_word='hey_jarvis', wake_threshold=0.35):
        self.capture = VoiceCapture(duration=capture_duration)
        self.transcriber = Transcriber(model_name=whisper_model)
        self.parser = IntentParser()
        self.actions = SafeActions()
        self.execute_enabled = os.getenv('ENABLE_ACTIONS', 'false').lower() == 'true'
        self.audit_log = Path('logs/pipeline.jsonl')
        self.audit_log.parent.mkdir(exist_ok=True)
        self.listener = WakeListener(wake_word=wake_word, threshold=wake_threshold, on_detect=self.on_wake_detected)
        logger.info(f"Pipeline ready. Execution: {'ENABLED' if self.execute_enabled else 'DISABLED'}")

    def on_wake_detected(self, wake_word, score):
        """Called when wake word detected — record, transcribe, parse, execute."""
        logger.warning(f"WAKE [{score:.2f}] — recording...")
        try:
            audio_path = self.capture.capture()
            transcript = self.transcriber.transcribe(audio_path)
            intent = self.parser.parse(transcript['text'])

            execution = None
            if self.execute_enabled and intent['confidence'] >= 0.3:
                logger.warning(f"EXECUTING: {intent['intent']}")
                execution = execute_action(intent, self.actions)
                print(f"  Executed: {execution}")
            else:
                reason = 'execution disabled' if not self.execute_enabled else f"low confidence ({intent['confidence']:.2f})"
                print(f"  Skipped: {reason}")

            entry = {
                'timestamp': datetime.now().isoformat(),
                'event': 'pipeline_complete',
                'wake_confidence': float(score),
                'transcript': transcript,
                'intent': intent,
                'execution': execution,
            }
            with open(self.audit_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

            print(f"\n  Heard: '{transcript['text']}'")
            print(f"  Intent: {intent['intent']} ({intent['confidence']:.2f})\n")
        except Exception as e:
            logger.error(f"Pipeline error: {e}")

    def run(self):
        self.listener.listen_forever()


if __name__ == '__main__':
    JarvisPipeline().run()
