"""Sensors for GEN24 Energy Control."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_EFFECTIVE_WRITE_ALLOWED,
    ATTR_MODE,
    ATTR_POLICY_WRITABLE,
    ATTR_PRICE_SOURCE_VALID,
    ATTR_REASON,
    ATTR_SOLAR_FORECAST_VALID,
    ATTR_WRITE_ENABLED,
    CONF_BATTERY_SOC_SENSOR,
    CONF_HOUSE_LOAD_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_SOLAR_FORECAST_SENSORS,
    CONF_WRITE_ENABLED,
    DEFAULT_DISCHARGE_LIMIT_W,
    DEFAULT_EXPORT_LIMIT_W,
    DEFAULT_MIN_SOC_PERCENT,
    DEFAULT_WRITE_ENABLED,
    DOMAIN,
)
from .planner import PlannerInputs, plan_battery_policy
from .price_slots import parse_price_slots

SCAN_INTERVAL = timedelta(minutes=5)
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up sensors."""
    coordinator = Gen24EnergyCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})["coordinator"] = coordinator
    await coordinator.async_config_entry_first_refresh()
    async_add_entities(
        [
            Gen24PolicySensor(coordinator, entry),
            Gen24DischargeLimitSensor(coordinator, entry),
        ],
        True,
    )


def _device_info(entry: ConfigEntry) -> dict[str, Any]:
    """Return the shared device info for all entities of this config entry."""
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "manufacturer": "Fronius",
        "model": "GEN24 Plus",
        "name": entry.title or "GEN24 Energy Control",
    }


class Gen24EnergyCoordinator(DataUpdateCoordinator):
    """Collect HA state and derive the current policy."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        config = dict(self.entry.data) | dict(self.entry.options)
        price_state = self.hass.states.get(config.get(CONF_PRICE_SENSOR))
        price_slots = parse_price_slots(price_state.attributes.get("data") if price_state else None)

        soc = _state_float(self.hass, config.get(CONF_BATTERY_SOC_SENSOR))
        house_load = _state_float(self.hass, config.get(CONF_HOUSE_LOAD_SENSOR))
        pv_forecast = _solar_forecast_remaining_kwh(self.hass, config.get(CONF_SOLAR_FORECAST_SENSORS, []))

        decision = plan_battery_policy(
            PlannerInputs(
                now=dt_util.now(),
                price_slots=price_slots,
                battery_soc_percent=soc,
                pv_forecast_remaining_kwh=pv_forecast,
                house_load_w=house_load,
                export_limit_w=DEFAULT_EXPORT_LIMIT_W,
                default_discharge_limit_w=DEFAULT_DISCHARGE_LIMIT_W,
                min_soc_percent=DEFAULT_MIN_SOC_PERCENT,
            )
        )
        return {
            "decision": decision,
            "price_slot_count": len(price_slots),
            "battery_soc_percent": soc,
            "house_load_w": house_load,
            "pv_forecast_remaining_kwh": pv_forecast,
            "write_enabled": config.get(CONF_WRITE_ENABLED, DEFAULT_WRITE_ENABLED),
        }


def _state_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _solar_forecast_remaining_kwh(hass: HomeAssistant, entity_ids: list[str] | str | None) -> float | None:
    if not entity_ids:
        return None
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    values: list[float] = []
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            continue
        for key in ("remaining_today", "forecast_remaining_kwh", "today", "tomorrow"):
            value = state.attributes.get(key)
            try:
                values.append(float(value))
                break
            except (TypeError, ValueError):
                continue
        else:
            try:
                values.append(float(state.state))
            except (TypeError, ValueError):
                continue
    if not values:
        return None
    return max(values)


class Gen24PolicySensor(CoordinatorEntity, SensorEntity):
    """Current policy sensor."""

    _attr_has_entity_name = True
    _attr_name = "Battery Policy"

    def __init__(self, coordinator: Gen24EnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_battery_policy"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str | None:
        decision = self.coordinator.data["decision"]
        return decision.mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data["decision"]
        write_enabled = self.coordinator.data["write_enabled"]
        return {
            ATTR_REASON: decision.reason,
            ATTR_POLICY_WRITABLE: decision.write_allowed,
            ATTR_WRITE_ENABLED: write_enabled,
            ATTR_EFFECTIVE_WRITE_ALLOWED: write_enabled and decision.write_allowed,
            ATTR_PRICE_SOURCE_VALID: decision.price_source_valid,
            ATTR_SOLAR_FORECAST_VALID: decision.solar_forecast_valid,
            "price_slot_count": self.coordinator.data["price_slot_count"],
            "battery_soc_percent": self.coordinator.data["battery_soc_percent"],
            "house_load_w": self.coordinator.data["house_load_w"],
            "pv_forecast_remaining_kwh": self.coordinator.data["pv_forecast_remaining_kwh"],
        }


class Gen24DischargeLimitSensor(CoordinatorEntity, SensorEntity):
    """Desired discharge limit sensor."""

    _attr_has_entity_name = True
    _attr_name = "Desired Discharge Limit"
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: Gen24EnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_desired_discharge_limit"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int | None:
        decision = self.coordinator.data["decision"]
        return decision.discharge_limit_w

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data["decision"]
        return {ATTR_MODE: decision.mode, ATTR_REASON: decision.reason}
