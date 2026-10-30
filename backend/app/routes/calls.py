from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import ForeignKeyViolation
from pydantic import BaseModel

from app.db.conn import get_conn

router = APIRouter(prefix="/calls", tags=["calls"])


class CallCreate(BaseModel):
    channel: Literal["browser", "phone"] = "browser"


class CallEnd(BaseModel):
    outcome: Literal["booked", "escalated", "abandoned", "failed"] | None = None


class TurnCreate(BaseModel):
    idx: int
    role: Literal["user", "assistant"]
    text: str | None = None
    t_user_stop: datetime | None = None
    t_stt_final: datetime | None = None
    t_llm_first_token: datetime | None = None
    t_tts_first_byte: datetime | None = None
    interrupted: bool = False


@router.post("", status_code=201)
async def create_call(body: CallCreate, conn=Depends(get_conn)):
    cur = await conn.execute("INSERT INTO calls (channel) VALUES (%s) RETURNING id", (body.channel,))
    return {"id": (await cur.fetchone())[0]}


@router.patch("/{call_id}")
async def end_call(call_id: int, body: CallEnd, conn=Depends(get_conn)):
    cur = await conn.execute(
        "UPDATE calls SET ended_at = now(), outcome = COALESCE(%s, outcome) WHERE id = %s RETURNING id", (body.outcome, call_id)
    )
    if await cur.fetchone() is None:
        raise HTTPException(404, "call not found")
    return {"id": call_id}


@router.post("/{call_id}/turns", status_code=201)
async def add_turn(call_id: int, body: TurnCreate, conn=Depends(get_conn)):
    try:
        cur = await conn.execute(
            "INSERT INTO turns (call_id, idx, role, text, t_user_stop, t_stt_final, t_llm_first_token, "
            "t_tts_first_byte, interrupted) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (call_id, idx) DO NOTHING RETURNING id",
            (
                call_id,
                body.idx,
                body.role,
                body.text,
                body.t_user_stop,
                body.t_stt_final,
                body.t_llm_first_token,
                body.t_tts_first_byte,
                body.interrupted,
            ),
        )
    except ForeignKeyViolation:
        raise HTTPException(404, "call not found") from None
    row = await cur.fetchone()  # None means a retry of an already stored turn: idempotent, not an error
    return {"id": row[0] if row else None}
