from custom_components.gen24_energy_control.solar_forecast import (
    SolarForecastValues,
    parse_solar_forecast_values,
    remaining_today_kwh,
)


def test_remaining_today_prefers_provider_remaining_when_actual_exceeds_total_forecast():
    remaining = remaining_today_kwh(
        forecast_today_kwh=47.671,
        pv_production_today_kwh=48.857,
        forecast_remaining_today_kwh=14.224,
    )

    assert remaining == 14.224


def test_remaining_today_falls_back_to_total_minus_actual_without_provider_remaining():
    remaining = remaining_today_kwh(
        forecast_today_kwh=48.509,
        pv_production_today_kwh=47.44,
        forecast_remaining_today_kwh=None,
    )

    assert remaining == 1.0690000000000026


class DummyState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class DummyStateStore:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        return self._mapping.get(entity_id)


class DummyHass:
    def __init__(self, mapping):
        self.states = DummyStateStore(mapping)


def test_prefers_direct_remaining_today_sensor_when_configured():
    hass = DummyHass(
        {
            "sensor.forecast_today": DummyState("12.5"),
            "sensor.forecast_tomorrow": DummyState("9.2"),
            "sensor.forecast_remaining_today": DummyState("3.4"),
        }
    )

    values = parse_solar_forecast_values(
        hass,
        forecast_entity_ids=["sensor.forecast_today", "sensor.forecast_tomorrow"],
        pv_production_today_kwh=8.0,
        remaining_today_entity_id="sensor.forecast_remaining_today",
    )

    assert values == SolarForecastValues(
        today_kwh=12.5,
        remaining_today_kwh=3.4,
        tomorrow_kwh=9.2,
        days_kwh=[12.5, 9.2],
        source_entity_id="sensor.forecast_today",
        remaining_source_entity_id="sensor.forecast_remaining_today",
        remaining_source_kind="direct_sensor",
    )
    assert values.remaining_source_kind == "direct_sensor"


def test_falls_back_to_today_minus_production_when_no_direct_remaining_sensor_is_configured():
    hass = DummyHass(
        {
            "sensor.forecast_today": DummyState("12.5"),
            "sensor.forecast_tomorrow": DummyState("9.2"),
        }
    )

    values = parse_solar_forecast_values(
        hass,
        forecast_entity_ids=["sensor.forecast_today", "sensor.forecast_tomorrow"],
        pv_production_today_kwh=8.0,
        remaining_today_entity_id=None,
    )

    assert values.remaining_today_kwh == 4.5
    assert values.remaining_source_entity_id is None
    assert values.remaining_source_kind == "derived_from_today_minus_production"


def test_falls_back_when_direct_remaining_sensor_is_not_numeric():
    hass = DummyHass(
        {
            "sensor.forecast_today": DummyState("12.5"),
            "sensor.forecast_tomorrow": DummyState("9.2"),
            "sensor.forecast_remaining_today": DummyState("unknown"),
        }
    )

    values = parse_solar_forecast_values(
        hass,
        forecast_entity_ids=["sensor.forecast_today", "sensor.forecast_tomorrow"],
        pv_production_today_kwh=8.0,
        remaining_today_entity_id="sensor.forecast_remaining_today",
    )

    assert values.remaining_today_kwh == 4.5
    assert values.remaining_source_entity_id is None
    assert values.remaining_source_kind == "derived_from_today_minus_production"


def test_fallback_remaining_today_never_goes_negative_when_forecast_is_already_exceeded():
    hass = DummyHass(
        {
            "sensor.forecast_today": DummyState("12.5"),
            "sensor.forecast_tomorrow": DummyState("9.2"),
        }
    )

    values = parse_solar_forecast_values(
        hass,
        forecast_entity_ids=["sensor.forecast_today", "sensor.forecast_tomorrow"],
        pv_production_today_kwh=14.0,
        remaining_today_entity_id=None,
    )

    assert values.remaining_today_kwh == 0.0
    assert values.remaining_source_kind == "derived_from_today_minus_production"


def test_uses_today_total_when_no_pv_production_sensor_is_available():
    hass = DummyHass(
        {
            "sensor.forecast_today": DummyState("12.5"),
            "sensor.forecast_tomorrow": DummyState("9.2"),
        }
    )

    values = parse_solar_forecast_values(
        hass,
        forecast_entity_ids=["sensor.forecast_today", "sensor.forecast_tomorrow"],
        pv_production_today_kwh=None,
        remaining_today_entity_id=None,
    )

    assert values.remaining_today_kwh == 12.5
    assert values.remaining_source_entity_id is None
    assert values.remaining_source_kind == "today_total"
