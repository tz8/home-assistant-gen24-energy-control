from custom_components.gen24_energy_control.solar_forecast import remaining_today_kwh


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
