"""Free every slot before a suite run: delete holds and appointments (call history is kept)."""

import os

import psycopg

URL = os.environ.get(
    "DATABASE_URL", "postgresql://voice:voice@localhost:5433/voice_intake"
)

if __name__ == "__main__":
    with psycopg.connect(URL) as conn:
        conn.execute("DELETE FROM holds")
        conn.execute("DELETE FROM appointments")
