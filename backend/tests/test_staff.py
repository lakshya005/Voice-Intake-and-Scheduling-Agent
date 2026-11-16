import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import DATABASE_URL, app
from app.staff_auth import hash_password

USERS = {"t_admin": ("pw-admin", "admin"), "t_agent": ("pw-agent", "agent"), "t_agent2": ("pw-agent2", "agent")}


@pytest.fixture
def staff_users():
    with psycopg.connect(DATABASE_URL) as conn:
        for name, (pw, role) in USERS.items():
            conn.execute(
                "INSERT INTO staff_users (username, password_hash, role) VALUES (%s, %s, %s) "
                "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash",
                (name, hash_password(pw), role),
            )
    yield
    with psycopg.connect(DATABASE_URL) as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM staff_users WHERE username = ANY(%s)", (list(USERS),))]
        conn.execute("DELETE FROM access_log WHERE staff_id = ANY(%s)", (ids,))
        conn.execute("UPDATE handoffs SET claimed_by = NULL WHERE claimed_by = ANY(%s)", (ids,))
        conn.execute("DELETE FROM staff_users WHERE id = ANY(%s)", (ids,))


def login(name: str) -> TestClient:
    c = TestClient(app)
    c.__enter__()
    assert c.post("/staff/login", json={"username": name, "password": USERS[name][0]}).status_code == 200
    return c


@pytest.fixture
def call_with_handoff():
    """A verified call that was escalated, with a transcript that names the patient."""
    with psycopg.connect(DATABASE_URL) as conn:
        first, last, dob = conn.execute(
            "SELECT first_name, last_name, dob FROM patients ORDER BY id LIMIT 1"
        ).fetchone()
        pid = conn.execute("SELECT id FROM patients ORDER BY id LIMIT 1").fetchone()[0]
        call_id = conn.execute(
            "INSERT INTO calls (verified_patient_id, outcome) VALUES (%s, 'escalated') RETURNING id", (pid,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO turns (call_id, idx, role, text) VALUES (%s, 0, 'user', %s)",
            (call_id, f"My name is {first} {last}, born {dob:%B} {dob.day}, {dob.year}."),
        )
        handoff_id = conn.execute(
            "INSERT INTO handoffs (call_id, reason, summary_json) VALUES (%s, 'test', %s) RETURNING id",
            (call_id, '{"verified": true}'),
        ).fetchone()[0]
    yield call_id, handoff_id, first, last
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DELETE FROM handoffs WHERE call_id = %s", (call_id,))
        conn.execute("DELETE FROM access_log WHERE call_id = %s", (call_id,))
        conn.execute("DELETE FROM calls WHERE id = %s", (call_id,))  # turns cascade


def test_dashboard_requires_login(staff_users):
    with TestClient(app) as c:
        assert c.get("/staff/calls").status_code == 401
        bad = c.post("/staff/login", json={"username": "t_admin", "password": "wrong"})
        assert bad.status_code == 401
        assert c.post("/staff/login", json={"username": "nobody", "password": "x"}).status_code == 401


def test_logout_ends_the_session(staff_users):
    c = login("t_agent")
    assert c.get("/staff/me").json() == {"username": "t_agent", "role": "agent"}
    c.post("/staff/logout")
    assert c.get("/staff/me").status_code == 401


def test_transcript_is_masked_and_only_an_admin_can_reveal_it(staff_users, call_with_handoff):
    call_id, _, first, last = call_with_handoff
    agent, admin = login("t_agent"), login("t_admin")
    text = agent.get(f"/staff/calls/{call_id}").json()["transcript"][0]["text"]
    assert first not in text and last not in text and "[NAME]" in text
    assert agent.get(f"/staff/calls/{call_id}?reveal=true").status_code == 403
    assert first in admin.get(f"/staff/calls/{call_id}?reveal=true").json()["transcript"][0]["text"]
    log = admin.get("/staff/access-log").json()
    actions = {(e["staff"], e["action"]) for e in log if e["call_id"] == call_id}
    assert {("t_agent", "view_call"), ("t_admin", "reveal_call")} <= actions
    assert agent.get("/staff/access-log").status_code == 403


def test_patient_details_only_after_claiming_and_only_for_the_claimer(staff_users, call_with_handoff):
    _, handoff_id, first, _ = call_with_handoff
    a, b = login("t_agent"), login("t_agent2")
    assert a.get(f"/staff/handoffs/{handoff_id}/patient").status_code == 403  # not claimed yet
    assert a.post(f"/staff/handoffs/{handoff_id}/claim").status_code == 200
    assert b.post(f"/staff/handoffs/{handoff_id}/claim").status_code == 409  # already taken
    assert b.get(f"/staff/handoffs/{handoff_id}/patient").status_code == 403
    assert a.get(f"/staff/handoffs/{handoff_id}/patient").json()["first_name"] == first
    assert b.post(f"/staff/handoffs/{handoff_id}/close").status_code == 409
    assert a.post(f"/staff/handoffs/{handoff_id}/close").status_code == 200
    admin = login("t_admin")
    assert ("t_agent", "view_patient") in {(e["staff"], e["action"]) for e in admin.get("/staff/access-log").json()}


def test_unverified_call_never_exposes_a_patient(staff_users, call_with_handoff):
    call_id, handoff_id, *_ = call_with_handoff
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("UPDATE calls SET verified_patient_id = NULL WHERE id = %s", (call_id,))
    a = login("t_agent")
    a.post(f"/staff/handoffs/{handoff_id}/claim")
    assert a.get(f"/staff/handoffs/{handoff_id}/patient").status_code == 409
