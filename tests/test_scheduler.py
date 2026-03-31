"""Tests for scheduler.py"""

import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from zoneinfo import ZoneInfo

from kotilaitteet.device_manager import DeviceManager
from kotilaitteet.electricity import PricePoint
from kotilaitteet.models import Device
from kotilaitteet.scheduler import build_daily_schedule, current_recommendations

_FINLAND_TZ = ZoneInfo("Europe/Helsinki")
_TARGET_DATE = datetime.date(2024, 1, 15)


def _make_price_points(base_date: datetime.date = _TARGET_DATE) -> list[PricePoint]:
    points = []
    for hour in range(24):
        dt = datetime.datetime(
            base_date.year, base_date.month, base_date.day, hour, 0, 0,
            tzinfo=_FINLAND_TZ,
        )
        points.append(PricePoint(hour_start=dt, price_cents_kwh=round(2.0 + hour * 0.5, 2)))
    return points


def _setup_manager(tmp_path: Path, price_controlled: bool = True) -> DeviceManager:
    mgr = DeviceManager(db_path=tmp_path / "devices.json")
    d = Device(
        name="Boiler",
        ip_address="192.168.1.10",
        mac_address="aa:bb:cc:dd:ee:01",
        price_controlled=price_controlled,
        min_daily_hours=3,
    )
    mgr.add_device(d)
    return mgr


class TestBuildDailySchedule:
    def test_no_price_controlled_devices(self, tmp_path: Path):
        mgr = _setup_manager(tmp_path, price_controlled=False)
        prices = _make_price_points()
        schedule = build_daily_schedule(mgr, _TARGET_DATE, prices)
        assert schedule == {}

    def test_cheapest_hours_are_on(self, tmp_path: Path):
        mgr = _setup_manager(tmp_path)
        prices = _make_price_points()
        schedule = build_daily_schedule(mgr, _TARGET_DATE, prices)
        mac = "aa:bb:cc:dd:ee:01"
        assert mac in schedule
        entries = schedule[mac]
        assert len(entries) == 24

        on_hours = {e.hour for e in entries if e.recommended_state}
        # With min_daily_hours=3, the 3 cheapest hours (0, 1, 2) should be on
        assert on_hours == {0, 1, 2}

    def test_price_threshold_turns_off(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        d = Device(
            name="AirCon",
            ip_address="192.168.1.11",
            mac_address="aa:bb:cc:dd:ee:02",
            price_controlled=True,
            min_daily_hours=5,
            price_threshold=5.0,  # threshold of 5 c/kWh
        )
        mgr.add_device(d)
        prices = _make_price_points()  # prices from 2.0 to 13.5 c/kWh
        schedule = build_daily_schedule(mgr, _TARGET_DATE, prices)
        mac = "aa:bb:cc:dd:ee:02"
        entries = {e.hour: e for e in schedule[mac]}

        # Hour 6: price = 2.0 + 6*0.5 = 5.0 (exactly at threshold, <= threshold means OK)
        # Hour 7: price = 2.0 + 7*0.5 = 5.5 > threshold → off
        assert entries[7].recommended_state is False
        assert "exceeds threshold" in entries[7].reason

    def test_no_prices_for_date_returns_empty(self, tmp_path: Path):
        mgr = _setup_manager(tmp_path)
        prices = _make_price_points(datetime.date(2024, 1, 16))  # different date
        schedule = build_daily_schedule(mgr, _TARGET_DATE, prices)
        mac = "aa:bb:cc:dd:ee:01"
        assert schedule.get(mac, []) == []


class TestCurrentRecommendations:
    def test_returns_recommendation_for_current_hour(self, tmp_path: Path):
        mgr = _setup_manager(tmp_path)
        prices = _make_price_points(datetime.date.today())
        recs = current_recommendations(mgr, prices)
        assert len(recs) == 1
        rec = recs[0]
        assert rec["device"].name == "Boiler"
        assert isinstance(rec["recommended_state"], bool)
        assert isinstance(rec["price"], float)

    def test_no_recommendations_when_no_price_controlled(self, tmp_path: Path):
        mgr = _setup_manager(tmp_path, price_controlled=False)
        prices = _make_price_points(datetime.date.today())
        recs = current_recommendations(mgr, prices)
        assert recs == []
