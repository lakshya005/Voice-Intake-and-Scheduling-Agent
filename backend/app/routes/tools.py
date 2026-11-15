"""Agent tool endpoints. The LLM only calls these; every rule (verification gate, hold TTL, no double
booking) is enforced here, never in the prompt. Every call is audited in tool_calls."""

import time
from datetime import date
from datetime import time as clock

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.db.conn import get_conn

router = APIRouter(prefix="/tools", tags=["tools"])
MAX_VERIFY_ATTEMPTS = 3
HOLD_TTL = "2 minutes"


async def audited(conn, call_id, name, args, fn):
    """Run fn(verified_patient_id) and record the outcome in tool_calls. 404 if the call doesn't exist."""
    cur = await conn.execute("SELECT verified_patient_id FROM calls WHERE id = %s", (call_id,))
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, "call not found")
    started, status, result = time.monotonic(), "ok", None
    try:
        result = await fn(row[0])
    except HTTPException as e:
        result, status = {"error": e.detail}, "denied"
        raise
    except Exception:
        result, status = {"error": "internal"}, "error"
        raise
    finally:
        await conn.execute(
            "INSERT INTO tool_calls (call_id, name, args_json, result_json, latency_ms, status) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (call_id, name, Jsonb(args), Jsonb(result), int((time.monotonic() - started) * 1000), status),
        )
    return result


def require_verified(patient_id):
    if patient_id is None:
        raise HTTPException(403, "caller is not verified")
    return patient_id


class VerifyIn(BaseModel):
    call_id: int
    first_name: str
    last_name: str
    dob: date


@router.post("/verify_patient")
async def verify_patient(body: VerifyIn, conn=Depends(get_conn)):
    async def run(_):
        cur = await conn.execute(
            "SELECT count(*) FROM tool_calls WHERE call_id = %s AND name = 'verify_patient' "
            "AND result_json->>'verified' = 'false'",
            (body.call_id,),
        )
        failed = (await cur.fetchone())[0]
        if failed >= MAX_VERIFY_ATTEMPTS:
            return {"verified": False, "patient_id": None, "attempts_left": 0}
        cur = await conn.execute(
            "SELECT id FROM patients WHERE lower(first_name) = lower(%s) AND lower(last_name) = lower(%s) AND dob = %s",
            (body.first_name.strip(), body.last_name.strip(), body.dob),
        )
        row = await cur.fetchone()
        if row is None:
            return {"verified": False, "patient_id": None, "attempts_left": MAX_VERIFY_ATTEMPTS - failed - 1}
        await conn.execute("UPDATE calls SET verified_patient_id = %s WHERE id = %s", (row[0], body.call_id))
        return {"verified": True, "patient_id": row[0], "attempts_left": MAX_VERIFY_ATTEMPTS - failed}

    return await audited(conn, body.call_id, "verify_patient", {}, run)  # args empty: name and DOB are PII


class FindSlotsIn(BaseModel):
    call_id: int
    visit_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    time_from: clock | None = None  # clinic-local time of day, e.g. 12:00 for afternoons
    time_to: clock | None = None
    provider_id: int | None = None


@router.post("/find_slots")
async def find_slots(body: FindSlotsIn, conn=Depends(get_conn)):
    async def run(_):
        cur = await conn.execute(
            """
            SELECT s.id, p.name, s.visit_type, s.start_time
            FROM slots s JOIN providers p ON p.id = s.provider_id
            WHERE s.start_time > now()
              AND (%(vt)s::text IS NULL OR s.visit_type = %(vt)s)
              AND (%(pid)s::bigint IS NULL OR s.provider_id = %(pid)s)
              AND (%(df)s::date IS NULL OR s.start_time >= (%(df)s::date)::timestamp AT TIME ZONE 'America/New_York')
              AND (%(dt)s::date IS NULL
                   OR s.start_time < ((%(dt)s::date) + 1)::timestamp AT TIME ZONE 'America/New_York')
              AND (%(tf)s::time IS NULL OR (s.start_time AT TIME ZONE 'America/New_York')::time >= %(tf)s::time)
              AND (%(tt)s::time IS NULL OR (s.start_time AT TIME ZONE 'America/New_York')::time < %(tt)s::time)
              AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.id)
              AND NOT EXISTS (SELECT 1 FROM holds h
                              WHERE h.slot_id = s.id AND h.status = 'active' AND h.expires_at > now())
            ORDER BY s.start_time LIMIT 3
            """,
            {
                "vt": body.visit_type,
                "pid": body.provider_id,
                "df": body.date_from,
                "dt": body.date_to,
                "tf": body.time_from,
                "tt": body.time_to,
            },
        )
        return {
            "slots": [
                {"slot_id": r[0], "provider": r[1], "visit_type": r[2], "start_time": r[3].isoformat()}
                for r in await cur.fetchall()
            ]
        }

    return await audited(conn, body.call_id, "find_slots", body.model_dump(mode="json"), run)


class HoldIn(BaseModel):
    call_id: int
    slot_id: int


