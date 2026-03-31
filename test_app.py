"""
Tests for the Kotilaitteet application.
Run with: pytest test_app.py -v
"""
import json
import os
import sys
import tempfile

import pytest

# Make sure we can import from the project root
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture()
def tmp_data_file(monkeypatch, tmp_path):
    """Redirect data storage to a temp file so tests are isolated."""
    import models as m
    data_file = tmp_path / "data.json"
    monkeypatch.setattr(m, "DATA_FILE", str(data_file))
    return data_file


@pytest.fixture()
def client(tmp_data_file):
    """Return a Flask test client with isolated data storage."""
    import app as application
    application.app.config["TESTING"] = True
    with application.app.test_client() as c:
        yield c


# ─── Model tests ──────────────────────────────────────────────────────────────

class TestModels:
    def test_get_devices_returns_defaults(self, tmp_data_file):
        import models as m
        devices = m.get_devices()
        assert len(devices) > 0
        assert all("id" in d and "name" in d and "state" in d for d in devices)

    def test_toggle_device(self, tmp_data_file):
        import models as m
        device = m.get_devices()[0]
        original_state = device["state"]
        updated = m.update_device(device["id"], state=not original_state)
        assert updated["state"] == (not original_state)

    def test_add_and_delete_device(self, tmp_data_file):
        import models as m
        new_dev = m.add_device("Test laite", "heating", "🔥")
        assert new_dev["name"] == "Test laite"
        assert new_dev["type"] == "heating"
        found = m.get_device(new_dev["id"])
        assert found is not None
        deleted = m.delete_device(new_dev["id"])
        assert deleted is True
        assert m.get_device(new_dev["id"]) is None

    def test_delete_nonexistent_device(self, tmp_data_file):
        import models as m
        assert m.delete_device(99999) is False

    def test_add_and_delete_schedule(self, tmp_data_file):
        import models as m
        device = m.get_devices()[0]
        sched = m.add_schedule(device["id"], 3, "on")
        assert sched["hour"] == 3
        assert sched["action"] == "on"
        assert m.delete_schedule(sched["id"]) is True
        assert m.delete_schedule(sched["id"]) is False


# ─── Electricity module tests ─────────────────────────────────────────────────

class TestElectricity:
    def test_get_cheapest_hours_empty(self):
        import electricity as e
        assert e.get_cheapest_hours([]) == []

    def test_get_cheapest_hours_returns_n(self):
        import electricity as e
        prices = [
            {"date": "2024-01-15", "hour": h, "price_mwh": float(h + 1),
             "price_kwh": float(h + 1) / 10, "datetime": f"2024-01-15T{h:02d}:00:00"}
            for h in range(24)
        ]
        e._annotate_cheapness(prices)
        hours = e.get_cheapest_hours(prices, date="2024-01-15", n=6)
        assert len(hours) == 6
        # All returned hours should have lower price than non-returned hours
        cheapest_set = set(hours)
        non_cheap = [p for p in prices if p["hour"] not in cheapest_set]
        cheap     = [p for p in prices if p["hour"] in cheapest_set]
        assert max(p["price_mwh"] for p in cheap) <= min(p["price_mwh"] for p in non_cheap)

    def test_annotate_cheapness(self):
        import electricity as e
        prices = [
            {"date": "2024-01-15", "hour": h, "price_mwh": float(h + 1),
             "price_kwh": float(h + 1) / 10, "datetime": f"2024-01-15T{h:02d}:00:00"}
            for h in range(6)
        ]
        e._annotate_cheapness(prices)
        # 1/3 of 6 = 2 cheap hours
        cheap_count = sum(1 for p in prices if p["is_cheap"])
        assert cheap_count == 2
        # The cheapest two have hour 0 and 1 (price 1.0 and 2.0)
        cheap_hours = {p["hour"] for p in prices if p["is_cheap"]}
        assert cheap_hours == {0, 1}


# ─── API tests ────────────────────────────────────────────────────────────────

