"""Smart scheduling: recommend cheapest hours for price-controlled devices."""

from __future__ import annotations

import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from .device_manager import DeviceManager
from .electricity import PricePoint, cheapest_hours, fetch_prices, price_summary
from .models import Device, ScheduleEntry

_FINLAND_TZ = ZoneInfo("Europe/Helsinki")


def _make_schedule_for_device(
    device: Device,
    prices: List[PricePoint],
    target_date: datetime.date,
) -> List[ScheduleEntry]:
    """Build hour-by-hour schedule entries for a single device."""
    entries: List[ScheduleEntry] = []

    # Build a map from hour -> price for easy lookup
    hour_price: Dict[int, float] = {
        p.hour_start.hour: p.price_cents_kwh
        for p in prices
        if p.hour_start.date() == target_date
    }

    if not hour_price:
        return entries

    # Determine which hours the device should be on
    on_hours: set[int] = set()

    if device.min_daily_hours > 0:
        cheap = cheapest_hours(device.min_daily_hours, prices, target_date)
        on_hours = {p.hour_start.hour for p in cheap}

    # Also apply the price threshold: device is off when price exceeds threshold
    threshold = device.price_threshold

    for hour in range(24):
        price = hour_price.get(hour)
        if price is None:
            continue  # No price data for this hour

        if threshold is not None and price > threshold:
            state = False
            reason = (
                f"Price {price:.2f} c/kWh exceeds threshold {threshold:.2f} c/kWh"
            )
        elif hour in on_hours:
            state = True
            reason = f"Among {device.min_daily_hours} cheapest hours ({price:.2f} c/kWh)"
        else:
            state = False
            reason = f"Outside cheapest window ({price:.2f} c/kWh)"

        entries.append(
            ScheduleEntry(
                device_mac=device.mac_address,
                hour=hour,
                date=target_date.isoformat(),
                recommended_state=state,
                price_cents_per_kwh=price,
                reason=reason,
            )
        )
    return entries


def build_daily_schedule(
    manager: DeviceManager,
    target_date: datetime.date | None = None,
    prices: List[PricePoint] | None = None,
) -> Dict[str, List[ScheduleEntry]]:
    """Generate a full-day schedule for all price-controlled devices.

    Args:
        manager: :class:`DeviceManager` instance.
        target_date: Date to schedule; defaults to today.
        prices: Pre-fetched prices; fetched automatically when *None*.

    Returns:
        Dict mapping device MAC address to a list of :class:`ScheduleEntry`.
    """
    if target_date is None:
        target_date = datetime.date.today()
    if prices is None:
        prices = fetch_prices()

    schedule: Dict[str, List[ScheduleEntry]] = {}
    for device in manager.list_devices():
        if not device.price_controlled:
            continue
        entries = _make_schedule_for_device(device, prices, target_date)
        if entries:
            schedule[device.mac_address] = entries
    return schedule


def current_recommendations(
    manager: DeviceManager,
    prices: List[PricePoint] | None = None,
) -> List[dict]:
    """Return a list of recommendations for the current hour.

    Each item is a dict with keys: device, recommended_state, reason, price.
    """
    if prices is None:
        prices = fetch_prices()

    now = datetime.datetime.now(tz=_FINLAND_TZ)
    today = now.date()
    current_hour = now.hour

    schedule = build_daily_schedule(manager, today, prices)
    recommendations: List[dict] = []

    for mac, entries in schedule.items():
        device = manager.get_device(mac)
        if device is None:
            continue
        for entry in entries:
            if entry.hour == current_hour:
                recommendations.append(
                    {
                        "device": device,
                        "recommended_state": entry.recommended_state,
                        "reason": entry.reason,
                        "price": entry.price_cents_per_kwh,
                    }
                )
                break

    return recommendations
