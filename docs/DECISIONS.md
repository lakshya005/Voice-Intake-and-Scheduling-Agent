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