class TestDeviceAPI:
    def test_get_devices(self, client):
        r = client.get("/api/devices")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_toggle_device(self, client):
        r = client.get("/api/devices")
        device_id = r.get_json()[0]["id"]
        original = r.get_json()[0]["state"]

        r2 = client.post(f"/api/devices/{device_id}/toggle")
        assert r2.status_code == 200
        assert r2.get_json()["state"] == (not original)

    def test_toggle_nonexistent(self, client):
        r = client.post("/api/devices/99999/toggle")
        assert r.status_code == 404

    def test_patch_device(self, client):
        r = client.get("/api/devices")
        device_id = r.get_json()[0]["id"]
        r2 = client.patch(f"/api/devices/{device_id}",
                          data=json.dumps({"max_price": 7.5}),
                          content_type="application/json")
        assert r2.status_code == 200
        assert r2.get_json()["max_price"] == 7.5

    def test_patch_invalid_field(self, client):
        r = client.get("/api/devices")
        device_id = r.get_json()[0]["id"]
        r2 = client.patch(f"/api/devices/{device_id}",
                          data=json.dumps({"malicious_field": "x"}),
                          content_type="application/json")
        assert r2.status_code == 400

    def test_add_device(self, client):
        r = client.post("/api/devices",
                        data=json.dumps({"name": "Uusi laite", "type": "other", "icon": "🔧"}),
                        content_type="application/json")
        assert r.status_code == 201
        assert r.get_json()["name"] == "Uusi laite"

    def test_add_device_no_name(self, client):
        r = client.post("/api/devices",
                        data=json.dumps({"type": "other"}),
                        content_type="application/json")
        assert r.status_code == 400

    def test_delete_device(self, client):
        r = client.post("/api/devices",
                        data=json.dumps({"name": "Temp", "type": "other"}),
                        content_type="application/json")
        dev_id = r.get_json()["id"]
        r2 = client.delete(f"/api/devices/{dev_id}")
        assert r2.status_code == 200


class TestScheduleAPI:
    def test_get_schedules(self, client):
        r = client.get("/api/schedules")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_add_schedule(self, client):
        r = client.get("/api/devices")
        device_id = r.get_json()[0]["id"]
        r2 = client.post("/api/schedules",
                         data=json.dumps({"device_id": device_id, "hour": 3, "action": "on"}),
                         content_type="application/json")
        assert r2.status_code == 201
        sched = r2.get_json()
        assert sched["hour"] == 3
        assert sched["action"] == "on"

    def test_add_schedule_invalid_hour(self, client):
        r = client.get("/api/devices")
        device_id = r.get_json()[0]["id"]
        r2 = client.post("/api/schedules",
                         data=json.dumps({"device_id": device_id, "hour": 25, "action": "on"}),
                         content_type="application/json")
        assert r2.status_code == 400

    def test_add_schedule_invalid_action(self, client):
        r = client.get("/api/devices")
        device_id = r.get_json()[0]["id"]
        r2 = client.post("/api/schedules",
                         data=json.dumps({"device_id": device_id, "hour": 3, "action": "maybe"}),
                         content_type="application/json")
        assert r2.status_code == 400

    def test_delete_schedule(self, client):
        r = client.get("/api/devices")
        device_id = r.get_json()[0]["id"]
        r2 = client.post("/api/schedules",
                         data=json.dumps({"device_id": device_id, "hour": 5, "action": "off"}),
                         content_type="application/json")
        sched_id = r2.get_json()["id"]
        r3 = client.delete(f"/api/schedules/{sched_id}")
        assert r3.status_code == 200


class TestElectricityAPI:
    def test_cheapest_endpoint(self, client):
        r = client.get("/api/electricity/cheapest")
        assert r.status_code == 200
        data = r.get_json()
        assert "cheapest_hours" in data
        assert "date" in data


