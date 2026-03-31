"""Fetch and analyse Finnish electricity spot prices from spot-hinta.fi."""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

try:
    import urllib.request
    import json as _json

    def _http_get(url: str, timeout: int = 10) -> dict | list:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _json.loads(resp.read().decode())

except ImportError:  # pragma: no cover
    def _http_get(url: str, timeout: int = 10) -> dict | list:  # type: ignore[misc]
        raise RuntimeError("HTTP not available")


_SPOT_HINTA_URL = "https://api.spot-hinta.fi/TodayAndDayForward"
_FINLAND_TZ = ZoneInfo("Europe/Helsinki")


class PricePoint:
    """A single hourly price point."""

    __slots__ = ("hour_start", "price_cents_kwh")

    def __init__(self, hour_start: datetime.datetime, price_cents_kwh: float) -> None:
        self.hour_start = hour_start
        self.price_cents_kwh = price_cents_kwh

    def __repr__(self) -> str:
        ts = self.hour_start.strftime("%Y-%m-%d %H:%M")
        return f"PricePoint({ts}, {self.price_cents_kwh:.2f} c/kWh)"


def fetch_prices() -> List[PricePoint]:
    """Return today's (and tomorrow's if available) hourly electricity prices.

    Prices are fetched from the public spot-hinta.fi API which provides
    Finnish electricity spot prices in c/kWh (including VAT).

    Returns:
        List of :class:`PricePoint` sorted by time.

    Raises:
        RuntimeError: If the API is unreachable or returns unexpected data.
    """
    try:
        data = _http_get(_SPOT_HINTA_URL)
    except Exception as exc:
        raise RuntimeError(f"Unable to fetch electricity prices: {exc}") from exc

    points: List[PricePoint] = []
    for item in data:
        try:
            # API returns ISO timestamp like "2024-01-15T00:00:00+02:00"
            dt_str = item.get("DateTime") or item.get("dateTime") or item.get("date")
            price_raw = item.get("PriceWithTax") or item.get("price") or item.get("value")
            if dt_str is None or price_raw is None:
                continue
            dt = datetime.datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_FINLAND_TZ)
            else:
                dt = dt.astimezone(_FINLAND_TZ)
            price = float(price_raw)
            points.append(PricePoint(hour_start=dt, price_cents_kwh=price))
        except (KeyError, ValueError, TypeError):
            continue

    points.sort(key=lambda p: p.hour_start)
    return points


def get_current_price(prices: List[PricePoint] | None = None) -> Optional[PricePoint]:
    """Return the price point for the current hour."""
    if prices is None:
        prices = fetch_prices()
    now = datetime.datetime.now(tz=_FINLAND_TZ)
    for p in prices:
        if (
            p.hour_start.date() == now.date()
            and p.hour_start.hour == now.hour
        ):
            return p
    return None


def prices_for_date(
    target_date: datetime.date,
    prices: List[PricePoint] | None = None,
) -> List[PricePoint]:
    """Return price points for a specific date."""
    if prices is None:
        prices = fetch_prices()
    return [p for p in prices if p.hour_start.date() == target_date]


def cheapest_hours(
    n: int,
    prices: List[PricePoint] | None = None,
    target_date: datetime.date | None = None,
) -> List[PricePoint]:
    """Return the *n* cheapest hourly price points for a given date.

    Args:
        n: Number of cheapest hours to return.
        prices: Pre-fetched price list; fetched automatically when *None*.
        target_date: Date to filter by; defaults to today.

    Returns:
        List of :class:`PricePoint` sorted by price (cheapest first).
    """
    if target_date is None:
        target_date = datetime.date.today()
    day_prices = prices_for_date(target_date, prices)
    return sorted(day_prices, key=lambda p: p.price_cents_kwh)[:n]


def price_summary(prices: List[PricePoint]) -> Dict[str, float]:
    """Return min / max / average prices from a list of price points."""
    if not prices:
        return {"min": 0.0, "max": 0.0, "avg": 0.0}
    values = [p.price_cents_kwh for p in prices]
    return {
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
    }
