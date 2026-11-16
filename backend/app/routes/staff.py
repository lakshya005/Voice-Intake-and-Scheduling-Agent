"""Dashboard API for logged-in staff. Transcripts are masked by default; unmasked text is admin-only and logged."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.db.conn import get_conn
from app.redact import redact
from app.staff_auth import (
    COOKIE,
    SESSION_HOURS,
    check_password_async,
    create_session,
    current_staff,
    end_session,
    log_access,
    require_admin,
)

router = APIRouter(prefix="/staff", tags=["staff"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginIn, response: Response, conn=Depends(get_conn)):
    cur = await conn.execute("SELECT id, password_hash, role FROM staff_users WHERE username = %s", (body.username,))
    row = await cur.fetchone()
    # a dummy hash keeps the response time the same whether or not the username exists
    stored = row[1] if row else "scrypt$00$00"
    ok = await check_password_async(body.password, stored)
    if row is None or not ok:
        raise HTTPException(401, "wrong username or password")
    token = await create_session(conn, row[0])
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_HOURS * 3600)
    return {"username": body.username, "role": row[2]}


@router.post("/logout")
async def logout(request: Request, response: Response, conn=Depends(get_conn)):
    await end_session(conn, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
async def me(staff=Depends(current_staff)):
    return {"username": staff["username"], "role": staff["role"]}


@router.get("/calls")
async def list_calls(limit: int = 50, staff=Depends(current_staff), conn=Depends(get_conn)):
    cur = await conn.execute(
        """
        SELECT c.id, c.started_at, c.ended_at, c.channel, c.outcome,
          (SELECT count(*) FROM turns t WHERE t.call_id = c.id AND t.text IS NOT NULL),
          (SELECT percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY extract(epoch FROM (t.t_tts_first_byte - t.t_user_stop)) * 1000)
             FROM turns t WHERE t.call_id = c.id AND t.t_tts_first_byte IS NOT NULL AND t.t_user_stop IS NOT NULL),
          (SELECT h.status FROM handoffs h WHERE h.call_id = c.id ORDER BY h.id DESC LIMIT 1)
        FROM calls c ORDER BY c.id DESC LIMIT %s
        """,
        (max(1, min(limit, 200)),),
    )
    return [
        {
            "id": r[0],
            "started_at": r[1].isoformat(),
            "ended_at": r[2].isoformat() if r[2] else None,
            "channel": r[3],
            "outcome": r[4],
            "turns": r[5],
            "p50_ms": round(r[6]) if r[6] is not None else None,
            "handoff_status": r[7],
        }
        for r in await cur.fetchall()
    ]


def _ms(a, b):
    return round((b - a).total_seconds() * 1000) if a and b else None


@router.get("/calls/{call_id}")
async def call_detail(call_id: int, reveal: bool = False, staff=Depends(current_staff), conn=Depends(get_conn)):
    if reveal and staff["role"] != "admin":
        raise HTTPException(403, "only an admin can see unmasked text")
    cur = await conn.execute(
        "SELECT c.id, c.started_at, c.ended_at, c.channel, c.outcome, c.verified_patient_id, "
        "p.first_name, p.last_name, p.dob, p.phone FROM calls c LEFT JOIN patients p ON p.id = c.verified_patient_id "
        "WHERE c.id = %s",
        (call_id,),
    )
    call = await cur.fetchone()
    if call is None:
        raise HTTPException(404, "call not found")
    patient = {"first_name": call[6], "last_name": call[7], "dob": call[8], "phone": call[9]} if call[5] else None

    cur = await conn.execute(
        "SELECT idx, role, text, interrupted, t_user_stop, t_stt_final, t_llm_first_token, t_tts_first_byte "
        "FROM turns WHERE call_id = %s ORDER BY idx",
        (call_id,),
    )
    turns = await cur.fetchall()
    cur = await conn.execute(
        "SELECT name, status, latency_ms, args_json, result_json FROM tool_calls WHERE call_id = %s ORDER BY id",
        (call_id,),
    )
    tools = await cur.fetchall()
    cur = await conn.execute(
        "SELECT a.id, s.start_time, pr.name, a.reason FROM tool_calls t "
        "JOIN appointments a ON a.id = (t.result_json->>'appointment_id')::bigint "
        "JOIN slots s ON s.id = a.slot_id JOIN providers pr ON pr.id = s.provider_id "
        "WHERE t.call_id = %s AND t.name = 'confirm_booking' AND t.status = 'ok'",
        (call_id,),
    )
    appt = await cur.fetchone()
    cur = await conn.execute(
        "SELECT id, reason, status, summary_json FROM handoffs WHERE call_id = %s ORDER BY id DESC LIMIT 1",
        (call_id,),
    )
    handoff = await cur.fetchone()

    await log_access(conn, staff["id"], "reveal_call" if reveal else "view_call", call_id)
    mask = (lambda t: t) if reveal else (lambda t: redact(t, patient))
    return {
        "id": call[0],
        "started_at": call[1].isoformat(),
        "ended_at": call[2].isoformat() if call[2] else None,
        "channel": call[3],
        "outcome": call[4],
        "verified": call[5] is not None,
        "masked": not reveal,
        "transcript": [{"idx": t[0], "role": t[1], "text": mask(t[2]), "interrupted": t[3]} for t in turns if t[2]],
        "latency": [
            {
                "idx": t[0],
                "stt_ms": _ms(t[4], t[5]),
                "llm_ms": _ms(t[5], t[6]),
                "tts_ms": _ms(t[6], t[7]),
                "total_ms": _ms(t[4], t[7]),
            }
            for t in turns
            if t[4] and t[7]
        ],
        "tool_calls": [{"name": t[0], "status": t[1], "latency_ms": t[2], "args": t[3], "result": t[4]} for t in tools],
        "appointment": {"id": appt[0], "start_time": appt[1].isoformat(), "provider": appt[2], "reason": appt[3]}
        if appt
        else None,
        "handoff": {"id": handoff[0], "reason": handoff[1], "status": handoff[2]} if handoff else None,
    }


@router.get("/handoffs")
async def list_handoffs(status: str | None = None, staff=Depends(current_staff), conn=Depends(get_conn)):
    cur = await conn.execute(
        "SELECT h.id, h.call_id, h.reason, h.status, h.created_at, u.username, h.summary_json "
        "FROM handoffs h LEFT JOIN staff_users u ON u.id = h.claimed_by "
        "WHERE (%s::text IS NULL OR h.status = %s) ORDER BY h.id DESC LIMIT 100",
        (status, status),
    )
    return [
        {
            "id": r[0],
            "call_id": r[1],
            "reason": r[2],
            "status": r[3],
            "created_at": r[4].isoformat(),
            "claimed_by": r[5],
            "verified": bool((r[6] or {}).get("verified")),
        }
        for r in await cur.fetchall()
    ]


@router.post("/handoffs/{handoff_id}/claim")
async def claim_handoff(handoff_id: int, staff=Depends(current_staff), conn=Depends(get_conn)):
    cur = await conn.execute(
        "UPDATE handoffs SET status = 'claimed', claimed_by = %s, claimed_at = now() "
        "WHERE id = %s AND status = 'open' RETURNING id",
        (staff["id"], handoff_id),
    )
    if await cur.fetchone() is None:
        raise HTTPException(409, "handoff is not open")
    await log_access(conn, staff["id"], "claim_handoff", None, {"handoff_id": handoff_id})
    return {"id": handoff_id, "status": "claimed"}


@router.post("/handoffs/{handoff_id}/close")
async def close_handoff(handoff_id: int, staff=Depends(current_staff), conn=Depends(get_conn)):
    cur = await conn.execute(
        "UPDATE handoffs SET status = 'closed', closed_at = now() "
        "WHERE id = %s AND status = 'claimed' AND (claimed_by = %s OR %s) RETURNING id",
        (handoff_id, staff["id"], staff["role"] == "admin"),
    )
    if await cur.fetchone() is None:
        raise HTTPException(409, "only the staff member who claimed an open handoff can close it")
    await log_access(conn, staff["id"], "close_handoff", None, {"handoff_id": handoff_id})
    return {"id": handoff_id, "status": "closed"}


@router.get("/handoffs/{handoff_id}/patient")
async def handoff_patient(handoff_id: int, staff=Depends(current_staff), conn=Depends(get_conn)):
    """The patient's details, for the staff member working the handoff. Only after claiming it, only if the
    agent verified the caller, always logged."""
    cur = await conn.execute(
        "SELECT h.claimed_by, h.call_id, p.id, p.first_name, p.last_name, p.dob, p.phone "
        "FROM handoffs h JOIN calls c ON c.id = h.call_id LEFT JOIN patients p ON p.id = c.verified_patient_id "
        "WHERE h.id = %s",
        (handoff_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, "handoff not found")
    if row[0] != staff["id"] and staff["role"] != "admin":
        raise HTTPException(403, "claim the handoff first")
    if row[2] is None:
        raise HTTPException(409, "caller was not verified: verify them yourself before opening any record")
    cur = await conn.execute(
        "SELECT v.visit_date, pr.name, v.reason FROM visits v JOIN providers pr ON pr.id = v.provider_id "
        "WHERE v.patient_id = %s ORDER BY v.visit_date DESC, v.id DESC LIMIT 3",
        (row[2],),
    )
    visits = [{"date": v[0].isoformat(), "provider": v[1], "reason": v[2]} for v in await cur.fetchall()]
    await log_access(conn, staff["id"], "view_patient", row[1], {"handoff_id": handoff_id})
    return {
        "first_name": row[3],
        "last_name": row[4],
        "dob": row[5].isoformat(),
        "phone": row[6],
        "recent_visits": visits,
    }


@router.get("/access-log")
async def access_log(limit: int = 100, staff=Depends(require_admin), conn=Depends(get_conn)):
    cur = await conn.execute(
        "SELECT a.id, a.at, u.username, a.action, a.call_id, a.detail FROM access_log a "
        "JOIN staff_users u ON u.id = a.staff_id ORDER BY a.id DESC LIMIT %s",
        (max(1, min(limit, 500)),),
    )
    return [
        {"id": r[0], "at": r[1].isoformat(), "staff": r[2], "action": r[3], "call_id": r[4], "detail": r[5]}
        for r in await cur.fetchall()
    ]
