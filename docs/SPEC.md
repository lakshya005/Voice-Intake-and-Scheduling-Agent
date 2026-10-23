# SPEC: Voice Intake & Scheduling Agent

## 1. What we're building
A real-time voice agent for a (fictional) medical office. A caller talks to it in the browser (later over the phone). The agent:
1. Verifies the caller (name + date of birth).
2. Collects the reason for the visit.
3. Screens for emergencies and escalates to a human if needed.
4. Finds and books an appointment slot, reads it back, and confirms.
5. Hands off to a human with a structured summary when it can't help.

Plus two things that make it a serious engineering project:
- **A staff dashboard** showing every call: transcript, extracted intake, booking, per-turn latency waterfall, handoff queue.
- **An eval harness** that runs ~100 simulated callers per build, catches hallucinated commitments, and gates merges in CI.

Later re-skin target (config change, not a rewrite): insurance first-notice-of-loss intake.

### Non-goals
- No medical advice or triage beyond a fixed red-flag list.
- No real EHR integration (Project 1 covers FHIR later).
- No speech-to-speech models (e.g., OpenAI Realtime) as the core. We build the pipeline ourselves to learn it.
- No auth/multi-tenancy for the dashboard in v1 (Project 2 covers that).

## 2. Stack
| Layer | Choice | Notes |
|---|---|---|
| Voice orchestration | Pipecat (Python, latest stable) | Pipecat Flows for the conversation state machine (`pipecat.flows`) |
| Transport | Pipecat's built-in WebRTC transport (browser) → Twilio Media Streams (phone, M5) | Browser first, no phone number needed |
| VAD / turn detection | Silero VAD + Smart Turn v3, or Deepgram Flux's built-in turn detection | Compare both, log the decision |
| STT | Deepgram Flux (streaming) | $200 free credit |
| LLM | Groq or Gemini Flash (free tier), behind one interface so it's swappable | Fast time-to-first-token matters most |
| TTS | Kokoro (local, open-source) | Fallback: a cloud TTS free tier |
| Backend API | FastAPI + psycopg (plain SQL, so I see every query) + PostgreSQL (Docker) | Tools the agent calls |
| Frontend | Vite + React + TypeScript + Tailwind + TanStack Table/Query | Dashboard + a "call" page |
| Evals | Pipecat Evals (`pipecat eval`) + our extensions | Judge LLM via Ollama locally |
| CI | GitHub Actions | Smoke eval suite on PR |

## 3. Repo layout
```
voice-intake-agent/
  CLAUDE.md
  docker-compose.yml          # postgres (+ ollama optional)
  .env.example
  agent/                      # Pipecat bot
    bot.py                    # pipeline assembly
    flows/                    # Flows node definitions
    tools/                    # tool functions → call backend API
    metrics/                  # per-turn timing observer
  backend/                    # FastAPI
    app/main.py
    app/routes/               # patients, slots, holds, bookings, calls, handoffs
    app/db/schema.sql
    app/db/seed.py            # synthetic patients, providers, slots
  web/                        # React dashboard + call page
  evals/
    scenarios/                # YAML scenarios
    personas/                 # caller personas
    checks/commitment_ledger.py
    perturb/                  # audio noise / 8kHz / speed
    run_suite.py
  docs/
    SPEC.md  LEARNING_PLAN.md  DECISIONS.md  ARCHITECTURE.md
```

## 4. Data model (Postgres)
- `patients(id, first_name, last_name, dob, phone)`: synthetic.
- `providers(id, name, specialty)`
- `visits(id, patient_id, provider_id, visit_date, reason, notes_summary)`: synthetic visit history, read-only for the agent (M2.5).
- `slots(id, provider_id, start_time, end_time, visit_type)`
- `holds(id, slot_id, patient_id, call_id, expires_at, status[active|released|converted])`
- `appointments(id, slot_id, patient_id, reason, idempotency_key UNIQUE, created_at)`, with **UNIQUE(slot_id)** so a slot can't be double-booked.
- `calls(id, started_at, ended_at, channel, verified_patient_id, outcome[booked|escalated|abandoned|failed], summary_json)`
- `turns(id, call_id, idx, role, text, t_user_stop, t_stt_final, t_llm_first_token, t_tts_first_byte, interrupted bool)`
- `tool_calls(id, call_id, turn_id, name, args_json, result_json, latency_ms, status)`
- `handoffs(id, call_id, reason, summary_json, status[open|claimed|closed])`
- `eval_runs(id, git_sha, started_at, suite)` and `eval_results(id, run_id, scenario, persona, perturbation, success, commitments_json, hallucinated_count, p50_ms, p95_ms, cost_usd)`

