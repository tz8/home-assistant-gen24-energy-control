"""GEN24 inverter HTTP API client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession


@dataclass(frozen=True, slots=True)
class TimeOfUseEntry:
    """Fronius time-of-use entry."""

    schedule_type: str
    power_w: int
    active: bool = True

    def as_payload(self) -> dict[str, Any]:
        return {
            "Active": self.active,
            "Power": self.power_w,
            "ScheduleType": self.schedule_type,
            "TimeTable": {"Start": "00:00", "End": "23:59"},
            "Weekdays": {
                "Mon": True,
                "Tue": True,
                "Wed": True,
                "Thu": True,
                "Fri": True,
                "Sat": True,
                "Sun": True,
            },
        }


class Gen24Client:
    """Small async client for the Fronius GEN24 local API."""

    def __init__(self, hass, base_url: str) -> None:
        self._hass = hass
        self._base_url = base_url.rstrip("/")

    async def async_get_timeofuse(self) -> list[dict[str, Any]]:
        session = async_get_clientsession(self._hass)
        async with session.get(f"{self._base_url}/config/timeofuse") as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
        return list(data.get("timeofuse", []))

    async def async_set_timeofuse(self, entries: list[TimeOfUseEntry]) -> None:
        session = async_get_clientsession(self._hass)
        payload = {"timeofuse": [entry.as_payload() for entry in entries]}
        async with session.post(
            f"{self._base_url}/config/timeofuse",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        ) as response:
            response.raise_for_status()

    async def async_get_batteries(self) -> dict[str, Any]:
        session = async_get_clientsession(self._hass)
        async with session.get(f"{self._base_url}/config/batteries") as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
        return dict(data)

    async def async_set_battery_config(self, values: dict[str, Any]) -> None:
        session = async_get_clientsession(self._hass)
        async with session.post(
            f"{self._base_url}/config/batteries",
            data=json.dumps(values),
            headers={"Content-Type": "application/json"},
        ) as response:
            response.raise_for_status()
