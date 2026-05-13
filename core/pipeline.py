"""Phase 3.1 pipeline: wake -> record -> STT -> intent -> execution + feedback prevention."""
from core.wake_listener import WakeListener
from core.voice_capture import VoiceCapture
from core.transcriber import Transcriber
from core.intent_parser import IntentParser
from actions.safe_actions import SafeActions, execute as execute_action
from loguru import logger
from pathlib import Path
import json
import time
import os
import threading
from datetime import datetime


class JarvisPipeline:
    def __init__(self, capture_duration=5, whisper_model='whisper-1', wake_word='hey_jarvis', wake_threshold=0.45):
        self.capture = VoiceCapture(duration=capture_duration)
        self.transcriber = Transcriber(model_name=whisper_model)
        self.parser = IntentParser()
        self.actions = SafeActions()
        self.execute_enabled = os.getenv('ENABLE_ACTIONS', 'false').lower() == 'true'
        self.audit_log = Path('logs/pipeline.jsonl')
        self.audit_log.parent.mkdir(exist_ok=True)

        # Feedback loop prevention
        self.processing_lock = threading.Lock()
        self.cooldown_until = 0.0  # epoch time — ignore wakes before this

        self.listener = WakeListener(
            wake_word=wake_word,
            threshold=wake_threshold,
            on_detect=self.on_wake_detected_safe,
        )
        logger.info(f"Pipeline ready. Backend: {whisper_model}, Execution: {'ENABLED' if self.execute_enabled else 'DISABLED'}")

    def on_wake_detected_safe(self, wake_word, score):
        """Gate: cooldown + processing lock prevent TTS feedback loops."""
        now = time.time()
        if now < self.cooldown_until:
            return  # silent ignore during cooldown window
        if not self.processing_lock.acquire(blocking=False):
            return  # already processing a command
        try:
            self.on_wake_detected(wake_word, score)
        finally:
            self.processing_lock.release()
            self.cooldown_until = time.time() + 2.0  # 2s post-action cooldown

    def on_wake_detected(self, wake_word, score):
        logger.warning(f"WAKE [{score:.2f}] — recording...")
        try:
            audio_path = self.capture.capture()
            transcript = self.transcriber.transcribe(audio_path)
            intent = self.parser.parse(transcript['text'])

            execution = None
            if self.execute_enabled and intent['confidence'] >= 0.3:
                logger.warning(f"EXECUTING: {intent['intent']}")
                self.cooldown_until = time.time() + 5.0  # mute during TTS
                execution = execute_action(intent, self.actions)
                self.cooldown_until = time.time() + 2.0  # post-TTS cooldown
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
