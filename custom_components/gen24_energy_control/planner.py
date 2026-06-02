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
    current_grid_export_w: float | None = None
    current_battery_charge_w: float | None = None
    previous_charge_limit_w: int | None = None
    live_export_enter_margin_w: int = 500
    live_export_exit_margin_w: int = 1500
    charge_target_hour: int = 17
    charge_smoothing_factor: float = 0.5
    charge_write_increase_threshold_w: int = 300
    charge_write_decrease_threshold_w: int = 1500
    soc_charge_cap_80_w: int = 2560
    soc_charge_cap_90_w: int = 1280
    soc_charge_cap_95_w: int = 640


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
    charge_limit_calculated_w: int | None = None
    charge_limit_requested_w: int | None = None
    charge_limit_previous_w: int | None = None
    charge_limit_write_needed: bool | None = None
    charge_limit_write_delta_w: int | None = None
    charge_limit_write_reason: str | None = None
    charge_limit_soc_cap_w: int | None = None


@dataclass(frozen=True, slots=True)
class ChargeLimitPlan:
    """Intermediate Wiggal-style charge-limit planning output."""

    charge_limit_w: int | None
    basis: str | None
    calculated_w: int | None
    requested_w: int | None
    previous_w: int | None
    write_needed: bool | None
    write_delta_w: int | None
    write_reason: str | None
    soc_cap_w: int | None


_EMPTY_CHARGE_LIMIT_PLAN = ChargeLimitPlan(
    charge_limit_w=None,
    basis=None,
    calculated_w=None,
    requested_w=None,
    previous_w=None,
    write_needed=None,
    write_delta_w=None,
    write_reason=None,
    soc_cap_w=None,
)


def _forecast_valid(value: float | None) -> bool:
    return value is not None and value >= 0


def _hours_until_target(now: datetime, target_hour: int) -> float:
    """Return remaining hours until today's charge target, with a small floor."""
    current_hour = now.hour + now.minute / 60 + now.second / 3600
    return max(target_hour - current_hour, 0.25)


def _join_basis(*parts: str | None) -> str | None:
    values: list[str] = []
    for part in parts:
        if not part:
            continue
        for item in str(part).split("|"):
            if item and item not in values:
                values.append(item)
    if not values:
        return None
    return "|".join(values)


def _forecast_surplus_kwh(inputs: PlannerInputs) -> float:
    """Estimate remaining PV surplus after covering house load until target hour."""
    if not _forecast_valid(inputs.pv_forecast_remaining_kwh) or inputs.house_load_w is None:
        return 0
    hours = _hours_until_target(inputs.now, inputs.charge_target_hour)
    house_load_until_target_kwh = max(inputs.house_load_w, 0) * hours / 1000
    return max(0, (inputs.pv_forecast_remaining_kwh or 0) - house_load_until_target_kwh)


def _should_plan_charge_limit(inputs: PlannerInputs) -> bool:
    """Return whether a Wiggal-like charge limit is meaningful right now."""
    if not _forecast_valid(inputs.pv_forecast_remaining_kwh) or inputs.house_load_w is None:
        return False

    previous_limit_w = inputs.previous_charge_limit_w or 0
    current_grid_export_w = inputs.current_grid_export_w or 0
    pv_surplus_kwh = _forecast_surplus_kwh(inputs)
    enter_threshold_w = inputs.export_limit_w - inputs.live_export_enter_margin_w
    exit_threshold_w = inputs.export_limit_w - inputs.live_export_exit_margin_w

    if current_grid_export_w >= enter_threshold_w:
        return True
    if previous_limit_w > 0 and current_grid_export_w >= exit_threshold_w:
        return True
    if pv_surplus_kwh >= 1:
        return True
    if previous_limit_w > 0 and pv_surplus_kwh >= 0.25:
        return True
    return False


