"""Price-slot parsing helpers for GEN24 Energy Control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class PriceSlot:
    """One electricity-price slot."""

    start: datetime
    end: datetime
    price_per_kwh: float

    @property
    def duration_minutes(self) -> float:
        """Return slot duration in minutes."""
        return (self.end - self.start).total_seconds() / 60


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"Expected ISO datetime string, got {value!r}")
    # Home Assistant integrations sometimes use Z suffix.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_price_slots(raw_slots: Iterable[dict[str, Any]] | None) -> list[PriceSlot]:
    """Parse ha_epex_spot-style data into sorted price slots.

    Expected input shape::

        [{"start_time": "...", "end_time": "...", "price_per_kwh": 0.23}]

    Invalid or incomplete entries are skipped. The caller can decide whether the
    resulting list is sufficiently complete for automation.
    """
    if not raw_slots:
        return []

    slots: list[PriceSlot] = []
    for entry in raw_slots:
        if not isinstance(entry, dict):
            continue
        try:
            start = _parse_datetime(entry.get("start_time") or entry.get("start"))
            end = _parse_datetime(entry.get("end_time") or entry.get("end"))
            price = float(entry.get("price_per_kwh"))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        slots.append(PriceSlot(start=start, end=end, price_per_kwh=price))

    return sorted(slots, key=lambda slot: slot.start)


def current_slot(slots: Iterable[PriceSlot], now: datetime) -> PriceSlot | None:
    """Return the slot covering ``now``."""
    for slot in slots:
        if slot.start <= now < slot.end:
            return slot
    return None


def future_slots(slots: Iterable[PriceSlot], now: datetime) -> list[PriceSlot]:
    """Return slots that have not ended yet."""
    return [slot for slot in slots if slot.end > now]


def cheapest_slots(slots: Iterable[PriceSlot], now: datetime, limit: int) -> list[PriceSlot]:
    """Return the cheapest future slots sorted by price."""
    return sorted(future_slots(slots, now), key=lambda slot: (slot.price_per_kwh, slot.start))[:limit]


def price_percentile(slots: Iterable[PriceSlot], current: PriceSlot) -> float:
    """Return current slot's price percentile in the supplied slot set.

    ``0.0`` means cheapest, ``1.0`` means most expensive. Equal prices are
    treated as the same rank.
    """
    prices = sorted({slot.price_per_kwh for slot in slots})
    if not prices:
        return 0.5
    if len(prices) == 1:
        return 0.5
    rank = prices.index(current.price_per_kwh)
    return rank / (len(prices) - 1)
