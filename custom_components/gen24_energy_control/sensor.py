"""Sensors for GEN24 Energy Control."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_EFFECTIVE_WRITE_ALLOWED,
    ATTR_INPUT_SOURCES_READY,
    ATTR_MISSING_INPUT_SOURCES,
    ATTR_MODE,
    ATTR_POLICY_WRITABLE,
    ATTR_PRICE_SOURCE_VALID,
    ATTR_REASON,
    ATTR_SOLAR_FORECAST_VALID,
    ATTR_WRITE_ENABLED,
    CONF_BATTERY_SOC_SENSOR,
    CONF_HOUSE_LOAD_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_PV_PRODUCTION_TODAY_SENSOR,
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
    _async_track_configured_sources(hass, entry, coordinator)
    async_add_entities(
        [
            Gen24PolicySensor(coordinator, entry),
            Gen24DischargeLimitSensor(coordinator, entry),
            Gen24ChargeLimitSensor(coordinator, entry),
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


def _async_track_configured_sources(hass: HomeAssistant, entry: ConfigEntry, coordinator: "Gen24EnergyCoordinator") -> None:
    """Refresh promptly when configured source sensors become ready or change."""
    config = dict(entry.data) | dict(entry.options)
    entity_ids = _configured_source_entity_ids(config)
    if not entity_ids:
        return

    async def _source_changed(_event) -> None:
        await coordinator.async_request_refresh()

    entry.async_on_unload(async_track_state_change_event(hass, entity_ids, _source_changed))


def _configured_source_entity_ids(config: dict[str, Any]) -> list[str]:
    """Return all configured source entity IDs for event tracking."""
    entity_ids: list[str] = []
    for key in (CONF_PRICE_SENSOR, CONF_BATTERY_SOC_SENSOR, CONF_HOUSE_LOAD_SENSOR, CONF_PV_PRODUCTION_TODAY_SENSOR):
        entity_id = config.get(key)
        if entity_id:
            entity_ids.append(entity_id)
    forecast_entities = config.get(CONF_SOLAR_FORECAST_SENSORS, [])
    if isinstance(forecast_entities, str):
        forecast_entities = [forecast_entities]
    entity_ids.extend(entity_id for entity_id in forecast_entities if entity_id)
    return sorted(set(entity_ids))


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
        pv_production_today = _state_float(self.hass, config.get(CONF_PV_PRODUCTION_TODAY_SENSOR))
        solar_forecast = _solar_forecast_values(
            self.hass,
            config.get(CONF_SOLAR_FORECAST_SENSORS, []),
            pv_production_today,
        )
        pv_forecast = solar_forecast.remaining_today_kwh

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
            "pv_forecast_today_kwh": solar_forecast.today_kwh,
            "pv_production_today_kwh": pv_production_today,
            "pv_forecast_tomorrow_kwh": solar_forecast.tomorrow_kwh,
            "pv_forecast_days_kwh": solar_forecast.days_kwh,
            "pv_forecast_source_entity": solar_forecast.source_entity_id,
            "write_enabled": config.get(CONF_WRITE_ENABLED, DEFAULT_WRITE_ENABLED),
            "missing_input_sources": _missing_input_sources(len(price_slots), soc, house_load, pv_forecast),
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


@dataclass(frozen=True, slots=True)
class SolarForecastValues:
    """Solar forecast values parsed from the configured forecast sensors."""

    today_kwh: float | None
    remaining_today_kwh: float | None
    tomorrow_kwh: float | None
    days_kwh: list[float | None]
    source_entity_id: str | None


def _solar_forecast_values(
    hass: HomeAssistant,
    entity_ids: list[str] | str | None,
    pv_production_today_kwh: float | None,
) -> SolarForecastValues:
    """Return ordered solar forecast values from the configured sensors.

    The config flow exposes one multi-entity selector instead of many dedicated
    day fields. Treat the configured list as ordered forecast inputs:

    - sensor 1: forecast today total (required for policy decisions)
    - sensor 2: forecast tomorrow (optional diagnostic / future planning input)
    - later sensors: reserved for d2..d7 planning

    Remaining PV for today is computed as ``today forecast - actual PV produced
    today`` when a production-today sensor is configured. Without that sensor,
    the today forecast is used as a conservative startup fallback.
    """
    if not entity_ids:
        return SolarForecastValues(None, None, None, [], None)
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]

    today: float | None = None
    tomorrow: float | None = None
    days: list[float | None] = []
    source_entity_id: str | None = None

    for index, entity_id in enumerate(entity_ids[:7]):
        state = hass.states.get(entity_id)
        if state is None:
            days.append(None)
            continue

        day_value = _float_state(state)
        days.append(day_value)

        # Some integrations expose a single aggregate entity with attributes.
        if today is None:
            today = _first_float_attribute(
                state,
                (
                    "today",
                    "forecast_today_kwh",
                    "estimate_today",
                    "estimate",
                ),
            )
            if today is not None:
                source_entity_id = entity_id

        if tomorrow is None:
            tomorrow = _first_float_attribute(
                state,
                (
                    "tomorrow",
                    "forecast_tomorrow_kwh",
                    "estimate_tomorrow",
                ),
            )

        # Positional fallback for the multi-selector: first entry is today,
        # second entry is tomorrow. This matches the HA option screen and avoids
        # seven separate config-flow fields for simple setups.
        if index == 0 and today is None:
            today = _float_state(state)
            if today is not None:
                source_entity_id = entity_id
        elif index == 1 and tomorrow is None:
            tomorrow = _float_state(state)

    if today is None:
        remaining_today = None
    elif pv_production_today_kwh is None:
        remaining_today = today
    else:
        remaining_today = max(0.0, today - pv_production_today_kwh)

    return SolarForecastValues(today, remaining_today, tomorrow, days, source_entity_id)


def _first_float_attribute(state: Any, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            return float(state.attributes.get(key))
        except (TypeError, ValueError):
            continue
    return None


def _float_state(state: Any) -> float | None:
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _missing_input_sources(price_slot_count: int, battery_soc: float | None, house_load: float | None, pv_forecast: float | None) -> list[str]:
    """Return configured inputs that are not ready enough for write decisions."""
    missing: list[str] = []
    if price_slot_count < 2:
        missing.append("price_slots")
    if battery_soc is None:
        missing.append("battery_soc")
    if house_load is None:
        missing.append("house_load")
    if pv_forecast is None or pv_forecast < 0:
        missing.append("solar_forecast")
    return missing


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
        missing_input_sources = self.coordinator.data["missing_input_sources"]
        return {
            ATTR_REASON: decision.reason,
            ATTR_POLICY_WRITABLE: decision.write_allowed,
            ATTR_WRITE_ENABLED: write_enabled,
            ATTR_EFFECTIVE_WRITE_ALLOWED: write_enabled and decision.write_allowed,
            ATTR_INPUT_SOURCES_READY: not missing_input_sources,
            ATTR_MISSING_INPUT_SOURCES: missing_input_sources,
            ATTR_PRICE_SOURCE_VALID: decision.price_source_valid,
            ATTR_SOLAR_FORECAST_VALID: decision.solar_forecast_valid,
            "price_slot_count": self.coordinator.data["price_slot_count"],
            "battery_soc_percent": self.coordinator.data["battery_soc_percent"],
            "house_load_w": self.coordinator.data["house_load_w"],
            "desired_charge_limit_w": decision.charge_limit_w,
            "desired_discharge_limit_w": decision.discharge_limit_w,
            "pv_forecast_remaining_kwh": self.coordinator.data["pv_forecast_remaining_kwh"],
            "pv_forecast_today_kwh": self.coordinator.data["pv_forecast_today_kwh"],
            "pv_production_today_kwh": self.coordinator.data["pv_production_today_kwh"],
            "pv_forecast_tomorrow_kwh": self.coordinator.data["pv_forecast_tomorrow_kwh"],
            "pv_forecast_days_kwh": self.coordinator.data["pv_forecast_days_kwh"],
            "pv_forecast_source_entity": self.coordinator.data["pv_forecast_source_entity"],
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


class Gen24ChargeLimitSensor(CoordinatorEntity, SensorEntity):
    """Desired charge limit sensor."""

    _attr_has_entity_name = True
    _attr_name = "Desired Charge Limit"
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: Gen24EnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_desired_charge_limit"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int | None:
        decision = self.coordinator.data["decision"]
        return decision.charge_limit_w

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self.coordinator.data["decision"]
        return {ATTR_MODE: decision.mode, ATTR_REASON: decision.reason}
