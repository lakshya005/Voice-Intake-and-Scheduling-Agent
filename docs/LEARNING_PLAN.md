# LEARNING PLAN

Study each block **before** its milestone (about 3–5 hours each). Primary sources first, videos second.
Search tip for YouTube: use the exact terms in **bold**; prefer talks from Daily/Pipecat, Deepgram, LiveKit, and AI Engineer conference channels.

---

## Before M1: How a voice agent works
**Concepts**
- **Cascaded pipeline** (VAD → STT → LLM → TTS) vs. **speech-to-speech** models. Why we chose cascaded: control, swappable vendors, debuggability.
- **Audio basics**: sample rate (16 kHz vs. 8 kHz phone), PCM frames, chunk size, **μ-law** encoding.
- **Streaming**: partial vs. final transcripts; streaming LLM tokens; streaming TTS.
- **VAD** (voice activity detection) vs. **semantic turn detection / end-of-utterance**. Why silence alone cuts people off.
- **Barge-in / interruptions** and context truncation.
- **Latency budget**: where the ~1 s goes.
- **WebRTC vs. WebSockets** for audio: UDP, jitter buffers, why WebRTC for real-time media.

**Read**
- docs.pipecat.ai: Introduction, Core concepts (frames, processors, pipelines), Speech input & turn detection.
- Pipecat GitHub examples (`pipecat-ai/pipecat` → `examples/`), and the Smart Turn repo (`pipecat-ai/smart-turn`).
- Deepgram docs: streaming STT and Flux.

**Watch** (search): **"Pipecat voice agent tutorial"**, **"voice AI latency Kwindla Kramer"**, **"WebRTC explained"**, **"semantic VAD turn detection"**.

**Interview questions you must answer**
1. Walk me through what happens between the user finishing a sentence and hearing the first word back.
2. Why not just wait for 1 second of silence to end a turn?
3. What happens to the LLM context when a user interrupts mid-response?
4. Why WebRTC instead of a plain WebSocket for browser audio?
5. Cascaded vs. speech-to-speech: when would you pick each?

---

## Before M2: Tools, state, and correctness
**Concepts**
- **LLM tool/function calling** and structured outputs.
- **State machines for conversations** (Pipecat Flows): why not one giant prompt.
- **Transactions, isolation levels, row locks** (`SELECT ... FOR UPDATE`), **unique constraints** as the last line of defense.
- **Idempotency keys**: retries without double side effects.
- **Hold/reservation pattern with TTL** (same idea as ticketing and hotel booking).
- **Timeouts, retries with backoff, graceful degradation** in a live conversation.
- **Guardrails**: deterministic rules for safety-critical paths; LLM for everything else.

**Read**
- Pipecat docs: function calling, Pipecat Flows.
- PostgreSQL docs: Transaction Isolation, Explicit Locking.
- Stripe engineering blog post on **idempotency keys** (search "Stripe idempotent requests").

**Watch** (search): **"idempotency keys explained"**, **"database race conditions double booking"**, **"LLM function calling tutorial"**.

**Interview questions**
1. Two callers try to book the same slot at the same moment. Walk me through what happens in your system.
2. The network drops right after `confirm_booking` succeeds and the agent retries. What prevents a double booking?
3. Why is the safety screen a fixed rule list and not the LLM's judgment?
4. A tool call takes 4 seconds. What does the caller hear, and what does the system do?
5. Why a state machine instead of one big system prompt?

---

## Before M3: Evaluating non-deterministic systems
**Concepts**
- **Scripted vs. simulated evals**; **LLM-as-judge** and its failure modes (bias, leniency); **calibrating a judge** against a few human labels.
- **Hallucination vs. grounded claims**: checking claims against a source of truth (your DB), not against another LLM's opinion.
- **Percentiles (p50/p95)** and why averages lie about latency.
- **Flaky tests** in probabilistic systems: repeated runs, thresholds, pass rates.
- **CI gating** on metrics.
- **Audio robustness**: noise, codecs, accents.

**Read**
- Pipecat docs: Evals overview, scripted scenarios, simulated scenarios, eval suites.
- Search: **"LLM as a judge best practices"**, **"evaluating voice agents"**, **"Hamel Husain evals"** (his blog is strong on practical evals).

**Interview questions**
1. How do you know a change to your prompt made the agent better, not worse?
2. How do you detect that the agent told a caller "you're booked" when it wasn't?
3. Your eval pass rate moves between 88% and 93% with no code change. How do you set a CI threshold?
4. Why do you report p95 latency and not average?
5. What can't your local eval suite catch that production monitoring would?

---

## Before M4: Observability and dashboards
**Concepts**
- **Tracing a request across stages** (spans); per-turn timing events.
- **Structured logging** and **PII redaction** before storage.
- Designing a **human-in-the-loop handoff queue** (claim/close, summaries).

**Read / watch** (search): **"OpenTelemetry basics"**, **"TanStack Query tutorial"** (you know TanStack Table already).

**Interview questions**
1. A caller complains the agent was slow at one point. How do you find out why?
2. What do you log, and what do you never log?
3. What does a good handoff summary contain, and why structured instead of a transcript?

---

## Before M5: Telephony
**Concepts**
- **PSTN → Twilio → WebSocket media stream**; **8 kHz μ-law** and resampling.
- **DTMF** (keypad input); why phone audio degrades STT accuracy.

**Read**: Twilio docs on **Media Streams**; Pipecat docs on Twilio/telephony transports.

**Interview questions**
1. What changes when moving from browser audio to a phone line, and how did your evals catch it?
2. Where does added latency come from on phone calls?

---

## System-design questions this project prepares you for
- "Design a voice AI receptionist for 1,000 clinics." (concurrency, per-tenant config, cost per call, vendor fallback)
- "How would you scale to 500 concurrent calls?" (one bot process per call, autoscaling workers, stateless backend, DB connection pooling)
- "How do you control cost per call?" (model choice, token limits, TTS caching for fixed phrases)
- "A vendor (STT/TTS/LLM) goes down mid-call. What happens?" (timeouts, fallbacks, escalate)

Write your own answer to each in `docs/DECISIONS.md` as you build.
