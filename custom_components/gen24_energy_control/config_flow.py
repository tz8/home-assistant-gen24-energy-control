"""Config flow for GEN24 Energy Control."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_SOC_SENSOR,
    CONF_BATTERY_CHARGE_POWER_SENSOR,
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


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_INVERTER_URL, default=defaults.get(CONF_INVERTER_URL, DEFAULT_INVERTER_URL)): str,
            vol.Required(CONF_PRICE_SENSOR, default=defaults.get(CONF_PRICE_SENSOR, "sensor.epex_spot_data_total_price")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_SOLAR_FORECAST_SENSORS, default=defaults.get(CONF_SOLAR_FORECAST_SENSORS, [])): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Optional(CONF_SOLAR_FORECAST_REMAINING_TODAY_SENSOR, default=defaults.get(CONF_SOLAR_FORECAST_REMAINING_TODAY_SENSOR, DEFAULT_SOLAR_FORECAST_REMAINING_TODAY_SENSOR)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_PV_PRODUCTION_TODAY_SENSOR, default=defaults.get(CONF_PV_PRODUCTION_TODAY_SENSOR)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_BATTERY_SOC_SENSOR, default=defaults.get(CONF_BATTERY_SOC_SENSOR)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_HOUSE_LOAD_SENSOR, default=defaults.get(CONF_HOUSE_LOAD_SENSOR)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_GRID_EXPORT_SENSOR, default=defaults.get(CONF_GRID_EXPORT_SENSOR, DEFAULT_GRID_EXPORT_SENSOR)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_BATTERY_CHARGE_POWER_SENSOR, default=defaults.get(CONF_BATTERY_CHARGE_POWER_SENSOR, DEFAULT_BATTERY_CHARGE_POWER_SENSOR)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_WRITE_ENABLED, default=defaults.get(CONF_WRITE_ENABLED, DEFAULT_WRITE_ENABLED)): bool,
        }
    )


def _forecast_entity_error(user_input: dict[str, Any]) -> str | None:
    """Validate the ordered solar forecast entity list.

    The UI mirrors the clear Solar Forecast Card convention: one ordered list of
    day sensors, not seven separate fields.
    """
    forecast_entities = user_input.get(CONF_SOLAR_FORECAST_SENSORS) or []
    if isinstance(forecast_entities, str):
        forecast_entities = [forecast_entities]
    if len(forecast_entities) < 2:
        return "forecast_entities_too_few"
    if len(forecast_entities) > 7:
        return "forecast_entities_too_many"
    return None


class Gen24EnergyControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input is not None:
            if forecast_error := _forecast_entity_error(user_input):
                return self.async_show_form(
                    step_id="user",
                    data_schema=_schema(user_input),
                    errors={CONF_SOLAR_FORECAST_SENSORS: forecast_error},
                )
            await self.async_set_unique_id("gen24_energy_control")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="GEN24 Energy Control", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return Gen24EnergyControlOptionsFlow(config_entry)


class Gen24EnergyControlOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        if user_input is not None:
            if forecast_error := _forecast_entity_error(user_input):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_schema(user_input),
                    errors={CONF_SOLAR_FORECAST_SENSORS: forecast_error},
                )
            return self.async_create_entry(title="", data=user_input)
        defaults = dict(self._config_entry.data) | dict(self._config_entry.options)
        return self.async_show_form(step_id="init", data_schema=_schema(defaults))
