"""Config flow for GEN24 Energy Control."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CHARGE_POWER_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_GRID_EXPORT_SENSOR,
    CONF_HOUSE_LOAD_SENSOR,
    CONF_INVERTER_URL,
    CONF_PRICE_SENSOR,
    CONF_PV_PRODUCTION_TODAY_SENSOR,
    CONF_SOLAR_FORECAST_REMAINING_TODAY_SENSOR,
    CONF_SOLAR_FORECAST_SENSORS,
    CONF_WRITE_ENABLED,
    DEFAULT_BATTERY_CHARGE_POWER_SENSOR,
    DEFAULT_GRID_EXPORT_SENSOR,
    DEFAULT_INVERTER_URL,
    DEFAULT_SOLAR_FORECAST_REMAINING_TODAY_SENSOR,
    DEFAULT_WRITE_ENABLED,
    DOMAIN,
)

_DEFAULT_PRICE_SENSOR = "sensor.epex_spot_data_total_price"
_KNOWN_FORECAST_ENTITY_IDS = [
    "sensor.pv_forecast_heute",
    "sensor.pv_forecast_morgen",
    "sensor.pv_forecast_uebermorgen",
    "sensor.pv_forecast_tag_4",
    "sensor.pv_forecast_tag_5",
    "sensor.pv_forecast_tag_6",
    "sensor.pv_forecast_tag_7",
]


_ENTITY_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
_MULTI_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        domain="sensor",
        multiple=True,
    )
)


def _normalize_inverter_url(value: str) -> str:
    """Normalize the user-provided inverter URL."""
    return value.strip().rstrip("/")


def _validate_inverter_url(value: str) -> str | None:
    """Validate the inverter URL and return an error key if invalid."""
    normalized = _normalize_inverter_url(value)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid_inverter_url"
    return None


def _forecast_entity_error(user_input: dict[str, Any]) -> str | None:
    """Validate the ordered solar forecast entity list."""
    forecast_entities = user_input.get(CONF_SOLAR_FORECAST_SENSORS) or []
    if isinstance(forecast_entities, str):
        forecast_entities = [forecast_entities]
    if len(forecast_entities) < 2:
        return "forecast_entities_too_few"
    if len(forecast_entities) > 7:
        return "forecast_entities_too_many"
    return None


def _suggest_entity_id(
    hass: HomeAssistant,
    defaults: dict[str, Any],
    key: str,
    fallback: str | None = None,
) -> str | None:
    """Return a stored value, otherwise only use a fallback that actually exists."""
    if key in defaults:
        return defaults.get(key)
    if fallback and hass.states.get(fallback) is not None:
        return fallback
    return None


def _suggest_forecast_entities(hass: HomeAssistant, defaults: dict[str, Any]) -> list[str]:
    """Return stored forecast entities, otherwise a known ordered default if available."""
    stored = defaults.get(CONF_SOLAR_FORECAST_SENSORS)
    if stored:
        if isinstance(stored, str):
            return [stored]
        return list(stored)

    detected = [entity_id for entity_id in _KNOWN_FORECAST_ENTITY_IDS if hass.states.get(entity_id) is not None]
    return detected if len(detected) >= 2 else []


def _required_field(key: str, default: Any | None = None) -> vol.Marker:
    """Build a required voluptuous field with or without default."""
    if default is None:
        return vol.Required(key)
    return vol.Required(key, default=default)


def _optional_field(key: str, default: Any | None = None) -> vol.Marker:
    """Build an optional voluptuous field with or without default."""
    if default is None:
        return vol.Optional(key)
    return vol.Optional(key, default=default)


def _connection_schema(hass: HomeAssistant, defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Schema for the connection / core planning inputs step."""
    defaults = defaults or {}
    inverter_default = defaults.get(CONF_INVERTER_URL, DEFAULT_INVERTER_URL)
    price_default = _suggest_entity_id(hass, defaults, CONF_PRICE_SENSOR, _DEFAULT_PRICE_SENSOR)
    return vol.Schema(
        {
            _required_field(CONF_INVERTER_URL, inverter_default): str,
            _required_field(CONF_PRICE_SENSOR, price_default): _ENTITY_SELECTOR,
        }
    )


