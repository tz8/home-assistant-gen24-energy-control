from datetime import datetime

from custom_components.gen24_energy_control.planner import PlannerInputs, plan_battery_policy
from custom_components.gen24_energy_control.price_slots import parse_price_slots


def _slots():
    return parse_price_slots([
        {"start_time": "2026-05-25T10:00:00+02:00", "end_time": "2026-05-25T10:15:00+02:00", "price_per_kwh": 0.12},
        {"start_time": "2026-05-25T10:15:00+02:00", "end_time": "2026-05-25T10:30:00+02:00", "price_per_kwh": 0.18},
        {"start_time": "2026-05-25T10:30:00+02:00", "end_time": "2026-05-25T10:45:00+02:00", "price_per_kwh": 0.42},
    ])


def test_planner_blocks_discharge_but_keeps_wiggal_style_charge_ramp_when_price_is_cheap_and_pv_forecast_is_high():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:05:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=39,
            house_load_w=900,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
            battery_capacity_kwh=13.8,
            max_charge_limit_w=6000,
            min_forecast_charge_limit_w=300,
            charge_target_hour=17,
            charge_smoothing_factor=0.5,
        )
    )

    assert decision.discharge_limit_w == 0
    assert decision.charge_limit_w == 548
    assert decision.charge_limit_calculated_w == 548
    assert decision.charge_limit_basis == "forecast_planner"
    assert decision.charge_limit_write_needed is True
    assert decision.mode == "hold_for_cheap_pv_window"
    assert "Wiggal-style forecast charge planner" in decision.reason


def test_planner_raises_charge_limit_when_live_export_is_near_export_limit():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:05:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=55,
            pv_forecast_remaining_kwh=20,
            house_load_w=300,
            current_grid_export_w=6800,
            current_battery_charge_w=700,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
            battery_capacity_kwh=13.8,
            max_charge_limit_w=6000,
            min_forecast_charge_limit_w=300,
            charge_target_hour=17,
            charge_smoothing_factor=0.5,
        )
    )

    assert decision.discharge_limit_w == 0
    assert decision.charge_limit_w == 1000
    assert decision.charge_limit_calculated_w == 448
    assert decision.charge_limit_basis == "forecast_planner|live_export_hysteresis_enter"
    assert decision.mode == "hold_for_cheap_pv_window"


def test_planner_keeps_live_export_charge_limit_until_export_falls_below_hysteresis_exit():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:05:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=55,
            pv_forecast_remaining_kwh=20,
            house_load_w=300,
            current_grid_export_w=5800,
            current_battery_charge_w=1200,
            previous_charge_limit_w=1800,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
            battery_capacity_kwh=13.8,
            max_charge_limit_w=6000,
            min_forecast_charge_limit_w=300,
            charge_target_hour=17,
            charge_smoothing_factor=0.5,
        )
    )

    assert decision.charge_limit_w == 1800
    assert decision.charge_limit_calculated_w == 448
    assert decision.charge_limit_requested_w == 1800
    assert decision.charge_limit_basis == "forecast_planner|live_export_hysteresis_hold"
    assert decision.charge_limit_previous_w == 1800
    assert decision.charge_limit_write_needed is False
    assert decision.charge_limit_write_reason == "unchanged"


def test_planner_returns_to_forecast_ramp_after_hysteresis_exit():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:05:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=55,
            pv_forecast_remaining_kwh=20,
            house_load_w=300,
            current_grid_export_w=4800,
            current_battery_charge_w=1200,
            previous_charge_limit_w=1800,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
            battery_capacity_kwh=13.8,
            max_charge_limit_w=6000,
            min_forecast_charge_limit_w=300,
            charge_target_hour=17,
            charge_smoothing_factor=0.5,
        )
    )

    assert decision.charge_limit_w == 1800
    assert decision.charge_limit_calculated_w == 448
    assert decision.charge_limit_requested_w == 448
    assert decision.charge_limit_basis == "forecast_planner"
    assert decision.charge_limit_previous_w == 1800
    assert decision.charge_limit_write_needed is False
    assert decision.charge_limit_write_reason == "decrease_within_hysteresis"


def test_planner_keeps_forecast_charge_ceiling_in_balanced_mode_for_shadow_comparison():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:20:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=12,
            house_load_w=900,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.charge_limit_w == 688
    assert decision.charge_limit_basis == "forecast_planner"
    assert decision.mode == "balanced_self_consumption"
    assert "shadow comparison" in decision.reason


