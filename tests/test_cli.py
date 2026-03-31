"""Tests for the CLI."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kotilaitteet.cli import main
from kotilaitteet.models import Device


def _db(tmp_path: Path) -> str:
    return str(tmp_path / "devices.json")


def _add_device(tmp_path: Path, name: str = "Heater", mac: str = "aa:bb:cc:dd:ee:01") -> int:
    return main([
        "--db", _db(tmp_path),
        "add",
        "--name", name,
        "--ip", "192.168.1.10",
        "--mac", mac,
        "--type", "heater",
    ])


class TestCliAdd:
    def test_add_device(self, tmp_path: Path, capsys):
        rc = _add_device(tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Heater" in out

    def test_add_persisted(self, tmp_path: Path):
        _add_device(tmp_path)
        db_path = Path(_db(tmp_path))
        data = json.loads(db_path.read_text())
        assert len(data) == 1
        assert data[0]["name"] == "Heater"


class TestCliList:
    def test_empty_list(self, tmp_path: Path, capsys):
        rc = main(["--db", _db(tmp_path), "list"])
        assert rc == 0

    def test_lists_device(self, tmp_path: Path, capsys):
        _add_device(tmp_path)
        rc = main(["--db", _db(tmp_path), "list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Heater" in out


class TestCliRemove:
    def test_remove_existing(self, tmp_path: Path, capsys):
        _add_device(tmp_path, mac="aa:bb:cc:dd:ee:01")
        rc = main(["--db", _db(tmp_path), "remove", "--mac", "aa:bb:cc:dd:ee:01"])
        assert rc == 0

    def test_remove_nonexistent(self, tmp_path: Path):
        rc = main(["--db", _db(tmp_path), "remove", "--mac", "00:00:00:00:00:00"])
        assert rc == 1


class TestCliOnOff:
    def test_turn_on(self, tmp_path: Path, capsys):
        _add_device(tmp_path, mac="aa:bb:cc:dd:ee:01")
        rc = main(["--db", _db(tmp_path), "on", "--mac", "aa:bb:cc:dd:ee:01"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "ON" in out

    def test_turn_off(self, tmp_path: Path, capsys):
        _add_device(tmp_path, mac="aa:bb:cc:dd:ee:01")
        main(["--db", _db(tmp_path), "on", "--mac", "aa:bb:cc:dd:ee:01"])
        rc = main(["--db", _db(tmp_path), "off", "--mac", "aa:bb:cc:dd:ee:01"])
        assert rc == 0

    def test_on_by_name(self, tmp_path: Path, capsys):
        _add_device(tmp_path, name="Boiler", mac="aa:bb:cc:dd:ee:01")
        rc = main(["--db", _db(tmp_path), "on", "--name", "Boiler"])
        assert rc == 0

    def test_on_unknown_mac(self, tmp_path: Path):
        rc = main(["--db", _db(tmp_path), "on", "--mac", "00:00:00:00:00:00"])
        assert rc == 1


class TestCliPrices:
    def _fake_prices(self):
        import datetime
        from zoneinfo import ZoneInfo
        from kotilaitteet.electricity import PricePoint
        tz = ZoneInfo("Europe/Helsinki")
        today = datetime.date.today()
        return [
            PricePoint(
                datetime.datetime(today.year, today.month, today.day, h, 0, 0, tzinfo=tz),
                round(2.0 + h * 0.5, 2),
            )
            for h in range(24)
        ]

    def test_prices_output(self, tmp_path: Path, capsys):
        with patch("kotilaitteet.cli.fetch_prices", return_value=self._fake_prices()):
            rc = main(["--db", _db(tmp_path), "prices"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "c/kWh" in out

    def test_prices_with_cheapest(self, tmp_path: Path, capsys):
        with patch("kotilaitteet.cli.fetch_prices", return_value=self._fake_prices()):
            rc = main(["--db", _db(tmp_path), "prices", "--cheapest", "3"])
        assert rc == 0

    def test_prices_api_error(self, tmp_path: Path, capsys):
        with patch("kotilaitteet.cli.fetch_prices", side_effect=RuntimeError("no internet")):
            rc = main(["--db", _db(tmp_path), "prices"])
        assert rc == 1


class TestCliSchedule:
    def _fake_prices(self):
        import datetime
        from zoneinfo import ZoneInfo
        from kotilaitteet.electricity import PricePoint
        tz = ZoneInfo("Europe/Helsinki")
        today = datetime.date.today()
        return [
            PricePoint(
                datetime.datetime(today.year, today.month, today.day, h, 0, 0, tzinfo=tz),
                round(2.0 + h * 0.5, 2),
            )
            for h in range(24)
        ]

    def test_schedule_no_devices(self, tmp_path: Path, capsys):
        with patch("kotilaitteet.cli.fetch_prices", return_value=self._fake_prices()):
            rc = main(["--db", _db(tmp_path), "schedule"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "No price-controlled devices" in out

    def test_schedule_with_device(self, tmp_path: Path, capsys):
        _add_device(tmp_path, mac="aa:bb:cc:dd:ee:01")
        main([
            "--db", _db(tmp_path), "price-control",
            "--enable", "--mac", "aa:bb:cc:dd:ee:01", "--hours", "3",
        ])
        with patch("kotilaitteet.cli.fetch_prices", return_value=self._fake_prices()):
            rc = main(["--db", _db(tmp_path), "schedule"])
        assert rc == 0

    def test_schedule_api_error(self, tmp_path: Path, capsys):
        with patch("kotilaitteet.cli.fetch_prices", side_effect=RuntimeError("fail")):
            rc = main(["--db", _db(tmp_path), "schedule"])
        assert rc == 1


class TestCliScan:
    def test_scan_no_devices(self, tmp_path: Path, capsys):
        with patch("kotilaitteet.cli.scan_network", return_value=[]):
            rc = main(["--db", _db(tmp_path), "scan"])
        assert rc == 0

    def test_scan_with_devices(self, tmp_path: Path, capsys):
        from kotilaitteet.models import NetworkDevice
        found = [
            NetworkDevice(
                ip_address="192.168.1.5",
                mac_address="11:22:33:44:55:66",
                hostname="my-device",
                vendor="TP-Link",
            )
        ]
        with patch("kotilaitteet.cli.scan_network", return_value=found):
            rc = main(["--db", _db(tmp_path), "scan"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "192.168.1.5" in out
        assert "TP-Link" in out
