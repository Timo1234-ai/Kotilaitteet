"""
Fetches Finnish spot electricity prices from spot-hinta.fi.

The public REST endpoint returns hourly prices in €/MWh.
We convert to snt/kWh (cents per kWh) which is the common Finnish unit.
"""
import logging
from datetime import datetime

import requests

SPOT_HINTA_URL = "https://api.spot-hinta.fi/TodayAndDayForward"
REQUEST_TIMEOUT = 10  # seconds

logger = logging.getLogger(__name__)


def fetch_prices() -> list[dict]:
    """
    Return a list of hourly price dicts sorted by DateTime:
        [{"hour": 14, "date": "2024-01-15", "price_mwh": 45.67,
          "price_kwh": 4.567, "rank": 3, "is_cheap": True}, ...]

    Falls back to an empty list on any network or parse error so that the
    application continues to work even when offline.
    """
    try:
        resp = requests.get(SPOT_HINTA_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch electricity prices: %s", exc)
        return []

    prices = []
    for entry in raw:
        try:
            dt_str = entry.get("DateTime") or entry.get("dateTime") or ""
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            price_mwh = float(entry.get("PriceWithTax", entry.get("price", 0)))
            prices.append({
                "datetime": dt.isoformat(),
                "date": dt.strftime("%Y-%m-%d"),
                "hour": dt.hour,
                "price_mwh": round(price_mwh, 4),
                "price_kwh": round(price_mwh / 10, 4),   # snt/kWh
            })
        except (KeyError, ValueError, TypeError) as exc:
            logger.debug("Skipping malformed price entry %s: %s", entry, exc)
            continue

    prices.sort(key=lambda x: x["datetime"])
    _annotate_cheapness(prices)
    return prices


def _annotate_cheapness(prices: list[dict]) -> None:
    """Mark the cheapest 1/3 of hours as cheap within each calendar day."""
    by_date: dict[str, list[dict]] = {}
    for p in prices:
        by_date.setdefault(p["date"], []).append(p)

    for day_prices in by_date.values():
        sorted_day = sorted(day_prices, key=lambda x: x["price_mwh"])
        cheap_count = max(1, len(sorted_day) // 3)
        cheap_set = {id(p) for p in sorted_day[:cheap_count]}
        for p in day_prices:
            p["is_cheap"] = id(p) in cheap_set

    # Add rank (1 = cheapest) within each day
    for day_prices in by_date.values():
        sorted_day = sorted(day_prices, key=lambda x: x["price_mwh"])
        rank_map = {id(p): i + 1 for i, p in enumerate(sorted_day)}
        for p in day_prices:
            p["rank"] = rank_map[id(p)]


def get_cheapest_hours(prices: list[dict], date: str | None = None, n: int = 8) -> list[int]:
    """Return the n cheapest hours (0-23) for a given date (default: today)."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    day_prices = [p for p in prices if p["date"] == target_date]
    if not day_prices:
        return []
    sorted_hours = sorted(day_prices, key=lambda x: x["price_mwh"])
    return [p["hour"] for p in sorted_hours[:n]]
