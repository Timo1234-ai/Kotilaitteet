"""Tests for device_manager.py"""

import json
import pytest
from pathlib import Path

from kotilaitteet.device_manager import DeviceManager
from kotilaitteet.models import Device


def _make_device(name: str = "TestDevice", mac: str = "aa:bb:cc:dd:ee:01") -> Device:
    return Device(name=name, ip_address="192.168.1.100", mac_address=mac)


class TestDeviceManager:
    def test_add_and_list(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        assert mgr.list_devices() == []
        d = _make_device()
        mgr.add_device(d)
        assert len(mgr.list_devices()) == 1

    def test_persistence(self, tmp_path: Path):
        db = tmp_path / "devices.json"
        mgr = DeviceManager(db_path=db)
        mgr.add_device(_make_device("Heater", "aa:bb:cc:dd:ee:01"))
        mgr.add_device(_make_device("Washer", "aa:bb:cc:dd:ee:02"))

        # Reload from disk
        mgr2 = DeviceManager(db_path=db)
        devices = {d.name for d in mgr2.list_devices()}
        assert devices == {"Heater", "Washer"}

    def test_remove_device(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        mac = "aa:bb:cc:dd:ee:01"
        mgr.add_device(_make_device(mac=mac))
        removed = mgr.remove_device(mac)
        assert removed is True
        assert mgr.list_devices() == []

    def test_remove_nonexistent(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        assert mgr.remove_device("00:00:00:00:00:00") is False

    def test_get_device(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        mac = "aa:bb:cc:dd:ee:01"
        mgr.add_device(_make_device("Lamp", mac))
        d = mgr.get_device(mac)
        assert d is not None
        assert d.name == "Lamp"

    def test_get_device_by_name(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        mgr.add_device(_make_device("Smart Heater", "aa:bb:cc:dd:ee:01"))
        d = mgr.get_device_by_name("smart heater")  # case-insensitive
        assert d is not None
        assert d.mac_address == "aa:bb:cc:dd:ee:01"

    def test_turn_on_off(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        mac = "aa:bb:cc:dd:ee:01"
        mgr.add_device(_make_device(mac=mac))
        assert mgr.get_device(mac).is_on is False
        assert mgr.turn_on(mac) is True
        assert mgr.get_device(mac).is_on is True
        assert mgr.turn_off(mac) is True
        assert mgr.get_device(mac).is_on is False

    def test_toggle(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        mac = "aa:bb:cc:dd:ee:01"
        mgr.add_device(_make_device(mac=mac))
        new_state = mgr.toggle(mac)
        assert new_state is True
        new_state = mgr.toggle(mac)
        assert new_state is False

    def test_toggle_nonexistent(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        assert mgr.toggle("00:00:00:00:00:00") is None

    def test_set_price_control(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        mac = "aa:bb:cc:dd:ee:01"
        mgr.add_device(_make_device(mac=mac))
        mgr.set_price_control(mac, enabled=True, min_daily_hours=3, price_threshold=12.5)
        d = mgr.get_device(mac)
        assert d.price_controlled is True
        assert d.min_daily_hours == 3
        assert d.price_threshold == 12.5

    def test_set_price_control_nonexistent(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        result = mgr.set_price_control("00:00:00:00:00:00", enabled=True)
        assert result is False

    def test_find_by_ip(self, tmp_path: Path):
        mgr = DeviceManager(db_path=tmp_path / "devices.json")
        mac = "aa:bb:cc:dd:ee:01"
        d = Device(name="Router", ip_address="192.168.1.1", mac_address=mac)
        mgr.add_device(d)
        found = mgr.find_by_ip("192.168.1.1")
        assert found is not None
        assert found.mac_address == mac

    def test_corrupt_db_recovers(self, tmp_path: Path):
        db = tmp_path / "devices.json"
        db.write_text("NOT VALID JSON")
        mgr = DeviceManager(db_path=db)
        assert mgr.list_devices() == []