def _forecast_charge_limit(inputs: PlannerInputs) -> tuple[int, str]:
    """Approximate Wiggal-style forecast charge limiting.

    The planner computes a continuous charge ceiling first, then the price/policy
    layer decides how to use it. Instead of subtracting the entire remaining PV
    surplus and collapsing to ``0`` too early, we reserve only a configurable
    fraction of future surplus. That keeps a non-zero, gradually changing charge
    ramp visible in shadow mode on mixed-weather days.
    """
    assert inputs.battery_soc_percent is not None
    assert inputs.house_load_w is not None
    assert inputs.pv_forecast_remaining_kwh is not None

    hours = _hours_until_target(inputs.now, inputs.charge_target_hour)
    battery_headroom_kwh = inputs.battery_capacity_kwh * max(0, 100 - inputs.battery_soc_percent) / 100
    house_load_until_target_kwh = inputs.house_load_w * hours / 1000
    pv_surplus_kwh = max(0, inputs.pv_forecast_remaining_kwh - house_load_until_target_kwh)
    forecast_reserve_kwh = min(battery_headroom_kwh, pv_surplus_kwh) * inputs.charge_smoothing_factor
    remaining_charge_need_kwh = max(0, battery_headroom_kwh - forecast_reserve_kwh)
    calculated_w = int((remaining_charge_need_kwh * 1000) / hours)
    calculated_w = max(0, min(inputs.max_charge_limit_w, calculated_w))

    morning_zero_threshold_w = int(inputs.charge_write_increase_threshold_w * 0.7)
    if 0 < calculated_w < morning_zero_threshold_w:
        return 0, "forecast_planner_morning_zero"
    if calculated_w == 0 and inputs.pv_forecast_remaining_kwh >= 8:
        return min(inputs.max_charge_limit_w, inputs.min_forecast_charge_limit_w), "forecast_planner_floor"
    return calculated_w, "forecast_planner"


def _live_export_charge_limit(inputs: PlannerInputs, forecast_limit_w: int) -> tuple[int, str] | None:
    """Raise charge limit when live export suggests curtailment risk, with hysteresis.

    Fast cloud movements can make live export jump around. Enter only when export
    is close to the inverter/export limit, then hold the raised value until export
    drops clearly below a lower exit threshold.
    """
    if inputs.current_grid_export_w is None:
        return None

    enter_threshold_w = inputs.export_limit_w - inputs.live_export_enter_margin_w
    exit_threshold_w = inputs.export_limit_w - inputs.live_export_exit_margin_w
    previous_limit_w = inputs.previous_charge_limit_w or 0

    if inputs.current_grid_export_w >= enter_threshold_w:
        spare_export_w = inputs.current_grid_export_w - enter_threshold_w
        current_battery_charge_w = max(0, int(inputs.current_battery_charge_w or 0))
        live_limit_w = current_battery_charge_w + int(spare_export_w)
        live_limit_w = max(forecast_limit_w, live_limit_w)
        return min(inputs.max_charge_limit_w, live_limit_w), "live_export_hysteresis_enter"

    if previous_limit_w > forecast_limit_w and inputs.current_grid_export_w >= exit_threshold_w:
        return min(inputs.max_charge_limit_w, previous_limit_w), "live_export_hysteresis_hold"

    return None


def _soc_charge_limit_cap(inputs: PlannerInputs) -> tuple[int, str] | None:
    """Return the active Akkuschonung cap, if any."""
    if inputs.battery_soc_percent is None:
        return None
    if inputs.battery_soc_percent >= 95:
        return inputs.soc_charge_cap_95_w, "soc_charge_cap_95"
    if inputs.battery_soc_percent >= 90:
        return inputs.soc_charge_cap_90_w, "soc_charge_cap_90"
    if inputs.battery_soc_percent >= 80:
        return inputs.soc_charge_cap_80_w, "soc_charge_cap_80"
    return None


def _charge_limit_write_state(
    inputs: PlannerInputs,
    charge_limit_w: int | None,
) -> tuple[int | None, bool | None, int | None, str | None]:
    """Return previous limit plus Wiggal-style write-hysteresis diagnostics."""
    previous_w = inputs.previous_charge_limit_w
    if charge_limit_w is None:
        return previous_w, None, None, None
    if previous_w is None:
        return None, True, None, "no_previous_limit"

    delta_w = charge_limit_w - previous_w
    if delta_w == 0:
        return previous_w, False, 0, "unchanged"
    if delta_w > 0:
        write_needed = delta_w >= inputs.charge_write_increase_threshold_w
        reason = "increase_above_hysteresis" if write_needed else "increase_within_hysteresis"
        return previous_w, write_needed, delta_w, reason

    delta_abs_w = abs(delta_w)
    write_needed = delta_abs_w >= inputs.charge_write_decrease_threshold_w
    reason = "decrease_above_hysteresis" if write_needed else "decrease_within_hysteresis"
    return previous_w, write_needed, delta_w, reason


