"""Tests for electricity.py – uses mocked HTTP responses."""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
from zoneinfo import ZoneInfo

from kotilaitteet.electricity import (
    PricePoint,
    cheapest_hours,
    fetch_prices,
    get_current_price,
    price_summary,
    prices_for_date,
)

_FINLAND_TZ = ZoneInfo("Europe/Helsinki")

# ---------------------------------------------------------------------------
# Sample API response fixture
# ---------------------------------------------------------------------------

def _make_api_response(base_date: str = "2024-01-15") -> list:
    """Return a list of 24 hourly price items (mimics spot-hinta.fi format)."""
    items = []
    for hour in range(24):
        items.append(
            {
                "DateTime": f"{base_date}T{hour:02d}:00:00+02:00",
                "PriceWithTax": round(2.0 + hour * 0.5, 2),
            }
        )
    return items


def _make_price_points(base_date: datetime.date | None = None) -> list[PricePoint]:
    if base_date is None:
        base_date = datetime.date(2024, 1, 15)
    points = []
    for hour in range(24):
        dt = datetime.datetime(
            base_date.year, base_date.month, base_date.day, hour, 0, 0,
            tzinfo=_FINLAND_TZ,
        )
        points.append(PricePoint(hour_start=dt, price_cents_kwh=round(2.0 + hour * 0.5, 2)))
    return points


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchPrices:
    def test_parses_api_response(self):
        with patch("kotilaitteet.electricity._http_get") as mock_get:
            mock_get.return_value = _make_api_response("2024-01-15")
            prices = fetch_prices()
        assert len(prices) == 24
        assert all(isinstance(p, PricePoint) for p in prices)

    def test_prices_sorted_by_time(self):
        with patch("kotilaitteet.electricity._http_get") as mock_get:
            data = _make_api_response("2024-01-15")
            # Shuffle to verify sorting
            import random
            random.shuffle(data)
            mock_get.return_value = data
            prices = fetch_prices()
        hours = [p.hour_start.hour for p in prices]
        assert hours == sorted(hours)

    def test_raises_on_network_error(self):
        with patch("kotilaitteet.electricity._http_get") as mock_get:
            mock_get.side_effect = Exception("connection refused")
            with pytest.raises(RuntimeError, match="Unable to fetch"):
                fetch_prices()

    def test_skips_malformed_entries(self):
        with patch("kotilaitteet.electricity._http_get") as mock_get:
            mock_get.return_value = [
                {"DateTime": "2024-01-15T00:00:00+02:00", "PriceWithTax": 3.5},
                {"DateTime": None, "PriceWithTax": None},  # malformed
                {"DateTime": "2024-01-15T01:00:00+02:00", "PriceWithTax": 4.0},
            ]
            prices = fetch_prices()
        assert len(prices) == 2


class TestPricesForDate:
    def test_filters_by_date(self):
        target = datetime.date(2024, 1, 15)
        prices = _make_price_points(target)
        # Add an extra point for a different date
        other_date = datetime.date(2024, 1, 16)
        extra = PricePoint(
            hour_start=datetime.datetime(2024, 1, 16, 0, 0, 0, tzinfo=_FINLAND_TZ),
            price_cents_kwh=5.0,
        )
        prices.append(extra)
        filtered = prices_for_date(target, prices)
        assert len(filtered) == 24
        assert all(p.hour_start.date() == target for p in filtered)


class TestCheapestHours:
    def test_returns_n_cheapest(self):
        prices = _make_price_points(datetime.date(2024, 1, 15))
        cheap = cheapest_hours(3, prices, datetime.date(2024, 1, 15))
        assert len(cheap) == 3
        # The cheapest should be hours 0, 1, 2 (prices 2.0, 2.5, 3.0)
        assert cheap[0].price_cents_kwh <= cheap[1].price_cents_kwh <= cheap[2].price_cents_kwh

    def test_n_larger_than_available(self):
        prices = _make_price_points(datetime.date(2024, 1, 15))
        cheap = cheapest_hours(100, prices, datetime.date(2024, 1, 15))
        assert len(cheap) == 24  # capped at available hours

    def test_empty_when_no_data(self):
        cheap = cheapest_hours(3, [], datetime.date(2024, 1, 15))
        assert cheap == []


class TestPriceSummary:
    def test_basic_stats(self):
        prices = [
            PricePoint(
                datetime.datetime(2024, 1, 15, h, 0, tzinfo=_FINLAND_TZ),
                float(h + 1),
            )
            for h in range(4)
        ]  # 1.0, 2.0, 3.0, 4.0
        summary = price_summary(prices)
        assert summary["min"] == 1.0
        assert summary["max"] == 4.0
        assert summary["avg"] == 2.5

    def test_empty_list(self):
        s = price_summary([])
        assert s == {"min": 0.0, "max": 0.0, "avg": 0.0}


class TestGetCurrentPrice:
    def test_returns_current_hour_price(self):
        now = datetime.datetime.now(tz=_FINLAND_TZ)
        prices = _make_price_points(now.date())
        result = get_current_price(prices)
        assert result is not None
        assert result.hour_start.hour == now.hour

    def test_returns_none_when_no_data(self):
        result = get_current_price([])
        assert result is None