def test_planner_keeps_forecast_charge_ceiling_even_when_price_is_expensive_if_pv_is_still_active():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=12,
            house_load_w=900,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.charge_limit_w == 697
    assert decision.charge_limit_requested_w == 697
    assert decision.charge_limit_basis == "forecast_planner|price_support_discharge"
    assert decision.mode == "price_support_discharge"
    assert "forecast-derived charge ceiling" in decision.reason


def test_planner_applies_akkuschonung_cap_to_late_day_charge_limit():
    late_slots = parse_price_slots([
        {"start_time": "2026-05-25T16:15:00+02:00", "end_time": "2026-05-25T16:30:00+02:00", "price_per_kwh": 0.12},
        {"start_time": "2026-05-25T16:30:00+02:00", "end_time": "2026-05-25T16:45:00+02:00", "price_per_kwh": 0.42},
        {"start_time": "2026-05-25T16:45:00+02:00", "end_time": "2026-05-25T17:00:00+02:00", "price_per_kwh": 0.30},
    ])

    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T16:30:00+02:00"),
            price_slots=late_slots,
            battery_soc_percent=81,
            pv_forecast_remaining_kwh=6,
            house_load_w=0,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.charge_limit_calculated_w == 2622
    assert decision.charge_limit_w == 2560
    assert decision.charge_limit_requested_w == 2560
    assert decision.charge_limit_soc_cap_w == 2560
    assert decision.charge_limit_basis == "forecast_planner|soc_charge_cap_80|price_support_discharge"


def test_planner_allows_default_discharge_and_blocks_charge_when_current_price_is_expensive_without_meaningful_pv_plan():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=4,
            house_load_w=900,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.charge_limit_w == 0
    assert decision.mode == "price_support_discharge"
    assert decision.charge_limit_basis == "price_block"
    assert "expensive" in decision.reason


def test_planner_blocks_charge_when_price_is_expensive_and_only_live_charge_noise_exists():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=1,
            house_load_w=900,
            current_grid_export_w=80,
            current_battery_charge_w=1100,
            previous_charge_limit_w=1200,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.charge_limit_w == 0
    assert decision.charge_limit_requested_w is None
    assert decision.charge_limit_basis == "price_block"
    assert decision.mode == "price_support_discharge"


def test_planner_blocks_charge_when_price_is_expensive_and_house_load_consumes_remaining_forecast():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=6,
            house_load_w=3000,
            previous_charge_limit_w=1800,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.charge_limit_w == 0
    assert decision.charge_limit_requested_w is None
    assert decision.charge_limit_basis == "price_block"
    assert decision.mode == "price_support_discharge"


def test_planner_blocks_charge_when_expensive_slot_would_otherwise_keep_a_higher_previous_limit():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=5,
            house_load_w=700,
            previous_charge_limit_w=1800,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.charge_limit_w == 0
    assert decision.charge_limit_requested_w == 1143
    assert decision.charge_limit_previous_w == 1800
    assert decision.charge_limit_write_needed is True
    assert decision.charge_limit_write_delta_w == -1800
    assert decision.charge_limit_write_reason == "price_block_override"
    assert decision.charge_limit_basis == "forecast_planner|price_block"
    assert decision.mode == "price_support_discharge"


def test_planner_blocks_charge_when_expensive_slot_has_only_marginal_surplus():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=4.8,
            house_load_w=700,
            previous_charge_limit_w=300,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.charge_limit_w == 0
    assert decision.charge_limit_requested_w == 1158
    assert decision.charge_limit_previous_w == 300
    assert decision.charge_limit_write_needed is True
    assert decision.charge_limit_write_delta_w == -300
    assert decision.charge_limit_write_reason == "price_block_override"
    assert decision.charge_limit_basis == "forecast_planner|price_block"
    assert decision.mode == "price_support_discharge"


def test_planner_refuses_price_strategy_without_valid_slots():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=[],
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=4,
            house_load_w=900,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.mode == "safe_fallback"
    assert decision.write_allowed is False


def test_planner_waits_for_all_sources_before_writing():
    decision = plan_battery_policy(
        PlannerInputs(
            now=datetime.fromisoformat("2026-05-25T10:35:00+02:00"),
            price_slots=_slots(),
            battery_soc_percent=45,
            pv_forecast_remaining_kwh=None,
            house_load_w=900,
            export_limit_w=7000,
            default_discharge_limit_w=2800,
            min_soc_percent=15,
        )
    )

    assert decision.discharge_limit_w == 2800
    assert decision.mode == "waiting_for_sources"
    assert decision.write_allowed is False