def _planned_charge_limit(inputs: PlannerInputs) -> ChargeLimitPlan:
    """Calculate a Wiggal-like charge limit plus diagnostics."""
    if inputs.battery_soc_percent is None or inputs.house_load_w is None or not _should_plan_charge_limit(inputs):
        return _EMPTY_CHARGE_LIMIT_PLAN

    calculated_w, basis = _forecast_charge_limit(inputs)
    charge_limit_w = calculated_w

    live_charge_limit = _live_export_charge_limit(inputs, charge_limit_w)
    if live_charge_limit is not None:
        charge_limit_w, live_basis = live_charge_limit
        basis = _join_basis(basis, live_basis)

    soc_cap = _soc_charge_limit_cap(inputs)
    soc_cap_w: int | None = None
    if soc_cap is not None:
        soc_cap_w, soc_basis = soc_cap
        if charge_limit_w > soc_cap_w:
            charge_limit_w = soc_cap_w
            basis = _join_basis(basis, soc_basis)

    requested_w = charge_limit_w
    previous_w, write_needed, write_delta_w, write_reason = _charge_limit_write_state(inputs, requested_w)
    effective_charge_limit_w = requested_w
    if requested_w is not None and write_needed is False and previous_w is not None:
        effective_charge_limit_w = previous_w

    return ChargeLimitPlan(
        charge_limit_w=effective_charge_limit_w,
        basis=basis,
        calculated_w=calculated_w,
        requested_w=requested_w,
        previous_w=previous_w,
        write_needed=write_needed,
        write_delta_w=write_delta_w,
        write_reason=write_reason,
        soc_cap_w=soc_cap_w,
    )


def _decision(
    *,
    mode: str,
    reason: str,
    discharge_limit_w: int | None,
    charge_limit_w: int | None,
    write_allowed: bool,
    price_source_valid: bool,
    solar_forecast_valid: bool,
    charge_limit_basis: str | None = None,
    charge_plan: ChargeLimitPlan = _EMPTY_CHARGE_LIMIT_PLAN,
) -> BatteryPolicyDecision:
    return BatteryPolicyDecision(
        mode=mode,
        reason=reason,
        discharge_limit_w=discharge_limit_w,
        charge_limit_w=charge_limit_w,
        write_allowed=write_allowed,
        price_source_valid=price_source_valid,
        solar_forecast_valid=solar_forecast_valid,
        charge_limit_basis=charge_limit_basis,
        charge_limit_calculated_w=charge_plan.calculated_w,
        charge_limit_requested_w=charge_plan.requested_w,
        charge_limit_previous_w=charge_plan.previous_w,
        charge_limit_write_needed=charge_plan.write_needed,
        charge_limit_write_delta_w=charge_plan.write_delta_w,
        charge_limit_write_reason=charge_plan.write_reason,
        charge_limit_soc_cap_w=charge_plan.soc_cap_w,
    )


def _charge_limit_safe_for_expensive_mode(inputs: PlannerInputs, charge_plan: ChargeLimitPlan) -> bool:
    """Return whether the effective limit remains safe to honor in expensive slots."""
    if charge_plan.requested_w is None:
        return False

    current_grid_export_w = inputs.current_grid_export_w or 0
    enter_threshold_w = inputs.export_limit_w - inputs.live_export_enter_margin_w
    exit_threshold_w = inputs.export_limit_w - inputs.live_export_exit_margin_w
    meaningful_pv_window = _forecast_surplus_kwh(inputs) >= 1
    meaningful_live_export = current_grid_export_w >= enter_threshold_w or (
        (charge_plan.previous_w or 0) > 0 and current_grid_export_w >= exit_threshold_w
    )
    if not meaningful_pv_window and not meaningful_live_export:
        return False

    if charge_plan.charge_limit_w == charge_plan.requested_w:
        return True
    if charge_plan.previous_w is None:
        return True
    return charge_plan.previous_w <= charge_plan.requested_w


