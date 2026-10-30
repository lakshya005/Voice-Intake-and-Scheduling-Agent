import asyncio

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import DATABASE_URL, app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_call(client):
    ids = []

    def make():
        ids.append(client.post("/calls", json={"channel": "browser"}).json()["id"])
        return ids[-1]

    yield make
    with psycopg.connect(DATABASE_URL) as conn:  # appointments and holds don't cascade from calls
        for call_id in ids:
            conn.execute("DELETE FROM appointments WHERE idempotency_key LIKE %s", (f"test-{call_id}-%",))
            conn.execute("DELETE FROM holds WHERE call_id = %s", (call_id,))
            conn.execute("DELETE FROM handoffs WHERE call_id = %s", (call_id,))
            conn.execute("DELETE FROM calls WHERE id = %s", (call_id,))


@pytest.fixture
def patient():
    with psycopg.connect(DATABASE_URL) as conn:
        first, last, dob = conn.execute(
            "SELECT first_name, last_name, dob FROM patients ORDER BY id LIMIT 1"
        ).fetchone()
    return {"first_name": first, "last_name": last, "dob": dob.isoformat()}


def verified_call(client, make_call, patient):
    call_id = make_call()
    assert client.post("/tools/verify_patient", json={"call_id": call_id, **patient}).json()["verified"] is True
    return call_id


def first_slot(client, call_id):
    return client.post("/tools/find_slots", json={"call_id": call_id}).json()["slots"][0]["slot_id"]


def test_verify_lockout_after_three_wrong_attempts(client, make_call, patient):
    call_id = make_call()
    wrong = {**patient, "dob": "1900-01-01"}
    attempts = [client.post("/tools/verify_patient", json={"call_id": call_id, **wrong}).json() for _ in range(3)]
    assert [a["attempts_left"] for a in attempts] == [2, 1, 0]
    # even the right details no longer work: the call is locked out and must escalate
    assert client.post("/tools/verify_patient", json={"call_id": call_id, **patient}).json()["verified"] is False


def test_booking_requires_verification(client, make_call):
    call_id = make_call()
    slot_id = first_slot(client, call_id)
    assert client.post("/tools/hold_slot", json={"call_id": call_id, "slot_id": slot_id}).status_code == 403


def test_full_booking_and_idempotent_retry(client, make_call, patient):
    call_id = verified_call(client, make_call, patient)
    slot_id = first_slot(client, call_id)
    hold = client.post("/tools/hold_slot", json={"call_id": call_id, "slot_id": slot_id}).json()
    confirm = {
        "call_id": call_id,
        "hold_id": hold["hold_id"],
        "idempotency_key": f"test-{call_id}-a",
        "reason": "checkup",
    }
    first = client.post("/tools/confirm_booking", json=confirm)
    retry = client.post("/tools/confirm_booking", json=confirm)  # e.g. the tool call timed out and was repeated
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute("SELECT count(*) FROM appointments WHERE slot_id = %s", (slot_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT outcome FROM calls WHERE id = %s", (call_id,)).fetchone()[0] == "booked"
    # a booked slot no longer shows up
    assert slot_id not in [
        s["slot_id"] for s in client.post("/tools/find_slots", json={"call_id": call_id}).json()["slots"]
    ]


def test_second_caller_cannot_hold_a_held_slot(client, make_call, patient):
    a, b = verified_call(client, make_call, patient), verified_call(client, make_call, patient)
    slot_id = first_slot(client, a)
    assert client.post("/tools/hold_slot", json={"call_id": a, "slot_id": slot_id}).status_code == 200
    assert client.post("/tools/hold_slot", json={"call_id": b, "slot_id": slot_id}).status_code == 409


def test_expired_hold_frees_the_slot(client, make_call, patient):
    a, b = verified_call(client, make_call, patient), verified_call(client, make_call, patient)
    slot_id = first_slot(client, a)
    hold_id = client.post("/tools/hold_slot", json={"call_id": a, "slot_id": slot_id}).json()["hold_id"]
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("UPDATE holds SET expires_at = now() - interval '1 second' WHERE id = %s", (hold_id,))
        conn.commit()
    assert client.post("/tools/hold_slot", json={"call_id": b, "slot_id": slot_id}).status_code == 200
    stale = {"call_id": a, "hold_id": hold_id, "idempotency_key": f"test-{a}-x"}
    assert client.post("/tools/confirm_booking", json=stale).status_code == 409


def test_escalate_records_handoff(client, make_call):
    call_id = make_call()
    body = {"call_id": call_id, "reason": "red flag", "attempted": "safety screen", "why_escalated": "chest pain"}
    assert client.post("/tools/escalate", json=body).status_code == 200
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute("SELECT outcome FROM calls WHERE id = %s", (call_id,)).fetchone()[0] == "escalated"
        assert conn.execute("SELECT count(*) FROM tool_calls WHERE call_id = %s", (call_id,)).fetchone()[0] == 1


def test_five_callers_race_for_one_slot_exactly_one_wins(client, make_call, patient):
    calls = [verified_call(client, make_call, patient) for _ in range(5)]
    slot_id = first_slot(client, calls[0])

    async def race():
        # Real concurrency against the real pool; the TestClient would serialize the requests.
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c,
        ):
            rs = await asyncio.gather(
                *[c.post("/tools/hold_slot", json={"call_id": i, "slot_id": slot_id}) for i in calls]
            )
        return sorted(r.status_code for r in rs)

    assert asyncio.run(race()) == [200, 409, 409, 409, 409]
