# DECISIONS

Each entry: context, options, choice, why.

## 1. FastAPI + plain SQL (psycopg), no ORM
- **Context:** Backend exposes ~6 tool endpoints to a real-time voice agent; booking correctness depends on transactions and row locks.
- **Options:** Django + ORM; FastAPI + ORM (SQLAlchemy); FastAPI + raw SQL.
- **Choice:** FastAPI + psycopg with plain SQL.
- **Why:** Async-native fits the live pipeline; Pydantic gives strict tool contracts; Django's admin/auth/ORM go unused; raw SQL makes every transaction and lock explicit and explainable.

## 2. Synthetic data only; HIPAA-aware, not HIPAA-compliant
- **Context:** Healthcare use case, portfolio project, free-tier vendors without BAAs.
- **Options:** Claim compliance; ignore the topic; build HIPAA-style safeguards and be honest about the gap.
- **Choice:** Third option.
- **Why:** Compliance is organizational (BAAs, risk assessments, policies), not achievable solo. Showing the safeguards (access gating, audit log, field allowlist, PII redaction) plus knowing what production needs is the stronger signal.

## 3. Record lookup is read-only and verification-gated in the backend (M2.5)
- **Context:** Later scope: verified callers can ask about their last visit and reason.
- **Choice:** Backend rejects record tools unless the call has a verified patient; fixed field allowlist; every access logged in `tool_calls`; ledger checks claims against the DB.
- **Why:** The LLM must never be the access-control layer; grounding claims in the DB prevents hallucinated facts.

## 4. Phone numbers: deterministic TTS transform, not a prompt instruction
- **Context:** Kokoro read "555-212-1345" as a quantity ("one thousand three hundred...").
- **Options:** tell the LLM to write digits separately; use Pipecat's `expand_phone_numbers` TTS text transform.
- **Choice:** the transform, wrapped to normalize Unicode hyphens first.
- **Why:** the LLM emitted U+2011 non-breaking hyphens, which Pipecat's regex doesn't match. Deterministic code beats a prompt the model can ignore. Limit: only 10-digit US numbers.

## 5. Turn detection: Silero + Smart Turn (Flux kept as a switch)
- **Context:** M1 needs end-of-turn detection that doesn't cut callers off.
- **Options:** (A) Silero VAD + Smart Turn v3 with Deepgram Nova STT, all turn logic local; (B) Deepgram Flux, one cloud model for STT and end-of-turn.
- **Observed:** both gave ~1-1.5 s voice-to-voice (timing observer: 1.3-1.5 s on Flux) and no cut-offs during a 15-20 s ramble. Flux ended the turn early on 2 of 5 turns in one booking call ("Assure, please. Go ahead." split in two) and misheard "wait, stop" as an interruption. Flux sends the transcript and the stop frame about 1 ms apart, so STT time is not separable.
- **Choice:** Smart Turn (default). A cut-off sentence in a booking call means a wrong answer, so reliability beats the small speed gain. Switching back is `TURN_MODE=flux`. No side-by-side ms comparison was run; revisit if latency becomes the problem.

## 6. Barge-in context truncation is sentence-granular with Kokoro
- **Context:** Interrupting the agent mid-answer. Goal: context keeps only what the caller heard.
- **Observed:** three interrupted turns stored `content=''`. Kokoro gives no word timestamps, so Pipecat adds a sentence to the context only after its audio finishes generating (documented in `TTSService._push_spoken_text`). A sentence interrupted midway is dropped entirely.
- **Consequence:** safe direction (never stores unheard words) but lossy: the agent forgot its own partial answer and repeated it. Mitigation: short sentences in the prompt. A TTS with word timestamps would give word-level truncation.
- **Also observed:** Flux transcribed "wait, stop" as "which top", "weird stop", "weed stop"; the junk then triggered new replies.

