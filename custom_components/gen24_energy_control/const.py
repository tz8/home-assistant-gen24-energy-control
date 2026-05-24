"""Constants for GEN24 Energy Control."""

DOMAIN = "gen24_energy_control"

CONF_INVERTER_URL = "inverter_url"
CONF_PRICE_SENSOR = "price_sensor"
CONF_SOLAR_FORECAST_SENSORS = "solar_forecast_sensors"
CONF_BATTERY_SOC_SENSOR = "battery_soc_sensor"
CONF_HOUSE_LOAD_SENSOR = "house_load_sensor"
CONF_WRITE_ENABLED = "write_enabled"

DEFAULT_INVERTER_URL = "http://192.168.178.135"
DEFAULT_DISCHARGE_LIMIT_W = 2800
DEFAULT_EXPORT_LIMIT_W = 7000
DEFAULT_MIN_SOC_PERCENT = 15
DEFAULT_WRITE_ENABLED = False

ATTR_REASON = "reason"
ATTR_MODE = "mode"
ATTR_WRITE_ALLOWED = "write_allowed"
ATTR_PRICE_SOURCE_VALID = "price_source_valid"
ATTR_SOLAR_FORECAST_VALID = "solar_forecast_valid"
