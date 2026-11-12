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
