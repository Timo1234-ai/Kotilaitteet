"""Tests for models.py"""

import pytest
from kotilaitteet.models import Device, NetworkDevice, ScheduleEntry


class TestDevice:
    def test_default_state(self):
        d = Device(name="Boiler", ip_address="192.168.1.10", mac_address="aa:bb:cc:dd:ee:ff")
        assert d.is_on is False
        assert d.price_controlled is False
        assert d.device_type == "unknown"
        assert d.min_daily_hours == 0
        assert d.price_threshold is None

    def test_to_dict_round_trip(self):
        d = Device(
            name="Heater",
            ip_address="10.0.0.5",
            mac_address="01:02:03:04:05:06",
            device_type="heater",
            is_on=True,
            price_controlled=True,
            min_daily_hours=4,
            price_threshold=10.0,
            notes="Living room",
        )
        data = d.to_dict()
        restored = Device.from_dict(data)
        assert restored.name == d.name
        assert restored.ip_address == d.ip_address
        assert restored.mac_address == d.mac_address
        assert restored.is_on is True
        assert restored.price_controlled is True
        assert restored.min_daily_hours == 4
        assert restored.price_threshold == 10.0
        assert restored.notes == "Living room"

    def test_from_dict_ignores_extra_keys(self):
        data = {
            "name": "Lamp",
            "ip_address": "192.168.1.1",
            "mac_address": "ff:ee:dd:cc:bb:aa",
            "device_type": "lamp",
            "is_on": False,
            "price_controlled": False,
            "min_daily_hours": 0,
            "price_threshold": None,
            "added_at": "2024-01-01T00:00:00",
            "notes": "",
            "extra_unknown_field": "should be ignored",
        }
        d = Device.from_dict({k: v for k, v in data.items() if k != "extra_unknown_field"})
        assert d.name == "Lamp"


class TestNetworkDevice:
    def test_defaults(self):
        nd = NetworkDevice(ip_address="192.168.1.2", mac_address="aa:bb:cc:dd:ee:01")
        assert nd.hostname == ""
        assert nd.vendor == ""

    def test_to_dict(self):
        nd = NetworkDevice(
            ip_address="192.168.1.3",
            mac_address="aa:bb:cc:dd:ee:02",
            hostname="my-device",
            vendor="TP-Link",
        )
        d = nd.to_dict()
        assert d["ip_address"] == "192.168.1.3"
        assert d["vendor"] == "TP-Link"


class TestScheduleEntry:
    def test_round_trip(self):
        entry = ScheduleEntry(
            device_mac="aa:bb:cc:dd:ee:ff",
            hour=14,
            date="2024-01-15",
            recommended_state=True,
            price_cents_per_kwh=5.5,
            reason="cheap hour",
        )
        d = entry.to_dict()
        restored = ScheduleEntry.from_dict(d)
        assert restored.hour == 14
        assert restored.recommended_state is True
        assert restored.price_cents_per_kwh == 5.5
