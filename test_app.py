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
