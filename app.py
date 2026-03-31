"""
Kotilaitteet – Home Device Control Application
===============================================
Flask web application for controlling home devices and scheduling them
to run during the cheapest electricity hours.
"""
import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, redirect, render_template, request, url_for

import electricity as elec
import models
import network_scanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory price cache so we don't hit the API on every page load
_price_cache: dict = {"prices": [], "fetched_at": None}
CACHE_TTL_SECONDS = 3600  # refresh prices at most once per hour


def _get_prices() -> list[dict]:
    """Return cached prices, refreshing if the cache is stale."""
    now = datetime.now(tz=timezone.utc)
    fetched_at = _price_cache["fetched_at"]
    if fetched_at is None or (now - fetched_at).total_seconds() > CACHE_TTL_SECONDS:
        _price_cache["prices"] = elec.fetch_prices()
        _price_cache["fetched_at"] = now
    return _price_cache["prices"]


# ─── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    devices = models.get_devices()
    prices = _get_prices()
    today = datetime.now().strftime("%Y-%m-%d")
    today_prices = [p for p in prices if p["date"] == today]
    cheapest = elec.get_cheapest_hours(prices, date=today, n=8)
    current_hour = datetime.now().hour
    current_price = next(
        (p for p in today_prices if p["hour"] == current_hour), None
    )
    return render_template(
        "index.html",
        devices=devices,
        today_prices=today_prices,
        cheapest_hours=cheapest,
        current_price=current_price,
        now=datetime.now(),
    )


@app.route("/devices")
def devices_page():
    devices = models.get_devices()
    return render_template("devices.html", devices=devices)


@app.route("/electricity")
def electricity_page():
    prices = _get_prices()
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = None
    dates_available = sorted({p["date"] for p in prices})
    if len(dates_available) > 1:
        tomorrow = dates_available[1]
    today_prices = [p for p in prices if p["date"] == today]
    tomorrow_prices = [p for p in prices if p["date"] == tomorrow] if tomorrow else []
    cheapest = elec.get_cheapest_hours(prices, date=today, n=8)
    fetched_at = _price_cache.get("fetched_at")
    return render_template(
        "electricity.html",
        today_prices=today_prices,
        tomorrow_prices=tomorrow_prices,
        cheapest_hours=cheapest,
        fetched_at=fetched_at,
        today=today,
        tomorrow=tomorrow,
    )


@app.route("/scan")
def scan_page():
    return render_template("scan.html")


@app.route("/schedule")
def schedule_page():
    schedules = models.get_schedules()
    devices = models.get_devices()
    device_map = {d["id"]: d for d in devices}
    prices = _get_prices()
    today = datetime.now().strftime("%Y-%m-%d")
    cheapest = elec.get_cheapest_hours(prices, date=today, n=8)
    return render_template(
        "schedule.html",
        schedules=schedules,
        devices=devices,
        device_map=device_map,
        cheapest_hours=cheapest,
    )


# ─── Device API ───────────────────────────────────────────────────────────────

@app.route("/api/devices", methods=["GET"])
def api_devices():
    return jsonify(models.get_devices())


@app.route("/api/devices/<int:device_id>/toggle", methods=["POST"])
def api_toggle(device_id: int):
    device = models.get_device(device_id)
    if device is None:
        return jsonify({"error": "Device not found"}), 404
    updated = models.update_device(device_id, state=not device["state"])
    return jsonify(updated)


@app.route("/api/devices/<int:device_id>", methods=["PATCH"])
def api_update_device(device_id: int):
    payload = request.get_json(silent=True) or {}
    allowed = {"state", "power", "auto", "max_price", "name"}
    fields = {k: v for k, v in payload.items() if k in allowed}
    if not fields:
        return jsonify({"error": "No valid fields provided"}), 400
    updated = models.update_device(device_id, **fields)
    if updated is None:
        return jsonify({"error": "Device not found"}), 404
    return jsonify(updated)


@app.route("/api/devices", methods=["POST"])
def api_add_device():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    device_type = (payload.get("type") or "other").strip()
    icon = (payload.get("icon") or "🔧").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    device = models.add_device(name, device_type, icon)
    return jsonify(device), 201


@app.route("/api/devices/<int:device_id>", methods=["DELETE"])
def api_delete_device(device_id: int):
    if not models.delete_device(device_id):
        return jsonify({"error": "Device not found"}), 404
    return jsonify({"deleted": device_id})


# ─── Schedule API ─────────────────────────────────────────────────────────────

@app.route("/api/schedules", methods=["GET"])
def api_schedules():
    return jsonify(models.get_schedules())


