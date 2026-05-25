"""Battery policy planner for GEN24 Energy Control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .price_slots import PriceSlot, current_slot, price_percentile


@dataclass(frozen=True, slots=True)
class PlannerInputs:
    """Inputs used to derive a conservative battery policy."""

    now: datetime
    price_slots: list[PriceSlot]
    battery_soc_percent: float | None
    pv_forecast_remaining_kwh: float | None
    house_load_w: float | None
    export_limit_w: int = 7000
    default_discharge_limit_w: int = 2800
    min_soc_percent: float = 15
    battery_capacity_kwh: float = 13.8
    max_charge_limit_w: int = 6000
    min_forecast_charge_limit_w: int = 300
    charge_target_hour: int = 17
    charge_smoothing_factor: float = 0.5


@dataclass(frozen=True, slots=True)
class BatteryPolicyDecision:
    """Resulting GEN24 write policy."""

    mode: str
    reason: str
    discharge_limit_w: int | None
    charge_limit_w: int | None
    write_allowed: bool
    price_source_valid: bool
    solar_forecast_valid: bool
    charge_limit_basis: str | None = None


def _forecast_valid(value: float | None) -> bool:
    return value is not None and value >= 0


def _hours_until_target(now: datetime, target_hour: int) -> float:
    """Return remaining hours until today's charge target, with a small floor."""
    current_hour = now.hour + now.minute / 60 + now.second / 3600
    return max(target_hour - current_hour, 0.25)


def _forecast_charge_limit(inputs: PlannerInputs) -> tuple[int, str]:
    """Approximate Wiggal-style forecast charge limiting.

    Wiggal's controller does not simply switch CHARGE_MAX to 0 during sunny
    cheap-price windows. It derives a small maximum charge value from remaining
    battery headroom, forecast surplus, target hour, and a smoothing factor.
    This conservative approximation uses a floor so HA shadow mode can model
    the observed ~300 W behavior instead of hard-blocking charging.
    """
    assert inputs.battery_soc_percent is not None
    assert inputs.house_load_w is not None
    assert inputs.pv_forecast_remaining_kwh is not None

    hours = _hours_until_target(inputs.now, inputs.charge_target_hour)
    battery_headroom_kwh = inputs.battery_capacity_kwh * max(0, 100 - inputs.battery_soc_percent) / 100
    house_load_until_target_kwh = inputs.house_load_w * hours / 1000
    pv_surplus_kwh = max(0, inputs.pv_forecast_remaining_kwh - house_load_until_target_kwh)
    remaining_charge_need_kwh = max(0, battery_headroom_kwh - pv_surplus_kwh)
    calculated_w = int((remaining_charge_need_kwh * 1000 / hours) * inputs.charge_smoothing_factor)
    calculated_w = max(0, min(inputs.max_charge_limit_w, calculated_w))

    if calculated_w == 0 and inputs.pv_forecast_remaining_kwh >= 8:
        return min(inputs.max_charge_limit_w, inputs.min_forecast_charge_limit_w), "forecast_planner_floor"
    return calculated_w, "forecast_planner"


def plan_battery_policy(inputs: PlannerInputs) -> BatteryPolicyDecision:
    """Plan a safe GEN24 battery policy.

    The planner is deliberately conservative. It decides *desired* charge and
    discharge limits only; the Home Assistant integration applies additional
    ownership, cooldown, and write-enabled checks before touching the inverter.
    """
    slot = current_slot(inputs.price_slots, inputs.now)
    price_valid = slot is not None and len(inputs.price_slots) >= 2
    forecast_valid = _forecast_valid(inputs.pv_forecast_remaining_kwh)

    if not price_valid:
        return BatteryPolicyDecision(
            mode="safe_fallback",
            reason="No valid current price slot; keep default discharge policy and do not write price strategy.",
            discharge_limit_w=inputs.default_discharge_limit_w,
            charge_limit_w=None,
            write_allowed=False,
            price_source_valid=False,
            solar_forecast_valid=forecast_valid,
        )

    if inputs.battery_soc_percent is None or inputs.house_load_w is None or not forecast_valid:
        return BatteryPolicyDecision(
            mode="waiting_for_sources",
            reason="One or more configured input sources are not ready; keep default discharge policy and do not write.",
            discharge_limit_w=inputs.default_discharge_limit_w,
            charge_limit_w=None,
            write_allowed=False,
            price_source_valid=True,
            solar_forecast_valid=forecast_valid,
        )

    if inputs.battery_soc_percent <= inputs.min_soc_percent:
        return BatteryPolicyDecision(
            mode="protect_min_soc",
            reason="Battery SOC is at or below minimum; block discharge.",
            discharge_limit_w=0,
            charge_limit_w=None,
            write_allowed=True,
            price_source_valid=True,
            solar_forecast_valid=forecast_valid,
        )

    percentile = price_percentile(inputs.price_slots, slot)
    pv_remaining = inputs.pv_forecast_remaining_kwh or 0

    # Cheap current energy and meaningful PV still ahead: conserve battery and
    # use a Wiggal-style forecast charge limit instead of hard-blocking charge.
    if percentile <= 0.25 and forecast_valid and pv_remaining >= 8:
        charge_limit_w, charge_limit_basis = _forecast_charge_limit(inputs)
        return BatteryPolicyDecision(
            mode="hold_for_cheap_pv_window",
            reason="Current price is cheap and solar forecast is high; block discharge and use a forecast-based charge limit to preserve battery headroom for the PV peak.",
            discharge_limit_w=0,
            charge_limit_w=charge_limit_w,
            write_allowed=True,
            price_source_valid=True,
            solar_forecast_valid=True,
            charge_limit_basis=charge_limit_basis,
        )

    if percentile >= 0.75:
        return BatteryPolicyDecision(
            mode="price_support_discharge",
            reason="Current price is expensive; avoid battery charging and allow configured default battery discharge.",
            discharge_limit_w=inputs.default_discharge_limit_w,
            charge_limit_w=0,
            write_allowed=True,
            price_source_valid=True,
            solar_forecast_valid=forecast_valid,
            charge_limit_basis="price_block",
        )

    return BatteryPolicyDecision(
        mode="balanced_self_consumption",
        reason="Price is neither clearly cheap nor expensive; use default discharge policy.",
        discharge_limit_w=inputs.default_discharge_limit_w,
        charge_limit_w=None,
        write_allowed=True,
        price_source_valid=True,
        solar_forecast_valid=forecast_valid,
    )
