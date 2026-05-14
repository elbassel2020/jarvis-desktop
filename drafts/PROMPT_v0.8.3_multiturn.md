# Sprint Prompt: JARVIS v0.8.3 — Multi-Turn Conversation Memory

> Paste this to Claude Code to implement.

---

JARVIS v0.8.3 — Multi-Turn Context Window

Current: each wake event is stateless. Brain gets no conversation history.
Target: last 5 exchanges passed as messages array to LLM.

SCOPE:
- Maintain short-term conversation buffer (last 5 turns) in pipeline
- Inject as messages history into Claude/Gemini calls
- Auto-clear on 5-minute idle
- NO changes to persistent memory.db (this is session-only RAM)

CONSTRAINTS:
- Modify core/pipeline.py: add `self.conversation_buffer = []`
- Modify core/brain_router.py: `_call_claude()` and `_call_gemini()` accept optional `history` param
- Buffer: list of `{'role': 'user'|'assistant', 'content': str}`
- Max 5 turns (10 messages) in buffer
- Auto-clear: track `self.last_interaction_time`, clear if > 300s elapsed
- DO NOT change memory.py or any other file

IMPLEMENTATION STEPS:
1. In pipeline.py `__init__`:
   ```python
   self.conversation_buffer = []
   self.last_interaction_time = 0.0
   CONVO_IDLE_TIMEOUT = 300  # 5 minutes
   ```

2. In `on_wake_detected()`, before brain.think():
   ```python
   # Clear buffer on 5-min idle
   if time.time() - self.last_interaction_time > CONVO_IDLE_TIMEOUT:
       self.conversation_buffer = []
   ```

3. Pass buffer to brain:
   ```python
   decision = self.brain.think(transcript['text'], history=self.conversation_buffer)
   ```

4. After response, append to buffer:
   ```python
   self.conversation_buffer.append({'role': 'user', 'content': transcript['text']})
   self.conversation_buffer.append({'role': 'assistant', 'content': decision.get('spoken', '')})
   if len(self.conversation_buffer) > 10:
       self.conversation_buffer = self.conversation_buffer[-10:]
   self.last_interaction_time = time.time()
   ```

5. In brain_router.py `_call_claude()`:
   - Accept `history: list = None` param
   - Build `messages = (history or []) + [{'role': 'user', 'content': transcript}]`
   - Pass to `messages.create()`

6. In `_call_gemini()`:
   - Build multi-turn `contents` from history if provided

VOICE EXAMPLE:
Turn 1: "what's Schneider's best breaker for 63A?"
Turn 2: "and how does that compare to ABB?"  ← references "that" from previous
Turn 3: "which one is easier to source in KSA?"  ← same context

TESTS: tests/test_multiturn.py — buffer fill, idle clear, history injection

COMMIT: feat: v0.8.3 — multi-turn conversation context (5-turn buffer, 5-min idle clear)
