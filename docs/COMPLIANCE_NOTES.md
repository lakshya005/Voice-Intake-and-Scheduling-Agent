# COMPLIANCE NOTES

This project uses synthetic data only. It is not HIPAA compliant and does not claim to be.

## Safeguards built in
- Verification (name + DOB, max 3 attempts) before any record access; enforced in the backend.
- Minimum-necessary disclosure: fixed allowlist of fields the agent may read aloud.
- Audit log of every record access (`tool_calls`).
- PII redaction in logs and stored transcripts.
- Deterministic safety screen and fail-closed verification.
- Secrets in `.env`, never committed.

## Required for a real deployment (not built here)
- Business associate agreements with every vendor handling PHI (STT, LLM, TTS, telephony, hosting).
- Encryption at rest and in transit, key management.
- Formal risk assessment, access controls and authentication for staff.
- Retention and deletion policies, breach response procedure, staff training.
