from datetime import datetime

from custom_components.gen24_energy_control.price_slots import parse_price_slots, current_slot, cheapest_slots


def test_parse_price_slots_accepts_epex_data_attribute_shape():
    raw = [
        {
            "start_time": "2026-05-25T00:00:00+02:00",
            "end_time": "2026-05-25T00:15:00+02:00",
            "price_per_kwh": 0.3479,
        },
        {
            "start_time": "2026-05-25T00:15:00+02:00",
            "end_time": "2026-05-25T00:30:00+02:00",
            "price_per_kwh": "0.3406",
        },
    ]

    slots = parse_price_slots(raw)

    assert len(slots) == 2
    assert slots[0].price_per_kwh == 0.3479
    assert slots[0].start.isoformat() == "2026-05-25T00:00:00+02:00"
    assert slots[1].price_per_kwh == 0.3406


def test_current_slot_returns_slot_covering_timestamp():
    slots = parse_price_slots([
        {"start_time": "2026-05-25T00:00:00+02:00", "end_time": "2026-05-25T00:15:00+02:00", "price_per_kwh": 0.30},
        {"start_time": "2026-05-25T00:15:00+02:00", "end_time": "2026-05-25T00:30:00+02:00", "price_per_kwh": 0.20},
    ])

    slot = current_slot(slots, datetime.fromisoformat("2026-05-25T00:16:00+02:00"))

    assert slot is not None
    assert slot.price_per_kwh == 0.20


def test_cheapest_slots_returns_sorted_future_slots_limited_by_count():
    slots = parse_price_slots([
        {"start_time": "2026-05-25T00:00:00+02:00", "end_time": "2026-05-25T00:15:00+02:00", "price_per_kwh": 0.40},
        {"start_time": "2026-05-25T00:15:00+02:00", "end_time": "2026-05-25T00:30:00+02:00", "price_per_kwh": 0.10},
        {"start_time": "2026-05-25T00:30:00+02:00", "end_time": "2026-05-25T00:45:00+02:00", "price_per_kwh": 0.20},
    ])

    cheapest = cheapest_slots(slots, datetime.fromisoformat("2026-05-25T00:01:00+02:00"), limit=2)

    assert [slot.price_per_kwh for slot in cheapest] == [0.10, 0.20]
