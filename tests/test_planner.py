from datetime import datetime

from custom_components.gen24_energy_control.planner import PlannerInputs, plan_battery_policy
from custom_components.gen24_energy_control.price_slots import parse_price_slots


def _slots():
    return parse_price_slots([
        {"start_time": "2026-05-25T10:00:00+02:00", "end_time": "2026-05-25T10:15:00+02:00", "price_per_kwh": 0.12},
        {"start_time": "2026-05-25T10:15:00+02:00", "end_time": "2026-05-25T10:30:00+02:00", "price_per_kwh": 0.18},
        {"start_time": "2026-05-25T10:30:00+02:00", "end_time": "2026-05-25T10:45:00+02:00", "price_per_kwh": 0.42},
    ])


def test_planner_blocks_discharge_but_keeps_wiggal_style_small_charge_limit_when_price_is_cheap_and_pv_forecast_is_high():
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
    assert decision.charge_limit_w == 300
    assert decision.charge_limit_basis == "forecast_planner_floor"
    assert decision.mode == "hold_for_cheap_pv_window"
    assert "forecast-based" in decision.reason


def test_planner_allows_default_discharge_when_current_price_is_expensive():
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
    assert "expensive" in decision.reason


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
