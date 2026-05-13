"""Phase 4 pipeline: wake -> record -> STT -> LLM brain -> safe action."""
from core.wake_listener import WakeListener
from core.voice_capture import VoiceCapture
from core.transcriber import Transcriber
from core.llm_brain import LLMBrain
from actions.safe_actions import SafeActions, execute as execute_action
from loguru import logger
from pathlib import Path
import json
import time
import os
import threading
from datetime import datetime


class JarvisPipeline:
    def __init__(self, capture_duration=5, whisper_model='whisper-1',
                 wake_word='hey_jarvis', wake_threshold=0.45, llm_model='qwen2.5:7b'):
        self.capture = VoiceCapture(duration=capture_duration)
        self.transcriber = Transcriber(model_name=whisper_model)
        self.brain = LLMBrain(model=llm_model)
        self.actions = SafeActions()
        self.execute_enabled = os.getenv('ENABLE_ACTIONS', 'false').lower() == 'true'
        self.audit_log = Path('logs/pipeline.jsonl')
        self.audit_log.parent.mkdir(exist_ok=True)

        self.processing_lock = threading.Lock()
        self.cooldown_until = 0.0

        self.listener = WakeListener(
            wake_word=wake_word,
            threshold=wake_threshold,
            on_detect=self.on_wake_detected_safe,
        )
        logger.info(f"v0.4.0 Pipeline: STT={whisper_model} Brain={llm_model} Exec={self.execute_enabled}")

    def on_wake_detected_safe(self, wake_word, score):
        now = time.time()
        if now < self.cooldown_until:
            return
        if not self.processing_lock.acquire(blocking=False):
            return
        try:
            self.on_wake_detected(wake_word, score)
        finally:
            self.processing_lock.release()
            self.cooldown_until = time.time() + 2.0

    def on_wake_detected(self, wake_word, score):
        logger.warning(f"WAKE [{score:.2f}] — recording...")
        try:
            audio_path = self.capture.capture()
            transcript = self.transcriber.transcribe(audio_path)

            # LLM brain decides action + response
            decision = self.brain.think(transcript['text'])

            execution = None
            if self.execute_enabled and decision['action'] not in ('chat', 'cancel'):
                if decision['confidence'] >= 0.3:
                    logger.warning(f"EXECUTING: {decision['action']}")
                    self.cooldown_until = time.time() + 8.0
                    intent_dict = {
                        'intent': decision['action'],
                        'confidence': decision['confidence'],
                        'raw_text': decision['params'] or transcript['text'],
                    }
                    execution = execute_action(intent_dict, self.actions)
                    self.cooldown_until = time.time() + 2.0
                else:
                    self.actions.speak("Sorry, I am not sure what you meant")
            elif decision['action'] == 'chat' and decision.get('response'):
                self.cooldown_until = time.time() + 5.0
                self.actions.speak(decision['response'])

            entry = {
                'timestamp': datetime.now().isoformat(),
                'event': 'pipeline_complete',
                'wake_confidence': float(score),
                'transcript': transcript,
                'decision': decision,
                'execution': execution,
            }
            with open(self.audit_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

            print(f"\n  Heard:    '{transcript['text']}'")
            print(f"  Brain:    {decision['action']} (conf={decision['confidence']:.2f})")
            print(f"  Response: '{decision['response']}'")
            if execution:
                print(f"  Executed: {execution.get('action')} success={execution.get('success')}")
            print()
        except Exception as e:
            logger.error(f"Pipeline error: {e}")

    def run(self):
        self.listener.listen_forever()


if __name__ == '__main__':
    JarvisPipeline().run()
