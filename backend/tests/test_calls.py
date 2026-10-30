from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import DATABASE_URL, app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def stored_turns(call_id):
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            "SELECT idx, role, interrupted, t_user_stop IS NOT NULL FROM turns WHERE call_id = %s", (call_id,)
        ).fetchall()


def test_call_lifecycle_and_turn_storage(client):
    call_id = client.post("/calls", json={"channel": "browser"}).json()["id"]
    turn = {
        "idx": 0,
        "role": "assistant",
        "interrupted": False,
        "t_user_stop": datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC).isoformat(),
    }
    assert client.post(f"/calls/{call_id}/turns", json=turn).status_code == 201
    assert client.post(f"/calls/{call_id}/turns", json=turn).status_code == 201  # retry: no duplicate
    assert stored_turns(call_id) == [(0, "assistant", False, True)]
    assert client.patch(f"/calls/{call_id}", json={"outcome": "abandoned"}).status_code == 200
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute("SELECT outcome, ended_at IS NOT NULL FROM calls WHERE id = %s", (call_id,)).fetchone() == (
            "abandoned",
            True,
        )
        conn.execute("DELETE FROM calls WHERE id = %s", (call_id,))  # cascades to turns
        conn.commit()


def test_unknown_call_returns_404(client):
    assert client.post("/calls/999999/turns", json={"idx": 0, "role": "assistant"}).status_code == 404
    assert client.patch("/calls/999999", json={}).status_code == 404
