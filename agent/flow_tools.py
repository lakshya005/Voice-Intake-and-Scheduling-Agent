"""Handlers behind flow.yaml. Each tool calls the backend, which enforces the rules; the tool only reshapes the
result for the LLM and sets a "status" the YAML branches on."""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger
from pipecat.flows import TRANSITION_IN_YAML, FlowManager

UNSENT_HANDOFFS = Path(__file__).with_name("unsent_handoffs.jsonl")
CLINIC_TZ = ZoneInfo("America/New_York")
VISIT_TYPES = {"checkup", "follow_up", "sick_visit"}
# shortcut: substring match on the stated reason only, not on the whole call; add a transcript-level screen in M3
RED_FLAGS = (
    "chest pain", "chest pressure", "heart attack", "can't breathe", "cannot breathe", "trouble breathing",
    "difficulty breathing", "short of breath", "shortness of breath", "stroke", "face droop", "slurred speech",
    "suicid", "kill myself", "end my life", "overdose", "unconscious", "passed out", "seizure", "choking",
    "severe bleeding", "bleeding heavily", "anaphyla",
)  # fmt: skip


def spoken(start_iso: str, provider: str) -> str:
    dt = datetime.fromisoformat(start_iso).astimezone(CLINIC_TZ)
    return f"{dt:%A %B} {dt.day} at {dt.strftime('%-I:%M %p')} with {provider}"


def red_flag(text: str) -> str | None:
    text = text.lower().replace("’", "'")
    return next((flag for flag in RED_FLAGS if flag in text), None)


def _append(path: Path, line: str):
    with open(path, "a") as f:
        f.write(line)


def _call(fm: FlowManager):
    return fm.state["backend"], fm.state["call_id"]


def _escalate_state(fm: FlowManager, reason: str, attempted: str):
    fm.state["handoff_reason"], fm.state["handoff_attempted"] = reason, attempted


async def verify_patient(
    flow_manager: FlowManager, first_name: str, last_name: str, date_of_birth: str
):
    """Look up the caller by name and date of birth.

    Args:
        first_name (str): The caller's first name.
        last_name (str): The caller's last name.
        date_of_birth (str): The caller's date of birth as YYYY-MM-DD.
    """
    backend, call_id = _call(flow_manager)
    r = await backend.tool(
        "verify_patient",
        call_id=call_id,
        first_name=first_name,
        last_name=last_name,
        dob=date_of_birth,
    )
    if r.get("http_status") == 422:
        return {
            "status": "retry",
            "message": "That date was not understood. Ask for the date of birth again.",
        }, TRANSITION_IN_YAML
    if "error" in r:
        _escalate_state(
            flow_manager, "scheduling system unavailable", "identity verification"
        )
        return {"status": "escalate"}, TRANSITION_IN_YAML
    if r["verified"]:
        flow_manager.state["patient_first"] = first_name.strip().title()
        return {
            "status": "verified",
            "first_name": flow_manager.state["patient_first"],
        }, TRANSITION_IN_YAML
    if r["attempts_left"] == 0:
        _escalate_state(
            flow_manager,
            "identity not verified after 3 attempts",
            "identity verification",
        )
        return {"status": "escalate"}, TRANSITION_IN_YAML
    return {
        "status": "retry",
        "message": "The details did not match. Ask the caller to repeat first name, last name and date of birth.",
    }, TRANSITION_IN_YAML


async def record_reason(flow_manager: FlowManager, reason: str, visit_type: str):
    """Record why the caller wants to be seen.

    Args:
        reason (str): The caller's reason for the visit, in their own words.
        visit_type (str): The closest of: checkup, follow_up, sick_visit.
    """
    if not reason.strip():  # the model chained this call before the caller answered
        return {
            "status": "retry",
            "message": "The caller has not said why they are calling. Ask them.",
        }, TRANSITION_IN_YAML
    if flag := red_flag(reason):
        _escalate_state(
            flow_manager, f"red flag in stated reason: {flag}", "safety screen"
        )
        return {"status": "red_flag"}, TRANSITION_IN_YAML
    flow_manager.state["reason"] = reason
    flow_manager.state["visit_type"] = visit_type if visit_type in VISIT_TYPES else None
    return {"status": "ok"}, TRANSITION_IN_YAML


