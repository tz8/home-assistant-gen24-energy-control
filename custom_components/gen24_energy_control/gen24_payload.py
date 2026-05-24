"""Payload builders for Fronius GEN24 API writes."""

from __future__ import annotations

from typing import Any

from .planner import BatteryPolicyDecision

_WEEKDAYS = {"Mon": True, "Tue": True, "Wed": True, "Thu": True, "Fri": True, "Sat": True, "Sun": True}
_TIME_TABLE = {"Start": "00:00", "End": "23:59"}


def _entry(schedule_type: str, power_w: int) -> dict[str, Any]:
    return {
        "Active": True,
        "Power": power_w,
        "ScheduleType": schedule_type,
        "TimeTable": dict(_TIME_TABLE),
        "Weekdays": dict(_WEEKDAYS),
    }


def build_timeofuse_payload(decision: BatteryPolicyDecision) -> dict[str, list[dict[str, Any]]]:
    """Build a complete ``/config/timeofuse`` payload.

    The GEN24 endpoint expects the full desired set of entries. We deliberately
    return an empty list for non-writable decisions so safe fallback never causes
    accidental writes of stale strategy values.
    """
    if not decision.write_allowed:
        return {"timeofuse": []}

    entries: list[dict[str, Any]] = []
    if decision.charge_limit_w is not None:
        entries.append(_entry("CHARGE_MAX", int(decision.charge_limit_w)))
    if decision.discharge_limit_w is not None:
        entries.append(_entry("DISCHARGE_MAX", int(decision.discharge_limit_w)))
    return {"timeofuse": entries}
