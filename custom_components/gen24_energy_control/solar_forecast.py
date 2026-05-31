"""Pure solar forecast helpers for GEN24 Energy Control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SolarForecastValues:
    """Solar forecast values parsed from configured sensors."""

    today_kwh: float | None
    remaining_today_kwh: float | None
    tomorrow_kwh: float | None
    days_kwh: list[float | None]
    source_entity_id: str | None
    remaining_source_entity_id: str | None
    remaining_source_kind: str | None = None


def remaining_today_kwh(
    forecast_today_kwh: float | None,
    pv_production_today_kwh: float | None,
    forecast_remaining_today_kwh: float | None = None,
) -> float | None:
    """Return expected PV energy still remaining today.

    Prefer a provider's explicit remaining-today forecast when available. A
    full-day forecast minus actual production can hit zero too early when the
    plant overperformed the forecast so far, even though the provider still
    expects useful production later in the day.
    """
    if forecast_remaining_today_kwh is not None:
        return max(0.0, forecast_remaining_today_kwh)
    if forecast_today_kwh is None:
        return None
    if pv_production_today_kwh is None:
        return forecast_today_kwh
    return max(0.0, forecast_today_kwh - pv_production_today_kwh)


def parse_solar_forecast_values(
    hass: Any,
    forecast_entity_ids: list[str] | str | None,
    pv_production_today_kwh: float | None,
    remaining_today_entity_id: str | None = None,
) -> SolarForecastValues:
    """Return ordered solar forecast values from configured sensors."""
    if not forecast_entity_ids:
        return SolarForecastValues(None, None, None, [], None, None)
    if isinstance(forecast_entity_ids, str):
        forecast_entity_ids = [forecast_entity_ids]

    today: float | None = None
    tomorrow: float | None = None
    days: list[float | None] = []
    source_entity_id: str | None = None

    for index, entity_id in enumerate(forecast_entity_ids[:7]):
        state = hass.states.get(entity_id)
        if state is None:
            days.append(None)
            continue

        day_value = _float_state(state)
        days.append(day_value)

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

        if index == 0 and today is None:
            today = _float_state(state)
            if today is not None:
                source_entity_id = entity_id
        elif index == 1 and tomorrow is None:
            tomorrow = _float_state(state)

    remaining_today = None
    remaining_source_entity_id = None
    remaining_source_kind = None
    if remaining_today_entity_id:
        remaining_state = hass.states.get(remaining_today_entity_id)
        remaining_today = _float_state(remaining_state) if remaining_state is not None else None
        if remaining_today is not None:
            remaining_source_entity_id = remaining_today_entity_id
            remaining_source_kind = "direct_sensor"

    if remaining_today is None:
        remaining_today = remaining_today_kwh(today, pv_production_today_kwh)
        if remaining_today is not None:
            if pv_production_today_kwh is None:
                remaining_source_kind = "today_total"
            else:
                remaining_source_kind = "derived_from_today_minus_production"

    return SolarForecastValues(
        today_kwh=today,
        remaining_today_kwh=remaining_today,
        tomorrow_kwh=tomorrow,
        days_kwh=days,
        source_entity_id=source_entity_id,
        remaining_source_entity_id=remaining_source_entity_id,
        remaining_source_kind=remaining_source_kind,
    )


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
    except (AttributeError, TypeError, ValueError):
        return None