@app.route("/api/schedules", methods=["POST"])
def api_add_schedule():
    payload = request.get_json(silent=True) or {}
    device_id = payload.get("device_id")
    hour = payload.get("hour")
    action = payload.get("action")
    if device_id is None or hour is None or action not in ("on", "off"):
        return jsonify({"error": "device_id, hour, and action ('on'/'off') are required"}), 400
    try:
        hour = int(hour)
        if not 0 <= hour <= 23:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "hour must be an integer 0-23"}), 400
    if models.get_device(int(device_id)) is None:
        return jsonify({"error": "Device not found"}), 404
    schedule = models.add_schedule(int(device_id), hour, action)
    return jsonify(schedule), 201


@app.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
def api_delete_schedule(schedule_id: int):
    if not models.delete_schedule(schedule_id):
        return jsonify({"error": "Schedule not found"}), 404
    return jsonify({"deleted": schedule_id})


# ─── Electricity price API ────────────────────────────────────────────────────

@app.route("/api/electricity/prices", methods=["GET"])
def api_prices():
    prices = _get_prices()
    date = request.args.get("date")
    if date:
        prices = [p for p in prices if p["date"] == date]
    return jsonify(prices)


@app.route("/api/electricity/cheapest", methods=["GET"])
def api_cheapest():
    date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    n = int(request.args.get("n", 8))
    prices = _get_prices()
    hours = elec.get_cheapest_hours(prices, date=date, n=n)
    return jsonify({"date": date, "cheapest_hours": hours})


@app.route("/api/electricity/refresh", methods=["POST"])
def api_refresh_prices():
    """Force a price cache refresh."""
    _price_cache["fetched_at"] = None
    prices = _get_prices()
    fetched_at = _price_cache["fetched_at"]
    return jsonify({
        "fetched": len(prices),
        "fetched_at": fetched_at.isoformat() if fetched_at is not None else None,
    })


# ─── Auto-scheduling tick ─────────────────────────────────────────────────────

@app.route("/api/auto/tick", methods=["POST"])
def api_auto_tick():
    """
    Apply auto-schedule logic: turn on devices whose max_price >= current price.
    This endpoint is meant to be called once per hour (e.g. by a cron job).
    """
    prices = _get_prices()
    current_hour = datetime.now().hour
    today = datetime.now().strftime("%Y-%m-%d")
    current_price_entry = next(
        (p for p in prices if p["date"] == today and p["hour"] == current_hour), None
    )
    if current_price_entry is None:
        return jsonify({"message": "No price data available for current hour"}), 200

    current_price_kwh = current_price_entry["price_kwh"]
    actions = []
    for device in models.get_devices():
        if not device.get("auto"):
            continue
        should_be_on = current_price_kwh <= device.get("max_price", 0)
        if device["state"] != should_be_on:
            models.update_device(device["id"], state=should_be_on)
            actions.append({
                "device_id": device["id"],
                "name": device["name"],
                "action": "on" if should_be_on else "off",
                "price_kwh": current_price_kwh,
            })

    return jsonify({"current_price_kwh": current_price_kwh, "actions": actions})


# ─── Network scan API ─────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["GET"])
def api_scan():
    """
    Scan the local WLAN/LAN and return discovered devices.

    Query parameters:
        timeout  (int, default 1)  – per-host ping timeout in seconds
        workers  (int, default 50) – parallel worker threads

    Returns JSON:
        {"network": "192.168.1.0/24", "count": N, "devices": [...]}
    """
    timeout = max(1, min(int(request.args.get("timeout", 1)), 10))
    workers = max(1, min(int(request.args.get("workers", 50)), 200))
    devices = network_scanner.scan_network(timeout=timeout, max_workers=workers)
    local_net = network_scanner.get_local_network()
    return jsonify({"network": local_net, "count": len(devices), "devices": devices})


@app.route("/api/scan/import", methods=["POST"])
def api_scan_import():
    """
    Import a discovered network device into the managed device list.

    Expected JSON body:
        {"ip": "192.168.1.10", "hostname": "mydevice", "type": "phone", "mac": "aa:bb:cc:..."}

    Returns the newly created device object (HTTP 201).
    """
    payload = request.get_json(silent=True) or {}
    ip = (payload.get("ip") or "").strip()
    hostname = (payload.get("hostname") or "").strip() or None
    device_type = (payload.get("type") or "other").strip()
    mac = (payload.get("mac") or "").strip() or None

    if not ip:
        return jsonify({"error": "ip is required"}), 400

    name = hostname or ip
    icon = network_scanner.ICON_MAP.get(device_type, "🔧")
    device = models.add_device(name, device_type, icon)
    # Store the network metadata on the device record
    models.update_device(device["id"], ip=ip, mac=mac, hostname=hostname)
    # Re-fetch so the response includes ip/mac/hostname
    device = models.get_device(device["id"])
    return jsonify(device), 201



    import os as _os
    debug = _os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=5000)
