

# Jarvis v0.11.0 Recommendations

Based on deep research review against current v0.10.0 state.

---

## KEEP as shipped

### 1. openWakeWord (hey_jarvis)
The research confirms openWakeWord is the clear winner for your use case. v0.6.0 adds custom verifier models and improved training — both useful later. Porcupine's commercial model licensing is a non-starter for a personal project. *"openWakeWord produces a model that is more accurate than Porcupine"* on tested data. **No action needed.**

**One tweak worth doing now:** If you haven't already, enable `vad_threshold` on the Silero VAD bundled with openWakeWord. The research is explicit: *"can significantly reduce false-positive activations in the presence of non-speech noise."* This is a one-line config change, not an upgrade.

### 2. Groq Whisper-Large-v3-Turbo for STT
At $0.02/hour (18× cheaper than OpenAI) and ~200ms real-world latency, nothing touches this for your architecture. The research confirms: *"Groq is consistently 4–5x faster than OpenAI's endpoint."* Your chunk-based pipeline (wake → record → transcribe) is exactly the right pattern for Groq's segmented processing. The lack of native streaming is irrelevant since you're not building a real-time captioning system.

### 3. SQLite 4-layer memory
The research validates this emphatically: *"SQLite is the sleeper hit of solo-user AI memory in 2026"* and *"For solo dev use cases... SQLite storage, $0/month cost, handle under 100K memories with ease."* Your 4-layer architecture (in-context, episodic, semantic, procedural) maps exactly to the research's recommended taxonomy. **Do not migrate to a vector DB.** You are nowhere near the 100K+ memory threshold where it matters.

### 4. ElevenLabs TTS (Brian / eleven_flash_v2_5)
Research confirms ElevenLabs is #1 in blind listening tests: *"chosen as the top voice 37 times versus the next competitor at 19."* Flash v2.5 at 75ms latency is the fastest option available. **Keep for English.**

### 5. Ensemble think_ensemble() (Claude + Gemini parallel)
The research strongly validates multi-model: *"the era of picking one model and committing is over"* and *"no single model dominates every task."* Your Claude + Gemini parallel pattern is the right foundation.

### 6. Vision, shop, github_watch, self_analyze
All shipped features are architecturally sound and aligned with research trends.

---

## UPGRADE (specific changes)

### U1. Upgrade ensemble to Tiered Intelligence Stack (HIGH VALUE / MEDIUM EFFORT)
Your current `think_ensemble()` fires Claude + Gemini in parallel for everything. This is wasteful. The research describes the dominant pattern:

> *"A single application might route 70% of traffic to DeepSeek V4-Flash, 25% to Claude Sonnet 4.6, and reserve 5% for Claude Opus 4.7 — achieving overall performance indistinguishable from routing everything to a frontier model, at roughly 15% of the cost."*

**Specific change:** Add a lightweight classifier step before LLM calls:
- **Simple queries** (time, weather, quick facts, memory lookups) → **Qwen 2.5:7b** (already deployed, $0)
- **Standard queries** (summaries, planning, code review) → **Claude Sonnet 4.6** alone
- **Complex/high-stakes** (multi-step reasoning, novel analysis, critical decisions) → **think_ensemble()** (Claude + Gemini parallel)

The classifier can be Qwen itself with a 3-line system prompt: classify intent as `simple | standard | complex`. This cuts your API costs ~60-70% while preserving quality where it matters.

### U2. Add procedural memory extraction to nightly reflection (HIGH VALUE / LOW EFFORT)
Your nightly reflection currently generates daily insights. The research identifies a gap:

> *"Procedural memory — how you like tasks done — structured key-value or graph nodes"*

Your reflection scheduler should also extract **patterns in your preferences**: "User always asks for code in Python", "User prefers bullet points over paragraphs", "User wants prices in SAR not USD." Store these as key-value pairs in a `procedural_memory` SQLite table. Inject the top-N relevant ones into system prompts. This is the difference between a smart assistant and *your* smart assistant.

### U3. Vision: Use Files API for multi-turn image conversations (MEDIUM VALUE / LOW EFFORT)
The research flags a critical efficiency issue you're probably hitting:

> *"In multi-turn conversations, each request resends the full conversation history. If images are base64-encoded, the full image bytes are included in the payload on every turn, which can significantly increase request size and latency."*

**Switch to Anthropic's Files API** for vision: upload once, reference by `file_id` in subsequent turns. This reduces payload size and latency in multi-turn image analysis sessions. Also add pre-processing: minimum 200px short edge, auto-rotation correction before submission.

### U4. Upgrade self_analyze toward sandbox self-improvement (HIGH VALUE / HIGH EFFORT — staged)
Your current `self_analyze` is read-only code review. The research shows the next step is achievable but must be staged carefully:

> *"The key principle is to separate experimentation from deployment: allow the agent to explore and improve within a controlled sandbox, while ensuring that any changes that affect real systems are carefully validated before being applied."*

**Phase 1 (v0.11.0):** Let self_analyze *propose* code patches (git diff format) and write them to a `proposed_patches/` directory. Human reviews and applies.

**Phase 2 (v0.12.0):** Auto-apply patches to a staging branch, run test suite, require human `approve` command before merge. Never auto-deploy.

The research is crystal clear on the boundary: *"AI self-improvement only works reliably where outcomes are verifiable."* Your test suite is the gate. No tests = no auto-modification.

---

## ADD (new high-value features)

### A1. Smart model routing with quality scoring (HIGH VALUE / MEDIUM EFFORT)
Beyond the tiered stack (U1), add response quality scoring for the ensemble path. When both Claude and Gemini respond:

The research shows measurable capability gaps: *"Claude's schema validation: 97.3% vs GPT's 91.2%. Gemini's factual accuracy: 94.2% vs GPT's 89.7%."* Use the non-generating model as a judge:

```
response_a = claude(query)
response_b = gemini(query)
winner = claude.judge(response_a, response_b, query)  # or gemini.judge()
```

Log which model wins per query category. After 2 weeks, you have empirical routing data specific to *your* usage patterns.

### A2. Morning brief with OpenJarvis-style digest pattern (MEDIUM VALUE / LOW EFFORT)
You already have a morning brief. The research highlights Stanford's OpenJarvis preset `morning-digest-mac` as a proven pattern. Enrich your brief with:
- GitHub watch results (already have)
- Memory insights from overnight reflection (already have)
- **NEW:** Calendar/task summary for the day
- **NEW:** Trending HN/Reddit posts matching your interests (filterable)
- **NEW:** KSA market prices for watched components (from shop module)

This is a scheduler enhancement, not a new system.

### A3. Amazon SA API migration — Creators API (HIGH VALUE if shop module uses Amazon / LOW EFFORT)
**Critical deprecation alert from research:**

> *"Amazon's Product Advertising API (PA-API) was deprecated on April 30th, 2026. You must migrate to the Creators API."*

If your `shop` module queries Amazon.sa, this is **broken right now**. Migrate immediately. Use marketplace locale `www.amazon.sa`, default language `en_AE`. For B2B procurement, also integrate Selling Partner API (SP-API) which remains active.

### A4. Arabic TTS voice clone for Egyptian Arabic (MEDIUM VALUE / MEDIUM EFFORT)
The research reveals a critical gap if you want Egyptian Arabic output:

> *"ElevenLabs explicitly lists Arabic (Saudi Arabia, UAE) — notably not Egyptian Arabic. ElevenLabs' Arabic support has a Gulf Arabic bias. For Egyptian Arabic specifically, voice cloning of a native Egyptian speaker is the recommended workaround."*

If you need Egyptian Arabic TTS: clone a native Egyptian speaker's voice using ElevenLabs' voice cloning. If MSA or Gulf Arabic is acceptable, the current setup works. **Defer unless Egyptian dialect is a requirement.**

---

## SKIP / DEFER

### ❌ SKIP: Migrating to an agent framework (LangGraph, CrewAI, AutoGen)
Your custom pipeline works. The research shows these frameworks add value for *multi-agent teams* and *enterprise observability*, neither of which applies to a solo-user voice assistant. LangGraph's 62% task completion rate is impressive but you're not running complex multi-node agentic workflows — you're running a voice pipeline with tool calls.

