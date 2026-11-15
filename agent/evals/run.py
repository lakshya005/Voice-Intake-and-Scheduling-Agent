"""Run every eval: scripted callers, then the failure drill, then the commitment ledger.

Run from agent/:  uv run python -m evals.run [--pace 45]
Scenarios run one at a time with a pause between them: Groq's free tier allows 8,000 tokens a minute,
about one scenario's worth. Exits 1 if any scenario fails, a drill leaves the wrong handoff, or the ledger finds a violation."""

import argparse
import subprocess
import sys
import time

import psycopg

from evals.ledger import URL, check

NORMAL = [
    "happy_path",
    "change_of_mind",
    "wrong_birthday_three_times",
    "chest_pain",
    "asks_for_a_person",
    "asks_for_medical_advice",
]
# failure drill: manifest entry -> the handoff reason the call must end with
FAULTS = {
    "faults/find_slots": "scheduling system unavailable",
    "faults/hold_slot": "scheduling system unavailable",
    "faults/verify_patient": "scheduling system unavailable",
    "faults/llm": "assistant service error",
}


def suite(manifest: str, flag: str, value: str) -> bool:
    cmd = [sys.executable, "-m", "pipecat.evals", "suite", manifest, flag, value]
    return subprocess.run(cmd, check=False).returncode == 0


def last_handoff(conn) -> str | None:
    row = conn.execute(
        "SELECT h.reason FROM calls c LEFT JOIN handoffs h ON h.call_id = c.id ORDER BY c.id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pace", type=int, default=45, help="seconds to wait between scenarios"
    )
    pace = ap.parse_args().pace
    failures = []
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("DELETE FROM holds")
        conn.execute("DELETE FROM appointments")
        first_id = conn.execute(
            "SELECT coalesce(max(id), 0) + 1 FROM calls"
        ).fetchone()[0]
        runs = [("evals/manifest.yaml", "-s", n, None) for n in NORMAL]
        runs += [
            ("evals/manifest_faults.yaml", "-p", n, why) for n, why in FAULTS.items()
        ]
        for i, (manifest, flag, name, why) in enumerate(runs):
            if i:
                time.sleep(pace)
            if not suite(manifest, flag, name):
                failures.append(f"{name}: scenario failed")
            if why and (got := last_handoff(conn)) != why:
                failures.append(f"{name}: expected handoff {why!r}, got {got!r}")
        failures += check(conn, first_id)
    print("\n== eval summary ==")
    print(*(failures or ["all scenarios, drills and ledger checks passed"]), sep="\n")
    sys.exit(1 if failures else 0)