def _forecast_schema(hass: HomeAssistant, defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Schema for the PV forecast inputs step."""
    defaults = defaults or {}
    forecast_defaults = _suggest_forecast_entities(hass, defaults)
    remaining_default = _suggest_entity_id(
        hass,
        defaults,
        CONF_SOLAR_FORECAST_REMAINING_TODAY_SENSOR,
        DEFAULT_SOLAR_FORECAST_REMAINING_TODAY_SENSOR,
    )
    production_default = _suggest_entity_id(hass, defaults, CONF_PV_PRODUCTION_TODAY_SENSOR)
    return vol.Schema(
        {
            _required_field(CONF_SOLAR_FORECAST_SENSORS, forecast_defaults): _MULTI_ENTITY_SELECTOR,
            _optional_field(CONF_SOLAR_FORECAST_REMAINING_TODAY_SENSOR, remaining_default): _ENTITY_SELECTOR,
            _optional_field(CONF_PV_PRODUCTION_TODAY_SENSOR, production_default): _ENTITY_SELECTOR,
        }
    )


def _live_data_schema(hass: HomeAssistant, defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Schema for live power / safety inputs step."""
    defaults = defaults or {}
    battery_soc_default = _suggest_entity_id(hass, defaults, CONF_BATTERY_SOC_SENSOR)
    house_load_default = _suggest_entity_id(hass, defaults, CONF_HOUSE_LOAD_SENSOR)
    grid_export_default = _suggest_entity_id(hass, defaults, CONF_GRID_EXPORT_SENSOR, DEFAULT_GRID_EXPORT_SENSOR)
    battery_charge_default = _suggest_entity_id(
        hass,
        defaults,
        CONF_BATTERY_CHARGE_POWER_SENSOR,
        DEFAULT_BATTERY_CHARGE_POWER_SENSOR,
    )
    write_enabled_default = defaults.get(CONF_WRITE_ENABLED, DEFAULT_WRITE_ENABLED)
    return vol.Schema(
        {
            _required_field(CONF_BATTERY_SOC_SENSOR, battery_soc_default): _ENTITY_SELECTOR,
            _required_field(CONF_HOUSE_LOAD_SENSOR, house_load_default): _ENTITY_SELECTOR,
            _optional_field(CONF_GRID_EXPORT_SENSOR, grid_export_default): _ENTITY_SELECTOR,
            _optional_field(CONF_BATTERY_CHARGE_POWER_SENSOR, battery_charge_default): _ENTITY_SELECTOR,
            _required_field(CONF_WRITE_ENABLED, write_enabled_default): bool,
        }
    )


def _merged(defaults: dict[str, Any], updates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge stored defaults and new step input."""
    return dict(defaults) | dict(updates or {})


class Gen24EnergyControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the first step: connection and price source."""
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized = dict(user_input)
            normalized[CONF_INVERTER_URL] = _normalize_inverter_url(normalized[CONF_INVERTER_URL])
            if inverter_url_error := _validate_inverter_url(normalized[CONF_INVERTER_URL]):
                errors[CONF_INVERTER_URL] = inverter_url_error
            if not errors:
                self._data.update(normalized)
                return await self.async_step_forecast()
            return self.async_show_form(
                step_id="user",
                data_schema=_connection_schema(self.hass, _merged(self._data, normalized)),
                errors=errors,
            )

        return self.async_show_form(step_id="user", data_schema=_connection_schema(self.hass, self._data), errors=errors)

    async def async_step_forecast(self, user_input: dict[str, Any] | None = None):
        """Handle the forecast source step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            merged_input = _merged(self._data, user_input)
            if forecast_error := _forecast_entity_error(merged_input):
                errors[CONF_SOLAR_FORECAST_SENSORS] = forecast_error
            if not errors:
                self._data.update(user_input)
                return await self.async_step_live()
            return self.async_show_form(
                step_id="forecast",
                data_schema=_forecast_schema(self.hass, merged_input),
                errors=errors,
            )

        return self.async_show_form(step_id="forecast", data_schema=_forecast_schema(self.hass, self._data), errors=errors)

    async def async_step_live(self, user_input: dict[str, Any] | None = None):
        """Handle live power inputs and write safety."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            await self.async_set_unique_id("gen24_energy_control")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="GEN24 Energy Control", data=self._data)

        return self.async_show_form(step_id="live", data_schema=_live_data_schema(self.hass, self._data), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return Gen24EnergyControlOptionsFlow(config_entry)


class Gen24EnergyControlOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data) | dict(config_entry.options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Edit the connection and price-source step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized = dict(user_input)
            normalized[CONF_INVERTER_URL] = _normalize_inverter_url(normalized[CONF_INVERTER_URL])
            if inverter_url_error := _validate_inverter_url(normalized[CONF_INVERTER_URL]):
                errors[CONF_INVERTER_URL] = inverter_url_error
            if not errors:
                self._data.update(normalized)
                return await self.async_step_forecast()
            return self.async_show_form(
                step_id="init",
                data_schema=_connection_schema(self.hass, _merged(self._data, normalized)),
                errors=errors,
            )

        return self.async_show_form(step_id="init", data_schema=_connection_schema(self.hass, self._data), errors=errors)

    async def async_step_forecast(self, user_input: dict[str, Any] | None = None):
        """Edit the forecast-source step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            merged_input = _merged(self._data, user_input)
            if forecast_error := _forecast_entity_error(merged_input):
                errors[CONF_SOLAR_FORECAST_SENSORS] = forecast_error
            if not errors:
                self._data.update(user_input)
                return await self.async_step_live()
            return self.async_show_form(
                step_id="forecast",
                data_schema=_forecast_schema(self.hass, merged_input),
                errors=errors,
            )

        return self.async_show_form(step_id="forecast", data_schema=_forecast_schema(self.hass, self._data), errors=errors)

    async def async_step_live(self, user_input: dict[str, Any] | None = None):
        """Edit live power inputs and write safety."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)

        return self.async_show_form(step_id="live", data_schema=_live_data_schema(self.hass, self._data), errors=errors)
