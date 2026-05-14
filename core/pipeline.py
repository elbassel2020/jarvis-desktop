"""Phase 4 pipeline: wake -> record -> STT -> LLM brain -> safe action."""
from core.wake_listener import WakeListener
from core.voice_capture import VoiceCapture
from core.transcriber import Transcriber
from core.llm_brain import LLMBrain
from core.memory import JarvisMemory
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
        self.memory = JarvisMemory()
        self.brain = LLMBrain(model=llm_model)
        self.actions = SafeActions()
        self.execute_enabled = os.getenv('ENABLE_ACTIONS', 'false').lower() == 'true'
        self.audit_log = Path('logs/pipeline.jsonl')
        self.audit_log.parent.mkdir(exist_ok=True)

        self.processing_lock = threading.Lock()
        self.cooldown_until = 0.0
        self.pending_action = None  # waiting for confirmation

        self.listener = WakeListener(
            wake_word=wake_word,
            threshold=wake_threshold,
            on_detect=self.on_wake_detected_safe,
        )
        logger.info(f"v0.7.1 Pipeline: STT={whisper_model} Brain={llm_model} Exec={self.execute_enabled}")

        # Midnight reflection — daemon thread, runs at 00:05 daily
        try:
            import datetime as _dt

            def _run_reflection_loop():
                import time as _time
                while True:
                    now = _dt.datetime.now()
                    next_run = (now + _dt.timedelta(days=1)).replace(
                        hour=0, minute=5, second=0, microsecond=0
                    )
                    _time.sleep((next_run - now).total_seconds())
                    try:
                        from core.reflection import Reflector
                        Reflector().reflect_on_today()
                    except Exception as _e:
                        logger.debug(f"Reflection loop: {_e}")

            _t = threading.Thread(target=_run_reflection_loop, daemon=True, name='reflection')
            _t.start()
            self.reflection_thread = _t
            logger.info("Midnight reflection scheduler started")
        except Exception as e:
            logger.warning(f"Reflection scheduler failed: {e}")

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

            # Handle pending confirmation BEFORE calling LLM
            if self.pending_action is not None:
                text_lower = transcript.get('text', '').lower()
                if any(w in text_lower for w in ['yes', 'تمام', 'ايوة', 'اوكي', 'ok', 'confirm', 'go', 'yep', 'sure']):
                    logger.warning(f"  ✓ CONFIRMED: {self.pending_action['intent']}")
                    execution = execute_action(self.pending_action, self.actions)
                    self.pending_action = None
                    return
                elif any(w in text_lower for w in ['no', 'لا', 'cancel', 'الغاء', 'stop', 'nope']):
                    self.actions.speak('Cancelled')
                    self.pending_action = None
                    return
                else:
                    self.actions.speak('I had a pending action. Say yes or no first.')
                    return

            # LLM brain decides action + response
            decision = self.brain.think(transcript['text'])

            # Gate destructive actions behind confirmation
            if decision.get('confirmation_required', False) and decision['action'] not in ('chat', 'cancel'):
                self.pending_action = {
                    'intent': decision['action'],
                    'confidence': decision.get('confidence', 0.5),
                    'raw_text': decision.get('params') or transcript.get('text', ''),
                }
                self.actions.speak(decision.get('spoken') or 'Confirm?')
                logger.warning(f"  ⏸ PENDING: {decision['action']} — awaiting confirmation")
                return

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
            elif decision['action'] == 'chat' and (decision.get('spoken') or decision.get('response')):
                self.cooldown_until = time.time() + 5.0
                self.actions.speak(decision.get('spoken') or decision.get('response', ''))

            try:
                self.memory.log_episode(
                    transcript=transcript.get('text', ''),
                    intent=decision.get('action', 'unknown'),
                    response=decision.get('response', ''),
                    backend=decision.get('backend', 'unknown'),
                    latency=decision.get('duration_s', 0),
                    confidence=decision.get('confidence', 0),
                    success=execution.get('success', False) if execution else True,
                )
            except Exception as _e:
                logger.debug(f"Memory log: {_e}")

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
