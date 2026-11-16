-- One-time upgrade of a database created before the dashboard: adds the staff tables and handoff columns without
-- touching data. A fresh database gets all of this from schema.sql.
CREATE TABLE IF NOT EXISTS staff_users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'agent'))
);
CREATE TABLE IF NOT EXISTS staff_sessions (
    token_hash TEXT PRIMARY KEY,
    staff_id   BIGINT NOT NULL REFERENCES staff_users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE handoffs
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS claimed_by BIGINT REFERENCES staff_users(id),
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS access_log (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staff_id BIGINT NOT NULL REFERENCES staff_users(id),
    action   TEXT NOT NULL,
    call_id  BIGINT REFERENCES calls(id) ON DELETE SET NULL,
    at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail   JSONB
);
