-- Voice Intake & Scheduling Agent: schema. Synthetic data only.
-- Status columns use TEXT + CHECK (not ENUM types) so values are easy to change later.

DROP TABLE IF EXISTS access_log, staff_sessions, staff_users, eval_results, eval_runs, handoffs, tool_calls, turns,
    appointments, holds, calls, visits, slots, providers, patients CASCADE;

CREATE TABLE patients (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    dob         DATE NOT NULL,
    phone       TEXT
);
-- verify_patient looks up by name + DOB; this keeps a match unambiguous.
CREATE UNIQUE INDEX patients_identity_uq
    ON patients (lower(first_name), lower(last_name), dob);

CREATE TABLE providers (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT NOT NULL,
    specialty  TEXT NOT NULL
);

CREATE TABLE slots (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id BIGINT NOT NULL REFERENCES providers(id),
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ NOT NULL,
    visit_type  TEXT NOT NULL,
    CHECK (end_time > start_time),
    UNIQUE (provider_id, start_time)          -- a provider can't have two slots at once
);
CREATE INDEX slots_start_idx ON slots (start_time);

-- Past visits the agent may read back (M2.5). Read-only for the agent.
CREATE TABLE visits (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id    BIGINT NOT NULL REFERENCES patients(id),
    provider_id   BIGINT NOT NULL REFERENCES providers(id),
    visit_date    DATE NOT NULL,
    reason        TEXT NOT NULL,
    notes_summary TEXT
);
CREATE INDEX visits_patient_date_idx ON visits (patient_id, visit_date DESC);

CREATE TABLE calls (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at            TIMESTAMPTZ,
    channel             TEXT NOT NULL DEFAULT 'browser' CHECK (channel IN ('browser', 'phone')),
    verified_patient_id BIGINT REFERENCES patients(id),   -- the gate for record access
    outcome             TEXT CHECK (outcome IN ('booked', 'escalated', 'abandoned', 'failed')),
    summary_json        JSONB
);

CREATE TABLE holds (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slot_id     BIGINT NOT NULL REFERENCES slots(id),
    patient_id  BIGINT NOT NULL REFERENCES patients(id),
    call_id     BIGINT NOT NULL REFERENCES calls(id),
    expires_at  TIMESTAMPTZ NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'released', 'converted'))
);
-- At most one ACTIVE hold per slot. Released/converted rows are kept as history.
CREATE UNIQUE INDEX holds_one_active_per_slot ON holds (slot_id) WHERE status = 'active';

CREATE TABLE appointments (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slot_id         BIGINT NOT NULL UNIQUE REFERENCES slots(id),   -- last line of defense vs double booking
    patient_id      BIGINT NOT NULL REFERENCES patients(id),
    reason          TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,                          -- a retry can't create a second row
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE turns (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    call_id           BIGINT NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    idx               INT NOT NULL,
    role              TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text              TEXT,
    t_user_stop       TIMESTAMPTZ,
    t_stt_final       TIMESTAMPTZ,
    t_llm_first_token TIMESTAMPTZ,
    t_tts_first_byte  TIMESTAMPTZ,
    interrupted       BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (call_id, idx)
);

-- Doubles as the audit log: every tool call, including record access.
CREATE TABLE tool_calls (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    call_id     BIGINT NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    turn_id     BIGINT REFERENCES turns(id),
    name        TEXT NOT NULL,
    args_json   JSONB,
    result_json JSONB,
    latency_ms  INT,
    status      TEXT NOT NULL CHECK (status IN ('ok', 'error', 'timeout', 'denied'))
);
CREATE INDEX tool_calls_call_idx ON tool_calls (call_id);

-- Staff who work the dashboard. Created before handoffs, which record who claimed them.
CREATE TABLE staff_users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,                              -- scrypt, never the password
    role          TEXT NOT NULL CHECK (role IN ('admin', 'agent'))
);

-- Only the hash of the session token is stored, so a database leak does not hand out live sessions.
CREATE TABLE staff_sessions (
    token_hash TEXT PRIMARY KEY,
    staff_id   BIGINT NOT NULL REFERENCES staff_users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE handoffs (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    call_id      BIGINT NOT NULL REFERENCES calls(id),
    reason       TEXT NOT NULL,
    summary_json JSONB NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'claimed', 'closed')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_by   BIGINT REFERENCES staff_users(id),
    claimed_at   TIMESTAMPTZ,
    closed_at    TIMESTAMPTZ
);

-- Who looked at what: opening a call, revealing unmasked text, opening a patient from a handoff.
CREATE TABLE access_log (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staff_id BIGINT NOT NULL REFERENCES staff_users(id),
    action   TEXT NOT NULL,
    call_id  BIGINT REFERENCES calls(id) ON DELETE SET NULL,
    at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail   JSONB
);

CREATE TABLE eval_runs (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    git_sha    TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    suite      TEXT NOT NULL
);

CREATE TABLE eval_results (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id             BIGINT NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    scenario           TEXT NOT NULL,
    persona            TEXT,
    perturbation       TEXT,
    success            BOOLEAN NOT NULL,
    commitments_json   JSONB,
    hallucinated_count INT NOT NULL DEFAULT 0,
    p50_ms             INT,
    p95_ms             INT,
    cost_usd           NUMERIC(10, 6)
);
