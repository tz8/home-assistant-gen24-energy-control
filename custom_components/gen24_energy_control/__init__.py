"""GEN24 Energy Control custom integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .const import CONF_INVERTER_URL, CONF_WRITE_ENABLED, DEFAULT_WRITE_ENABLED, DOMAIN
from .gen24_payload import build_timeofuse_payload

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

try:  # pragma: no cover - exercised by Home Assistant runtime
    from homeassistant.const import Platform

    PLATFORMS = [Platform.SENSOR]
except ModuleNotFoundError:  # Allows pure unit tests without Home Assistant installed.
    PLATFORMS = ["sensor"]
SERVICE_APPLY_POLICY = "apply_policy"


async def async_setup_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    """Set up GEN24 Energy Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"entry": entry, "config": dict(entry.data) | dict(entry.options)}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


def _async_register_services(hass: "HomeAssistant") -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_APPLY_POLICY):
        return

    async def _apply_policy(call: "ServiceCall") -> None:
        entry_id = call.data.get("entry_id")
        entries = hass.data.get(DOMAIN, {})
        candidates = [entries[entry_id]] if entry_id else list(entries.values())
        for runtime in candidates:
            entry = runtime.get("entry")
            config = (dict(entry.data) | dict(entry.options)) if entry is not None else runtime.get("config", {})
            if not config.get(CONF_WRITE_ENABLED, DEFAULT_WRITE_ENABLED):
                continue
            coordinator = runtime.get("coordinator")
            if coordinator is None or not coordinator.data:
                continue
            decision = coordinator.data["decision"]
            if not decision.write_allowed:
                continue
            payload = build_timeofuse_payload(decision)
            if not payload["timeofuse"]:
                continue
            await _post_timeofuse(hass, config[CONF_INVERTER_URL], payload)

    hass.services.async_register(DOMAIN, SERVICE_APPLY_POLICY, _apply_policy)


async def _post_timeofuse(hass: "HomeAssistant", inverter_url: str, payload: dict[str, Any]) -> None:
    """Post a complete time-of-use payload to the GEN24 inverter."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    async with session.post(
        f"{inverter_url.rstrip('/')}/config/timeofuse",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    ) as response:
        response.raise_for_status()
