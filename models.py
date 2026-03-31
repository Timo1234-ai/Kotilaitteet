"""
Device and schedule data models with JSON-file persistence.
"""
import json
import os
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

# Default devices loaded on first run
DEFAULT_DEVICES = [
    {"id": 1, "name": "Lämmitys",        "type": "heating",   "icon": "🔥", "state": False, "power": 0,  "auto": False, "max_price": 10.0},
    {"id": 2, "name": "Olohuoneen valot", "type": "lighting",  "icon": "💡", "state": False, "power": 0,  "auto": False, "max_price": 15.0},
    {"id": 3, "name": "Makuuhuoneen valot","type": "lighting", "icon": "💡", "state": False, "power": 0,  "auto": False, "max_price": 15.0},
    {"id": 4, "name": "Ilmastointi",      "type": "ac",        "icon": "❄️", "state": False, "power": 0,  "auto": False, "max_price": 8.0},
    {"id": 5, "name": "Sähköauton lataus","type": "ev_charger","icon": "🔌", "state": False, "power": 0,  "auto": False, "max_price": 5.0},
    {"id": 6, "name": "Poreallas",        "type": "jacuzzi",   "icon": "🛁", "state": False, "power": 0,  "auto": False, "max_price": 6.0},
    {"id": 7, "name": "Ulkovalaistus",    "type": "lighting",  "icon": "🏮", "state": False, "power": 0,  "auto": False, "max_price": 15.0},
    {"id": 8, "name": "Lattialämmitys",   "type": "heating",   "icon": "🔥", "state": False, "power": 0,  "auto": False, "max_price": 10.0},
]

def _load() -> dict:
    """Load application data from disk."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"devices": DEFAULT_DEVICES.copy(), "schedules": []}


def _save(data: dict) -> None:
    """Persist application data to disk."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Devices ──────────────────────────────────────────────────────────────────

def get_devices() -> list:
    return _load()["devices"]


def get_device(device_id: int) -> dict | None:
    for d in get_devices():
        if d["id"] == device_id:
            return d
    return None


def update_device(device_id: int, **fields) -> dict | None:
    data = _load()
    for d in data["devices"]:
        if d["id"] == device_id:
            d.update(fields)
            _save(data)
            return d
    return None


def add_device(name: str, device_type: str, icon: str = "🔧") -> dict:
    data = _load()
    new_id = max((d["id"] for d in data["devices"]), default=0) + 1
    device = {
        "id": new_id,
        "name": name,
        "type": device_type,
        "icon": icon,
        "state": False,
        "power": 0,
        "auto": False,
        "max_price": 10.0,
    }
    data["devices"].append(device)
    _save(data)
    return device


def delete_device(device_id: int) -> bool:
    data = _load()
    before = len(data["devices"])
    data["devices"] = [d for d in data["devices"] if d["id"] != device_id]
    if len(data["devices"]) < before:
        _save(data)
        return True
    return False


# ─── Schedules ────────────────────────────────────────────────────────────────

def get_schedules() -> list:
    return _load()["schedules"]


def add_schedule(device_id: int, hour: int, action: str) -> dict:
    data = _load()
    new_id = max((s["id"] for s in data["schedules"]), default=0) + 1
    schedule = {
        "id": new_id,
        "device_id": device_id,
        "hour": hour,
        "action": action,          # "on" or "off"
        "created_at": datetime.now().isoformat(),
    }
    data["schedules"].append(schedule)
    _save(data)
    return schedule


def delete_schedule(schedule_id: int) -> bool:
    data = _load()
    before = len(data["schedules"])
    data["schedules"] = [s for s in data["schedules"] if s["id"] != schedule_id]
    if len(data["schedules"]) < before:
        _save(data)
        return True
    return False
