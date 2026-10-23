"""Load synthetic data: 50 patients, 3 providers, 2 weeks of slots, past visits.

Run from backend/:  uv run python -m app.db.seed
Deterministic (fixed seed) and re-runnable: it wipes the tables first.
"""

import os
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg
from faker import Faker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://voice:voice@localhost:5433/voice_intake")
CLINIC_TZ = ZoneInfo("America/New_York")
N_PATIENTS = 50
PROVIDERS = [
    ("Dr. Maya Chen", "Family Medicine"),
    ("Dr. Omar Reyes", "Internal Medicine"),
    ("Dr. Priya Nair", "Pediatrics"),
]
VISIT_TYPES = ["checkup", "follow_up", "sick_visit"]
VISIT_REASONS = [
    "annual physical",
    "cough and congestion",
    "blood pressure follow-up",
    "back pain",
    "vaccination",
    "rash",
    "medication refill",
]
SLOT_MINUTES = 30
DAYS_AHEAD = 14

fake = Faker("en_US")
Faker.seed(42)
rng = random.Random(42)


def make_patients() -> list[tuple]:
    seen: set[tuple] = set()
    rows = []
    while len(rows) < N_PATIENTS:
        first, last = fake.first_name(), fake.last_name()
        dob = fake.date_of_birth(minimum_age=18, maximum_age=90)
        key = (first.lower(), last.lower(), dob)
        if key in seen:  # patients_identity_uq would reject it
            continue
        seen.add(key)
        rows.append((first, last, dob, fake.numerify("555-01##")))  # 555-01xx is reserved for fiction
    return rows


def make_slots(provider_ids: list[int]) -> list[tuple]:
    rows = []
    day = date.today() + timedelta(days=1)  # only future slots
    for offset in range(DAYS_AHEAD):
        d = day + timedelta(days=offset)
        if d.weekday() >= 5:  # skip weekends
            continue
        for pid in provider_ids:
            start = datetime.combine(d, time(9, 0), tzinfo=CLINIC_TZ)
            while start.hour < 17:
                end = start + timedelta(minutes=SLOT_MINUTES)
                rows.append((pid, start, end, rng.choice(VISIT_TYPES)))
                start = end
    return rows


def make_visits(patient_ids: list[int], provider_ids: list[int]) -> list[tuple]:
    rows = []
    for pat in patient_ids:
        for _ in range(rng.randint(0, 4)):
            when = date.today() - timedelta(days=rng.randint(7, 900))
            rows.append((pat, rng.choice(provider_ids), when, rng.choice(VISIT_REASONS), None))
    return rows


def main() -> None:
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE eval_results, eval_runs, handoffs, tool_calls, turns, appointments, "
            "holds, calls, visits, slots, providers, patients RESTART IDENTITY CASCADE"
        )
        cur.executemany(
            "INSERT INTO patients (first_name, last_name, dob, phone) VALUES (%s, %s, %s, %s)", make_patients()
        )
        cur.executemany("INSERT INTO providers (name, specialty) VALUES (%s, %s)", PROVIDERS)
        cur.execute("SELECT id FROM patients ORDER BY id")
        patient_ids = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT id FROM providers ORDER BY id")
        provider_ids = [r[0] for r in cur.fetchall()]
        cur.executemany(
            "INSERT INTO slots (provider_id, start_time, end_time, visit_type) VALUES (%s, %s, %s, %s)",
            make_slots(provider_ids),
        )
        cur.executemany(
            "INSERT INTO visits (patient_id, provider_id, visit_date, reason, notes_summary) VALUES (%s, %s, %s, %s, %s)",
            make_visits(patient_ids, provider_ids),
        )
        for table in ("patients", "providers", "slots", "visits"):
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"{table}: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
