"""Commitment ledger: check what the bot promised against what the database says happened.

Run after a suite:  uv run python -m evals.ledger [--since-id N]
Exits 1 on any violation. A "promise" is an assistant turn saying an appointment is booked."""

import argparse
import os
import re
import sys

import psycopg

from flow_tools import spoken, visit_spoken

URL = os.environ.get(
    "DATABASE_URL", "postgresql://voice:voice@localhost:5433/voice_intake"
)
# shortcut: phrase match on "booked"; replace with an LLM judge that extracts every promise in M3's next pass
PROMISE = re.compile(
    r"\b(is|are|been|you're|you are|it's|all)\s+(now\s+)?booked\b", re.IGNORECASE
)
# a spoken visit date such as "September 11, 2026"; appointment times have no year, so they never match
VISIT_DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}\b"
)
HELD_PROMISE = re.compile(
    r"\b(?:I['’]ve|I have|is|are|been|now)\s+held\b", re.IGNORECASE
)
STAFF_PROMISE = re.compile(
    r"(someone|staff|front desk|a person|a human)\b.{0,40}\b(will|is going to)\b|passing you to",
    re.IGNORECASE,
)


def check(conn, since_id: int) -> list[str]:
    bad = []
    calls = conn.execute(
        "SELECT id, outcome FROM calls WHERE id >= %s ORDER BY id", (since_id,)
    ).fetchall()
    for call_id, outcome in calls:
        say = [
            r[0]
            .replace("\u202f", " ")
            .replace("\u00a0", " ")  # TTS-friendly text uses narrow no-break spaces
            for r in conn.execute(
                "SELECT text FROM turns WHERE call_id = %s AND role = 'assistant' AND text IS NOT NULL",
                (call_id,),
            )
        ]
        promised = [t for t in say if PROMISE.search(t)]
        appt = conn.execute(
            "SELECT s.start_time, p.name FROM tool_calls t "
            "JOIN appointments a ON a.id = (t.result_json->>'appointment_id')::bigint "
            "JOIN slots s ON s.id = a.slot_id JOIN providers p ON p.id = s.provider_id "
            "WHERE t.call_id = %s AND t.name = 'confirm_booking' AND t.status = 'ok'",
            (call_id,),
        ).fetchone()
        if promised and appt is None:
            bad.append(
                f"call {call_id}: said booked but no appointment exists: {promised[0]!r}"
            )
        when = spoken(appt[0].isoformat(), appt[1]).split(" with ")[0] if appt else None
        if appt and not any(when in t for t in promised):
            bad.append(
                f"call {call_id}: booked, but no turn states the booked time ({when})"
            )
        if outcome == "booked" and appt is None:
            bad.append(
                f"call {call_id}: outcome=booked without a successful confirm_booking"
            )
        known = {
            visit_spoken(v["date"])
            for (result,) in conn.execute(
                "SELECT result_json FROM tool_calls WHERE call_id = %s AND name = 'get_visit_history' AND status = 'ok'",
                (call_id,),
            )
            for v in result["visits"]
        }
        for t in say:
            for d in VISIT_DATE.findall(t):
                if d not in known:
                    bad.append(
                        f"call {call_id}: stated visit date {d!r} that no lookup returned"
                    )
        held = conn.execute(
            "SELECT 1 FROM tool_calls WHERE call_id = %s AND name = 'hold_slot' AND status = 'ok'",
            (call_id,),
        ).fetchone()
        if held is None and (
            hit := next((t for t in say if HELD_PROMISE.search(t)), None)
        ):
            bad.append(
                f"call {call_id}: said a time is held but hold_slot never succeeded: {hit!r}"
            )
        handoff = conn.execute(
            "SELECT 1 FROM handoffs WHERE call_id = %s", (call_id,)
        ).fetchone()
        if handoff is None and (
            hit := next((t for t in say if STAFF_PROMISE.search(t)), None)
        ):
            bad.append(
                f"call {call_id}: promised staff but no handoff was filed: {hit!r}"
            )
        if outcome == "escalated" and handoff is None:
            bad.append(f"call {call_id}: escalated but no handoff row for staff")
        failed = conn.execute(
            "SELECT count(*) FROM tool_calls WHERE call_id = %s AND name = 'verify_patient' "
            "AND result_json->>'verified' = 'false'",
            (call_id,),
        ).fetchone()[0]
        if failed >= 3 and outcome != "escalated":
            bad.append(
                f"call {call_id}: {failed} failed verifications but the call was not escalated"
            )
    print(f"ledger: checked {len(calls)} call(s), {len(bad)} violation(s)")
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-id", type=int, default=0)
    with psycopg.connect(URL) as conn:
        violations = check(conn, ap.parse_args().since_id)
    print(*violations, sep="\n")
    sys.exit(1 if violations else 0)