def _blocked_charge_plan(charge_plan: ChargeLimitPlan, effective_charge_limit_w: int = 0) -> ChargeLimitPlan:
    """Return diagnostics for an explicit price-block override of the charge limit."""
    previous_w = charge_plan.previous_w
    if previous_w is None:
        write_needed = True
        write_delta_w = None
        write_reason = "price_block_override_no_previous"
    else:
        write_delta_w = effective_charge_limit_w - previous_w
        write_needed = write_delta_w != 0
        write_reason = "price_block_override" if write_needed else "price_block_unchanged"

    return ChargeLimitPlan(
        charge_limit_w=effective_charge_limit_w,
        basis=_join_basis(charge_plan.basis, "price_block"),
        calculated_w=charge_plan.calculated_w,
        requested_w=charge_plan.requested_w,
        previous_w=previous_w,
        write_needed=write_needed,
        write_delta_w=write_delta_w,
        write_reason=write_reason,
        soc_cap_w=charge_plan.soc_cap_w,
    )


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
        return _decision(
            mode="safe_fallback",
            reason="No valid current price slot; keep default discharge policy and do not write price strategy.",
            discharge_limit_w=inputs.default_discharge_limit_w,
            charge_limit_w=None,
            write_allowed=False,
            price_source_valid=False,
            solar_forecast_valid=forecast_valid,
        )

    if inputs.battery_soc_percent is None or inputs.house_load_w is None or not forecast_valid:
        return _decision(
            mode="waiting_for_sources",
            reason="One or more configured input sources are not ready; keep default discharge policy and do not write.",
            discharge_limit_w=inputs.default_discharge_limit_w,
            charge_limit_w=None,
            write_allowed=False,
            price_source_valid=True,
            solar_forecast_valid=forecast_valid,
        )

    if inputs.battery_soc_percent <= inputs.min_soc_percent:
        return _decision(
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
    charge_plan = _planned_charge_limit(inputs)

    # Cheap current energy and meaningful PV still ahead: conserve battery and
    # expose the forecast planner result directly instead of hard-blocking charge.
    if percentile <= 0.25 and forecast_valid and pv_remaining >= 8:
        return _decision(
            mode="hold_for_cheap_pv_window",
            reason="Current price is cheap and solar forecast is high; block discharge and use the Wiggal-style forecast charge planner to preserve battery headroom for the PV peak.",
            discharge_limit_w=0,
            charge_limit_w=charge_plan.charge_limit_w,
            write_allowed=True,
            price_source_valid=True,
            solar_forecast_valid=True,
            charge_limit_basis=charge_plan.basis,
            charge_plan=charge_plan,
        )

    if percentile >= 0.75:
        if _charge_limit_safe_for_expensive_mode(inputs, charge_plan):
            return _decision(
                mode="price_support_discharge",
                reason="Current price is expensive; allow configured battery discharge but keep the forecast-derived charge ceiling so solar charging remains throttled instead of fully blocked.",
                discharge_limit_w=inputs.default_discharge_limit_w,
                charge_limit_w=charge_plan.charge_limit_w,
                write_allowed=True,
                price_source_valid=True,
                solar_forecast_valid=forecast_valid,
                charge_limit_basis=_join_basis(charge_plan.basis, "price_support_discharge"),
                charge_plan=charge_plan,
            )
        if charge_plan.requested_w is not None:
            blocked_charge_plan = _blocked_charge_plan(charge_plan)
            return _decision(
                mode="price_support_discharge",
                reason="Current price is expensive; the forecast planner would lower CHARGE_MAX, but price protection overrides that request and blocks charging so a higher previous limit cannot stay active.",
                discharge_limit_w=inputs.default_discharge_limit_w,
                charge_limit_w=blocked_charge_plan.charge_limit_w,
                write_allowed=True,
                price_source_valid=True,
                solar_forecast_valid=forecast_valid,
                charge_limit_basis=blocked_charge_plan.basis,
                charge_plan=blocked_charge_plan,
            )
        return _decision(
            mode="price_support_discharge",
            reason="Current price is expensive; avoid battery charging and allow configured default battery discharge.",
            discharge_limit_w=inputs.default_discharge_limit_w,
            charge_limit_w=0,
            write_allowed=True,
            price_source_valid=True,
            solar_forecast_valid=forecast_valid,
            charge_limit_basis="price_block",
        )

    if charge_plan.charge_limit_w is not None:
        return _decision(
            mode="balanced_self_consumption",
            reason="Price is neither clearly cheap nor expensive; keep default discharge policy and expose the Wiggal-style forecast charge ceiling for shadow comparison.",
            discharge_limit_w=inputs.default_discharge_limit_w,
            charge_limit_w=charge_plan.charge_limit_w,
            write_allowed=True,
            price_source_valid=True,
            solar_forecast_valid=forecast_valid,
            charge_limit_basis=charge_plan.basis,
            charge_plan=charge_plan,
        )

    return _decision(
        mode="balanced_self_consumption",
        reason="Price is neither clearly cheap nor expensive; use default discharge policy.",
        discharge_limit_w=inputs.default_discharge_limit_w,
        charge_limit_w=None,
        write_allowed=True,
        price_source_valid=True,
        solar_forecast_valid=forecast_valid,
    )
