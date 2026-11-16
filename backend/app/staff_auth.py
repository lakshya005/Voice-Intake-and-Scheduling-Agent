"""Staff login for the dashboard: scrypt password hashes, server-side sessions, and the access log."""

import asyncio
import hashlib
import hmac
import os
import secrets

from fastapi import Depends, HTTPException, Request
from psycopg.types.json import Jsonb

from app.db.conn import get_conn

COOKIE = "staff_session"
SESSION_HOURS = 8


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    except ValueError:
        return False
    return hmac.compare_digest(got, bytes.fromhex(digest))


async def check_password_async(password: str, stored: str) -> bool:
    return await asyncio.to_thread(check_password, password, stored)  # scrypt is deliberately slow


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(conn, staff_id: int) -> str:
    token = secrets.token_urlsafe(32)
    await conn.execute(
        "INSERT INTO staff_sessions (token_hash, staff_id, expires_at) VALUES (%s, %s, now() + %s * interval '1 hour')",
        (_token_hash(token), staff_id, SESSION_HOURS),
    )
    return token


async def end_session(conn, token: str | None):
    if token:
        await conn.execute("DELETE FROM staff_sessions WHERE token_hash = %s", (_token_hash(token),))


async def current_staff(request: Request, conn=Depends(get_conn)) -> dict:
    token = request.cookies.get(COOKIE)
    row = None
    if token:
        cur = await conn.execute(
            "SELECT u.id, u.username, u.role FROM staff_sessions s JOIN staff_users u ON u.id = s.staff_id "
            "WHERE s.token_hash = %s AND s.expires_at > now()",
            (_token_hash(token),),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(401, "not logged in")
    return {"id": row[0], "username": row[1], "role": row[2]}


def require_admin(staff: dict = Depends(current_staff)) -> dict:
    if staff["role"] != "admin":
        raise HTTPException(403, "admin only")
    return staff


async def log_access(conn, staff_id: int, action: str, call_id: int | None = None, detail: dict | None = None):
    await conn.execute(
        "INSERT INTO access_log (staff_id, action, call_id, detail) VALUES (%s, %s, %s, %s)",
        (staff_id, action, call_id, Jsonb(detail) if detail else None),
    )