class TestPages:
    def test_index_page(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Kotilaitteet" in r.get_data(as_text=True)

    def test_devices_page(self, client):
        r = client.get("/devices")
        assert r.status_code == 200

    def test_electricity_page(self, client):
        r = client.get("/electricity")
        assert r.status_code == 200

    def test_schedule_page(self, client):
        r = client.get("/schedule")
        assert r.status_code == 200

    def test_scan_page(self, client):
        r = client.get("/scan")
        assert r.status_code == 200
        assert "Verkkolaitteet" in r.get_data(as_text=True)


# ─── Network scanner tests ────────────────────────────────────────────────────

class TestNetworkScanner:
    def test_get_local_network_returns_cidr(self):
        import network_scanner as ns
        net = ns.get_local_network()
        # Should be a valid CIDR string like "192.168.x.0/24"
        assert "/" in net
        import ipaddress
        ipaddress.IPv4Network(net)  # raises if invalid

    def test_guess_device_type_phone(self):
        import network_scanner as ns
        assert ns._guess_device_type("iphone-of-timo", None) == "phone"

    def test_guess_device_type_tv(self):
        import network_scanner as ns
        assert ns._guess_device_type("samsung-tv", None) == "tv"

    def test_guess_device_type_router(self):
        import network_scanner as ns
        assert ns._guess_device_type("fritzbox.home", None) == "router"

    def test_guess_device_type_unknown(self):
        import network_scanner as ns
        assert ns._guess_device_type(None, None) == "other"
        assert ns._guess_device_type("mystery-box", None) == "other"

    def test_scan_returns_list(self, monkeypatch):
        """scan_network() returns a list; mock the ping so no actual network I/O occurs."""
        import network_scanner as ns
        # Mock _ping_host to simulate one alive host
        monkeypatch.setattr(ns, "_ping_host", lambda ip, timeout=1: ip == "127.0.0.1")
        monkeypatch.setattr(ns, "_get_local_ip", lambda: "127.0.0.1")
        monkeypatch.setattr(ns, "_get_arp_table", lambda: {})
        monkeypatch.setattr(ns, "_resolve_hostname", lambda ip: None)
        result = ns.scan_network(timeout=1, max_workers=2)
        assert isinstance(result, list)

    def test_scan_returns_empty_on_loopback(self, monkeypatch):
        """scan_network() returns [] when local IP is 127.0.0.1."""
        import network_scanner as ns
        monkeypatch.setattr(ns, "_get_local_ip", lambda: "127.0.0.1")
        result = ns.scan_network()
        assert result == []


class TestScanAPI:
    def test_scan_endpoint_returns_json(self, client, monkeypatch):
        import network_scanner as ns
        monkeypatch.setattr(ns, "scan_network", lambda **kw: [
            {"ip": "192.168.1.42", "mac": "aa:bb:cc:dd:ee:ff",
             "hostname": "testhost", "type": "computer",
             "name": "testhost (192.168.1.42)"}
        ])
        r = client.get("/api/scan")
        assert r.status_code == 200
        data = r.get_json()
        assert "devices" in data
        assert "count" in data
        assert data["count"] == 1
        assert data["devices"][0]["ip"] == "192.168.1.42"

    def test_scan_import_creates_device(self, client):
        payload = {
            "ip": "192.168.1.55",
            "hostname": "mykamera",
            "type": "camera",
            "mac": "11:22:33:44:55:66",
        }
        r = client.post(
            "/api/scan/import",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert r.status_code == 201
        device = r.get_json()
        assert device["name"] == "mykamera"
        assert device["type"] == "camera"
        assert device["ip"] == "192.168.1.55"
        assert device["mac"] == "11:22:33:44:55:66"

    def test_scan_import_uses_ip_as_name_when_no_hostname(self, client):
        payload = {"ip": "192.168.1.99", "type": "other"}
        r = client.post(
            "/api/scan/import",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert r.status_code == 201
        device = r.get_json()
        assert device["name"] == "192.168.1.99"

    def test_scan_import_missing_ip(self, client):
        r = client.post(
            "/api/scan/import",
            data=json.dumps({"hostname": "ghost"}),
            content_type="application/json",
        )
        assert r.status_code == 400



class TestGetAvailableNetworks:
    def test_returns_list(self, monkeypatch):
        """get_available_networks() always returns a list."""
        import network_scanner as ns
        result = ns.get_available_networks()
        assert isinstance(result, list)

    def test_each_entry_has_required_keys(self, monkeypatch):
        """Each network entry contains interface, ip and network keys."""
        import network_scanner as ns
        monkeypatch.setattr(ns, "_get_local_ip", lambda: "192.168.50.1")
        result = ns.get_available_networks()
        # At minimum the fallback should kick in
        assert len(result) >= 1
        for entry in result:
            assert "interface" in entry
            assert "ip" in entry
            assert "network" in entry
            import ipaddress
            ipaddress.IPv4Network(entry["network"])  # valid CIDR

    def test_fallback_when_commands_fail(self, monkeypatch):
        """Falls back to _get_local_ip() when platform commands fail."""
        import network_scanner as ns
        monkeypatch.setattr(ns, "_get_local_ip", lambda: "10.0.0.5")
        # Make subprocess.check_output raise so the fallback path is exercised
        import subprocess

        def _raise(*a, **kw):
            raise OSError("fail")

        monkeypatch.setattr(subprocess, "check_output", _raise)
        result = ns.get_available_networks()
        assert len(result) == 1
        assert result[0]["ip"] == "10.0.0.5"
        assert result[0]["network"] == "10.0.0.0/24"

    def test_loopback_excluded(self, monkeypatch):
        """127.x.x.x addresses are never included."""
        import network_scanner as ns
        monkeypatch.setattr(ns, "_get_local_ip", lambda: "127.0.0.1")
        import subprocess

        def _raise(*a, **kw):
            raise OSError("fail")

        monkeypatch.setattr(subprocess, "check_output", _raise)
        result = ns.get_available_networks()
        assert all(not e["ip"].startswith("127.") for e in result)


class TestScanNetworkWithNetworkParam:
    def test_scan_specific_network(self, monkeypatch):
        """scan_network() respects an explicit network parameter."""
        import network_scanner as ns
        scanned_ips: list[str] = []

        def fake_ping(ip, timeout=1):
            scanned_ips.append(ip)
            return ip == "10.10.10.1"

        monkeypatch.setattr(ns, "_ping_host", fake_ping)
        monkeypatch.setattr(ns, "_get_arp_table", lambda: {})
        monkeypatch.setattr(ns, "_resolve_hostname", lambda ip: None)

        result = ns.scan_network(timeout=1, max_workers=4, network="10.10.10.0/30")
        # /30 has 2 usable hosts: .1 and .2
        assert all(ip.startswith("10.10.10.") for ip in scanned_ips)
        assert len(result) == 1
        assert result[0]["ip"] == "10.10.10.1"

    def test_scan_invalid_network_falls_back(self, monkeypatch):
        """scan_network() falls back to local detection when network is invalid."""
        import network_scanner as ns
        monkeypatch.setattr(ns, "_get_local_ip", lambda: "127.0.0.1")
        result = ns.scan_network(network="not-a-cidr")
        assert result == []


class TestScanNetworksAPI:
    def test_networks_endpoint_returns_list(self, client, monkeypatch):
        import network_scanner as ns
        monkeypatch.setattr(ns, "get_available_networks", lambda: [
            {"interface": "wlan0", "ip": "192.168.1.50", "network": "192.168.1.0/24"},
        ])
        r = client.get("/api/scan/networks")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["network"] == "192.168.1.0/24"

    def test_scan_endpoint_with_network_param(self, client, monkeypatch):
        import network_scanner as ns
        monkeypatch.setattr(ns, "scan_network", lambda **kw: [
            {"ip": "10.0.0.1", "mac": None, "hostname": None, "type": "other", "name": "10.0.0.1"}
        ])
        r = client.get("/api/scan?network=10.0.0.0%2F24")
        assert r.status_code == 200
        data = r.get_json()
        assert data["network"] == "10.0.0.0/24"
        assert data["count"] == 1
