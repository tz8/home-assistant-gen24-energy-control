"""Diagnostics support for GEN24 Energy Control."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics without secrets."""
    config = dict(entry.data) | dict(entry.options)
    return {
        "domain": DOMAIN,
        "config": {key: value for key, value in config.items() if "token" not in key.lower()},
    }