> *"LangGraph's state management requires careful schema design upfront — one content pipeline system had to be refactored three times as requirements evolved."*

The refactoring cost exceeds the benefit. Your modular Python architecture is more maintainable for a solo dev. **Revisit only if you need durable multi-step task execution (e.g., "research X, draft Y, email Z" as a single command).**

### ❌ SKIP: Deepgram / AssemblyAI migration
Groq Whisper is faster and cheaper than both for your chunk-based architecture. Deepgram Flux has better streaming, but you don't need streaming. *"Groq is the fastest for chunk-based transcription"* — that's your architecture.

### ❌ SKIP: Vector database migration (Pinecone, Qdrant, Chroma)
Research is explicit: *"The cost gap is significant: SQLite is a free local file, while Pinecone's paid plan starts at $50/month."* You're under 100K memories. SQLite + FTS5 handles your scale. Revisit at 100K+ entries or if semantic search quality degrades measurably.

### ❌ SKIP: OpenClaw integration
Despite 300K GitHub stars, the research flags: *"Security researchers have raised valid concerns about the broad permissions the agent requires... the skill repository still lacks rigorous vetting for malicious submissions."* The architecture (self-writing skills with broad system access) is antithetical to your controlled pipeline. Interesting to watch, dangerous to adopt.

### ⏳ DEFER: Opus 4.7 vision upgrade
*"Opus 4.7 can accept images up to 2,576 pixels on the long edge (~3.75 megapixels), more than three times as many as prior models."* This matters for fine-print reading and dense data tables. **Defer until you hit a concrete resolution limitation** with Sonnet 4.6 vision. The cost increase isn't justified for general clipboard/screenshot analysis.

### ⏳ DEFER: Full self-modifying code (DGM-style)
The research is seductive — *"performance improved from 20.0% to 50.0%"* — but the prerequisite is a comprehensive test suite with automated evaluation. Build that first (see U4 Phase 1). **Target v0.13.0 at earliest.**

### ⏳ DEFER: Noon.com programmatic search
No public API exists. Options are NoonSeller (analytics, not real-time search) or Apify scraping (*"residential proxies strongly recommended"*). Both are fragile. **Defer until Noon releases a buyer-side API or your shop module has proven demand for Noon-specific results.**

---

## UPDATED v0.11.0 PRIORITY LIST

Ranked by **(value × confidence) / effort**:

| # | Feature | Type | Effort | Expected Impact |
|---|---------|------|--------|----------------|
| **1** | Tiered model routing (classifier → Qwen/Sonnet/Ensemble) | UPGRADE | 2-3 days | 60-70% API cost reduction, same quality |
| **2** | Amazon SA Creators API migration | ADD | 1
| 2 | Response quality scoring (judge model) | NEW | 1-2 days | Enables data-driven prompt tuning; feeds back into routing accuracy |
| 3 | Procedural memory extraction in nightly reflection | UPGRADE | 2-3 days | Persistent skill retention; fewer repeated instructions across sessions |
| 4 | Proposed code patches directory (self_analyze phase 1) | NEW | 2-3 days | Foundation for self-improvement loop; reduces manual refactor effort |
| 5 | Morning brief enrichment (calendar + HN + component prices) | UPGRADE | 1-2 days | Daily utility jump; makes Jarvis the single morning dashboard |
| 6 | Amazon SA Creators API migration (shop module) | NEW | 3-4 days | Monetisation pathway; unlocks affiliate revenue on product recs |
| 7 | Vision Files API + image preprocessing | NEW | 2-3 days | Multimodal capability unlock; supports OCR, photo Q&A, diagram parsing |
| 8 | VAD threshold tweak for openWakeWord | FIX | 0.5-1 day | Reduces false wakes & missed triggers; immediate UX polish |
| 9 | Egyptian Arabic voice clone | NEW | 3-5 days | Native-feel interaction in Arabic; strong differentiator for personal use |
| 10 | Streaming STT evaluation (future) | RESEARCH | 1-2 days | Benchmarks Whisper-streaming vs current; informs latency roadmap |