@router.post("/hold_slot")
async def hold_slot(body: HoldIn, conn=Depends(get_conn)):
    async def run(pid):
        require_verified(pid)  # the patient comes from the verified call, never from the LLM
        try:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE holds SET status = 'released' WHERE status = 'active' AND (call_id = %s OR "
                    "(slot_id = %s AND expires_at <= now()))",
                    (body.call_id, body.slot_id),
                )
                cur = await conn.execute(
                    "SELECT s.start_time > now() AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.id) "
                    "FROM slots s WHERE s.id = %s",
                    (body.slot_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    raise HTTPException(404, "slot not found")
                if not row[0]:
                    raise HTTPException(409, "slot is not available")
                cur = await conn.execute(
                    f"INSERT INTO holds (slot_id, patient_id, call_id, expires_at) "
                    f"VALUES (%s, %s, %s, now() + interval '{HOLD_TTL}') RETURNING id, expires_at",
                    (body.slot_id, pid, body.call_id),
                )
                hold_id, expires_at = await cur.fetchone()
        except UniqueViolation:  # partial unique index: someone else holds this slot
            raise HTTPException(409, "slot is not available") from None
        return {"hold_id": hold_id, "expires_at": expires_at.isoformat()}

    return await audited(conn, body.call_id, "hold_slot", body.model_dump(mode="json"), run)


class ReleaseIn(BaseModel):
    call_id: int
    hold_id: int


@router.post("/release_hold")
async def release_hold(body: ReleaseIn, conn=Depends(get_conn)):
    async def run(_):
        cur = await conn.execute(
            "UPDATE holds SET status = 'released' WHERE id = %s AND call_id = %s AND status = 'active' RETURNING id",
            (body.hold_id, body.call_id),
        )
        return {"released": await cur.fetchone() is not None}

    return await audited(conn, body.call_id, "release_hold", body.model_dump(mode="json"), run)


class ConfirmIn(BaseModel):
    call_id: int
    hold_id: int
    idempotency_key: str
    reason: str | None = None


@router.post("/confirm_booking")
async def confirm_booking(body: ConfirmIn, conn=Depends(get_conn)):
    async def run(pid):
        require_verified(pid)
        try:
            async with conn.transaction():
                cur = await conn.execute(
                    "SELECT id, slot_id, patient_id FROM appointments WHERE idempotency_key = %s",
                    (body.idempotency_key,),
                )
                existing = await cur.fetchone()
                if existing:  # a retry of the same request: return the original result, create nothing
                    if existing[2] != pid:
                        raise HTTPException(409, "idempotency key belongs to another patient")
                    appointment_id, slot_id = existing[0], existing[1]
                else:
                    cur = await conn.execute(
                        "SELECT slot_id, status = 'active' AND expires_at > now() FROM holds "
                        "WHERE id = %s AND call_id = %s FOR UPDATE",
                        (body.hold_id, body.call_id),
                    )
                    hold = await cur.fetchone()
                    if hold is None:
                        raise HTTPException(404, "hold not found")
                    if not hold[1]:
                        raise HTTPException(409, "hold expired or already used")
                    slot_id = hold[0]
                    cur = await conn.execute(
                        "INSERT INTO appointments (slot_id, patient_id, reason, idempotency_key) "
                        "VALUES (%s, %s, %s, %s) RETURNING id",
                        (slot_id, pid, body.reason, body.idempotency_key),
                    )
                    appointment_id = (await cur.fetchone())[0]
                    await conn.execute("UPDATE holds SET status = 'converted' WHERE id = %s", (body.hold_id,))
                    await conn.execute("UPDATE calls SET outcome = 'booked' WHERE id = %s", (body.call_id,))
                cur = await conn.execute(
                    "SELECT p.name, s.start_time FROM slots s JOIN providers p ON p.id = s.provider_id WHERE s.id = %s",
                    (slot_id,),
                )
                provider, start = await cur.fetchone()
        except UniqueViolation:  # shouldn't happen under the hold lock; the constraint is the last defense
            raise HTTPException(409, "slot already booked") from None
        return {"appointment_id": appointment_id, "provider": provider, "start_time": start.isoformat()}

    return await audited(conn, body.call_id, "confirm_booking", body.model_dump(mode="json"), run)


class EscalateIn(BaseModel):
    call_id: int
    reason: str
    attempted: str
    why_escalated: str
    who: str | None = None


@router.post("/escalate")
async def escalate(body: EscalateIn, conn=Depends(get_conn)):
    async def run(pid):
        summary = {
            "who": body.who,
            "verified": pid is not None,
            "reason": body.reason,
            "attempted": body.attempted,
            "why_escalated": body.why_escalated,
        }
        async with conn.transaction():
            cur = await conn.execute(
                "INSERT INTO handoffs (call_id, reason, summary_json) VALUES (%s, %s, %s) RETURNING id",
                (body.call_id, body.reason, Jsonb(summary)),
            )
            await conn.execute("UPDATE calls SET outcome = 'escalated' WHERE id = %s", (body.call_id,))
        return {"handoff_id": (await cur.fetchone())[0]}

    return await audited(conn, body.call_id, "escalate", {"reason": body.reason}, run)


class VisitsIn(BaseModel):
    call_id: int
    limit: int = Field(default=1, ge=1, le=5)


@router.post("/get_visit_history")
async def get_visit_history(body: VisitsIn, conn=Depends(get_conn)):
    """Past visits of the verified caller, newest first. Allowlist: date, provider, reason. No notes."""

    async def run(pid):
        require_verified(pid)
        cur = await conn.execute(
            "SELECT v.visit_date, p.name, v.reason FROM visits v JOIN providers p ON p.id = v.provider_id "
            "WHERE v.patient_id = %s ORDER BY v.visit_date DESC, v.id DESC LIMIT %s",
            (pid, body.limit),
        )
        return {"visits": [{"date": r[0].isoformat(), "provider": r[1], "reason": r[2]} for r in await cur.fetchall()]}

    return await audited(conn, body.call_id, "get_visit_history", body.model_dump(mode="json"), run)
