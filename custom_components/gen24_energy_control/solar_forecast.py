"""Pure solar forecast helpers for GEN24 Energy Control."""

from __future__ import annotations


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