async def find_slots(
    flow_manager: FlowManager,
    date_from: str | None = None,
    date_to: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
):
    """Find up to three open appointment times.

    Args:
        date_from (str | None): Earliest date to consider, YYYY-MM-DD.
        date_to (str | None): Latest date to consider, YYYY-MM-DD.
        time_from (str | None): Earliest start time, 24-hour HH:MM. Afternoon starts at 12:00.
        time_to (str | None): Start must be before this time, 24-hour HH:MM. Morning ends at 12:00.
    """
    backend, call_id = _call(flow_manager)
    r = await backend.tool(
        "find_slots", call_id=call_id, visit_type=flow_manager.state.get("visit_type"),
        date_from=date_from, date_to=date_to, time_from=time_from, time_to=time_to,
    )  # fmt: skip
    if "error" in r:
        _escalate_state(flow_manager, "scheduling system unavailable", "slot search")
        return {"status": "escalate"}, TRANSITION_IN_YAML
    offered = {s["slot_id"]: spoken(s["start_time"], s["provider"]) for s in r["slots"]}
    flow_manager.state["offered"] = offered
    return {
        "status": "ok",
        "slots": [{"slot_id": i, "spoken": t} for i, t in offered.items()],
    }, TRANSITION_IN_YAML


async def hold_slot(flow_manager: FlowManager, slot_id: int):
    """Hold one of the offered times for two minutes while the caller confirms.

    Args:
        slot_id (int): The slot_id of an opening returned by find_slots.
    """
    offered = flow_manager.state.get("offered", {})
    if (
        slot_id not in offered
    ):  # the LLM may only pick what the backend actually returned
        return {
            "status": "unknown_slot",
            "message": "Only offer times returned by find_slots.",
        }, TRANSITION_IN_YAML
    backend, call_id = _call(flow_manager)
    r = await backend.tool("hold_slot", call_id=call_id, slot_id=slot_id)
    if (
        r.get("error") == "unavailable"
    ):  # an outage, not a taken slot: don't tell the caller it was taken
        _escalate_state(flow_manager, "scheduling system unavailable", "slot hold")
        return {"status": "escalate"}, TRANSITION_IN_YAML
    if "error" in r:
        return {
            "status": "taken",
            "message": "That time was just taken. Search again and offer another.",
        }, TRANSITION_IN_YAML
    flow_manager.state.update(
        hold_id=r["hold_id"],
        held_spoken=offered[slot_id],
        idempotency_key=str(uuid.uuid4()),
    )
    return {"status": "held"}, TRANSITION_IN_YAML


async def decline_slot(flow_manager: FlowManager):
    """Release the held time because the caller does not want it."""
    backend, call_id = _call(flow_manager)
    await backend.tool(
        "release_hold", call_id=call_id, hold_id=flow_manager.state["hold_id"]
    )
    return {"status": "released"}, TRANSITION_IN_YAML


async def confirm_booking(flow_manager: FlowManager):
    """Book the held time. Call only after the caller clearly said yes to the read-back."""
    backend, call_id = _call(flow_manager)
    s = flow_manager.state
    r = await backend.tool(
        "confirm_booking", call_id=call_id, hold_id=s["hold_id"], idempotency_key=s["idempotency_key"],
        reason=s.get("reason"),
    )  # fmt: skip
    if r.get("error") == "unavailable":
        _escalate_state(
            flow_manager,
            "booking system unavailable",
            "slot held, booking not confirmed",
        )
        return {"status": "escalate"}, TRANSITION_IN_YAML
    if "error" in r:
        return {
            "status": "failed",
            "message": "That time is no longer available. Apologize and offer another.",
        }, TRANSITION_IN_YAML
    s["booked_spoken"] = spoken(r["start_time"], r["provider"])
    return {"status": "booked"}, TRANSITION_IN_YAML


async def escalate_to_staff(flow_manager: FlowManager, reason: str):
    """Hand the call to human staff. Use when the caller asks for a person or you cannot help.

    Args:
        reason (str): Short reason for the handoff.
    """
    _escalate_state(flow_manager, reason, flow_manager.current_node or "unknown")
    return {"status": "ok"}, TRANSITION_IN_YAML


async def file_handoff(action: dict, flow_manager: FlowManager):
    """Action: record the handoff for staff, then the node ends the call."""
    backend, call_id = _call(flow_manager)
    s = flow_manager.state
    reason = s.get("handoff_reason", "caller asked for staff")
    r = await backend.tool(
        "escalate", call_id=call_id, reason=reason, attempted=s.get("handoff_attempted", "n/a"),
        why_escalated=reason, who=s.get("patient_first"),
    )  # fmt: skip
    if "error" in r:
        logger.error(f"handoff could not be filed for call {call_id}: {r}")
        # shortcut: a local file staff must read by hand; replace with a retry queue in M4
        line = (
            json.dumps(
                {"call_id": call_id, "reason": reason, "who": s.get("patient_first")}
            )
            + "\n"
        )
        await asyncio.to_thread(_append, UNSENT_HANDOFFS, line)