## 7. Conversation flow: Pipecat Flows state machine, not one big prompt
- **Context:** M2 needs a booking dialogue where wrong steps (booking before verifying, offering unreturned slots) are impossible, not just discouraged.
- **Options:** (A) one system prompt plus tools; (B) Pipecat Flows, a YAML state machine where the config decides transitions and tools return a `status` the config branches on.
- **Choice:** B. The LLM only talks and calls tools; the backend enforces the rules (verification gate, holds, unique constraints). Emergency and handoff nodes are scripted, with no LLM improvisation.
- **Cost:** the LLM still decides *when* to call a tool, so it can skip one. The evals caught it saying "someone will be with you" on a failed verification without calling `escalate_to_staff`.

## 8. Evals: scripted callers first, LLM-played callers later
- **Context:** M3 needs repeatable tests of the real bot. Groq's available models made poor simulated callers: gpt-oss wrote the bot's lines and hung up early, and the smaller models hit rate limits.
- **Choice:** Pipecat Evals with scripted caller turns (text modality, real flow, real tools, real backend), plus a commitment ledger (`agent/evals/ledger.py`) that checks what the bot promised against Postgres.
- **Found by the evals:** early self-escalation after two wrong birthdays, hanging up on a medical-advice question, a staff promise with no handoff filed, and silent calls when the LLM provider returns 429.
- **Limit:** Groq's free tier allows 8,000 tokens per minute on gpt-oss-120b, about one scenario per minute, so a full run is slow and can flake. LLM-played personas (angry, rambling) are still to do.

## 9. Failure handling: second model on rate limit, scripted handoff on any other LLM error, failure drill in the evals
- **Context:** Groq's free tier (8,000 tokens a minute on gpt-oss-120b) returned 429 during evals and left the caller in silence. Paying for a higher tier is not an option for this project.
- **Choice:** `FallbackGroqLLMService` retries once on `openai/gpt-oss-20b` (its own quota) when the primary is rate limited. Any other LLM error moves the call to the scripted `escalated` node (apology, handoff row, end call) instead of silence. A Groq "tool validation failed" error (the model called a tool from the previous step) is ignored, because the next turn recovers; escalating on it caused a false handoff in the first drill.
- **Failure drill:** the bot reads `runner_body.faults` and breaks one dependency on purpose (`find_slots`, `hold_slot`, `verify_patient`, or the LLM). Each drill must end with an `escalated` call and a handoff row with the right reason, and the ledger must find no unbacked promise.
- **Fixed on the way:** an outage of `hold_slot` was reported to the caller as "that time was taken"; `find_slots` offered staff but never moved the call; `record_reason` accepted an empty reason when the model chained it before the caller answered.
- **Limits:** the fallback model's tool-calling quality is not measured; if the backend is fully down a handoff cannot be filed, so it is appended to `agent/unsent_handoffs.jsonl` for staff to read by hand; the eval suite is paced (about 8 minutes) rather than fast.

## 10. Dashboard: React SPA, per-staff accounts, masking on read
- **Context:** M4 needs staff to review calls and work handoffs without every personal detail on screen by default.
- **Choices (yours):** Vite + React + TypeScript + Tailwind + TanStack Table/Query; per-staff accounts with roles (admin, agent) and a server-side session in an HttpOnly cookie.
- **Access rules:** transcripts are masked unless an admin reveals them, and every view or reveal is written to `access_log`. A patient's details open only for the staff member who claimed the handoff, only if the agent verified the caller, and the view is logged. An unverified caller never exposes a record.
- **Masking on read, not on write (my call, flag if you disagree):** the transcript is stored as spoken and masked when the dashboard reads it, using the verified patient's known values plus patterns. Pro: nothing is lost, the handoff and audit views stay accurate, and the masking rules can improve without rewriting data. Con: the database holds raw personal details, so write-time masking is still the stronger design and is not done.
- **Limits:** masking is best effort (a name nobody introduced or a garbled one can slip through); scrypt password hashes and sessions are hand-rolled with the standard library, not a vetted auth framework; demo passwords live in the seed file; no CSRF token beyond SameSite=Lax cookies; no rate limit on login.
