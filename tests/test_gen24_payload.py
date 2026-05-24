from custom_components.gen24_energy_control.gen24_payload import build_timeofuse_payload
from custom_components.gen24_energy_control.planner import BatteryPolicyDecision


def test_build_timeofuse_payload_includes_charge_and_discharge_entries():
    decision = BatteryPolicyDecision(
        mode="price_support_discharge",
        reason="expensive",
        discharge_limit_w=2800,
        charge_limit_w=-3000,
        write_allowed=True,
        price_source_valid=True,
        solar_forecast_valid=True,
    )

    payload = build_timeofuse_payload(decision)

    assert payload == {
        "timeofuse": [
            {
                "Active": True,
                "Power": -3000,
                "ScheduleType": "CHARGE_MAX",
                "TimeTable": {"Start": "00:00", "End": "23:59"},
                "Weekdays": {"Mon": True, "Tue": True, "Wed": True, "Thu": True, "Fri": True, "Sat": True, "Sun": True},
            },
            {
                "Active": True,
                "Power": 2800,
                "ScheduleType": "DISCHARGE_MAX",
                "TimeTable": {"Start": "00:00", "End": "23:59"},
                "Weekdays": {"Mon": True, "Tue": True, "Wed": True, "Thu": True, "Fri": True, "Sat": True, "Sun": True},
            },
        ]
    }


def test_build_timeofuse_payload_refuses_non_writable_decision():
    decision = BatteryPolicyDecision(
        mode="safe_fallback",
        reason="missing prices",
        discharge_limit_w=2800,
        charge_limit_w=None,
        write_allowed=False,
        price_source_valid=False,
        solar_forecast_valid=False,
    )

    assert build_timeofuse_payload(decision) == {"timeofuse": []}
