"""Small HTTP client for the backend. A backend failure must never break a live call: log and carry on."""

import os

import httpx
from loguru import logger


class BackendClient:
    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url=os.getenv("BACKEND_URL", "http://localhost:8000"), timeout=3
        )

    async def start_call(self, channel: str = "browser") -> int | None:
        try:
            r = await self._http.post("/calls", json={"channel": channel})
            r.raise_for_status()
            return r.json()["id"]
        except httpx.HTTPError as e:
            logger.warning(
                f"backend start_call failed, timings will not be stored: {e}"
            )
            return None

    async def end_call(self, call_id: int | None, outcome: str | None = None):
        if call_id is None:
            return
        try:
            (
                await self._http.patch(f"/calls/{call_id}", json={"outcome": outcome})
            ).raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"backend end_call failed: {e}")

    async def tool(self, name: str, **payload) -> dict:
        """Call a backend tool. Retries once on a timeout or 5xx; never raises.

        A rejection comes back as {"error": detail, "http_status": code}, an outage as {"error": "unavailable"}.
        """
        for _ in range(2):
            try:
                r = await self._http.post(f"/tools/{name}", json=payload)
            except httpx.TransportError as e:
                logger.warning(f"tool {name} transport error: {e!r}")
                continue
            if r.status_code >= 500:
                logger.warning(f"tool {name} returned {r.status_code}")
                continue
            if r.is_success:
                return r.json()
            return {
                "error": r.json().get("detail", "rejected"),
                "http_status": r.status_code,
            }
        return {"error": "unavailable"}

    async def add_turn(self, call_id: int | None, payload: dict):
        if call_id is None:
            return
        try:
            (
                await self._http.post(f"/calls/{call_id}/turns", json=payload)
            ).raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"backend add_turn failed: {e}")