## 5. Agent tools (backend API contract)
| Tool | Input | Output | Rules |
|---|---|---|---|
| `verify_patient` | first_name, last_name, dob | patient_id or null, attempts_left | Max 3 attempts, then escalate |
| `find_slots` | visit_type, date_from, date_to, provider_id? | up to 3 slots | Only future, unheld, unbooked slots |
| `hold_slot` | slot_id, patient_id, call_id | hold_id, expires_at (TTL 2 min) | Fails if slot held/booked |
| `confirm_booking` | hold_id, idempotency_key | appointment | **[I WRITE]** Idempotent, transactional, converts hold |
| `release_hold` | hold_id | ok | Called on caller rejection or hang-up |
| `escalate` | reason, summary | handoff_id | Summary schema: who, verified?, reason, attempted, why_escalated |
| `get_last_visit` (M2.5) | call_id | date, provider, reason | Read-only. Backend rejects unless the call has a verified patient. Allowlisted fields only |
| `get_visit_history` (M2.5) | call_id, limit | list of the same fields | Same rules; every access logged in `tool_calls` |

## 6. Conversation flow (Pipecat Flows)
`greet → verify_identity → reason_for_visit → safety_screen → find_slots → hold_and_read_back → confirm → wrap_up`
- `escalate` is reachable from every node.
- `safety_screen`: fixed red-flag list (chest pain, can't breathe, stroke signs, suicidal statements, etc.) → scripted "please hang up and call 911" + escalate. No LLM improvisation here.
- Read-back is mandatory before `confirm_booking`.

## 7. Milestones and acceptance criteria

### M0: Setup (half a day)
- Repo, uv, docker-compose Postgres, schema + seed, `.env.example`.
- **Done when:** `seed.py` loads 50 synthetic patients, 3 providers, 2 weeks of slots.

### M1: Voice loop (week 1)
- Browser ↔ Pipecat pipeline: VAD → STT → LLM → TTS, streaming tokens into TTS sentence by sentence.
- **[I WRITE]** A timing observer that records per-turn timestamps into `turns`.
- Barge-in: interrupting cancels TTS and the in-flight LLM call; the context keeps only what the caller actually heard.
- **Done when:** I can talk to it in the browser, interrupt it mid-sentence, and see per-turn timings in Postgres. Compare Silero+Smart Turn vs. Flux turn detection and log results in DECISIONS.md.

### M2: Tools + flow + correctness (week 2)
- FastAPI tool endpoints, Flows state machine, safety screen, escalation.
- Filler phrase when a tool takes >300 ms; tool timeout + retry + graceful escalation.
- **[I WRITE]** `confirm_booking` with a transaction, idempotency key, and hold → appointment conversion.
- **[I WRITE]** A concurrency test: two simulated callers race for the same slot; exactly one succeeds.
- **Done when:** a full call books a real row, red-flag phrases escalate, and the race test passes.

### M2.5: Record lookup (after M2)
- New Flows branch after `verify_identity`: book an appointment, or ask about past visits.
- Read-only `get_last_visit` / `get_visit_history`. Verification gate enforced in the backend, not the prompt.
- Fixed allowlist of fields the agent may read aloud (date, provider, reason). No diagnoses, results, or interpretation.
- Extend the commitment ledger: every factual claim about a visit is checked against the DB.
- **Done when:** a verified caller can ask about their last visit and get a correct answer; an unverified or wrong-DOB caller gets nothing; eval scenarios with invented dates are caught.

### M3: Eval harness (week 3)
- Pipecat Evals scripted + simulated scenarios.
- Persona matrix: cooperative, angry, rambling, interrupter, wrong DOB, asks for medical advice, emergency mention, off-topic.
- **[I WRITE]** Commitment ledger: judge extracts every promise the agent made; a deterministic checker verifies each against the DB. Unbacked promise = hallucinated commitment.
- Audio perturbations: background noise, 8 kHz phone-codec downsample, speed change.
- Metrics: task success, p50/p95 voice-to-voice latency, barge-in recovery, wrong-escalation rate, cost per call → `eval_results`.
- GitHub Action: 20-scenario smoke suite on PR, fail on regression vs. last main run. Full suite nightly or manual.
- **Done when:** one command runs the suite and prints a results table; CI blocks a deliberately broken prompt.

### M4: Dashboard (week 4, first half)
- Calls list, call detail (transcript, extracted intake, booking, tool calls), per-turn latency waterfall, handoff queue (claim/close), eval results over time.
- **Done when:** a recruiter can understand what happened on any call in 10 seconds.

### M5: Phone + write-up (week 4, second half)
- Twilio trial number → Pipecat via Media Streams (8 kHz μ-law).
- `docs/ARCHITECTURE.md` with a diagram, README with a 2-minute demo video, measured numbers from eval runs only.
- **Done when:** I can call the number from my phone and book an appointment.

## 8. Healthcare and compliance posture
Synthetic data only, so HIPAA does not apply to this project, and we do not claim compliance. We design with HIPAA-style safeguards: verification gating, minimum-necessary disclosure (field allowlist), audit logging of every record access, PII redaction in logs, fail-closed verification, deterministic safety paths. A production deployment would additionally need BAAs with every vendor, encryption at rest and in transit, a formal risk assessment, and retention policies. See `docs/COMPLIANCE_NOTES.md`.

## 9. Definition of done (portfolio)
- Live demo video, README with architecture diagram and real eval numbers.
- DECISIONS.md with 10+ entries.
- I can answer every question in LEARNING_PLAN.md without notes.
