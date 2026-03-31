"""Device registration and state management with JSON persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from .models import Device

_DEFAULT_DB_PATH = Path.home() / ".kotilaitteet" / "devices.json"


class DeviceManager:
    """Manage a collection of home devices with persistent JSON storage."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._devices: dict[str, Device] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                with self._path.open() as fh:
                    data = json.load(fh)
                self._devices = {
                    d["mac_address"]: Device.from_dict(d) for d in data
                }
            except (json.JSONDecodeError, KeyError):
                self._devices = {}

    def save(self) -> None:
        """Persist the device list to disk."""
        with self._path.open("w") as fh:
            json.dump(
                [d.to_dict() for d in self._devices.values()],
                fh,
                indent=2,
                ensure_ascii=False,
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_device(self, device: Device) -> Device:
        """Register a new device. Returns the device (possibly updated)."""
        self._devices[device.mac_address] = device
        self.save()
        return device

    def remove_device(self, mac_address: str) -> bool:
        """Remove a device by MAC address. Returns True if removed."""
        if mac_address in self._devices:
            del self._devices[mac_address]
            self.save()
            return True
        return False

    def get_device(self, mac_address: str) -> Optional[Device]:
        return self._devices.get(mac_address)

    def get_device_by_name(self, name: str) -> Optional[Device]:
        for d in self._devices.values():
            if d.name.lower() == name.lower():
                return d
        return None

    def list_devices(self) -> List[Device]:
        return list(self._devices.values())

    # ------------------------------------------------------------------
    # State control
    # ------------------------------------------------------------------

    def turn_on(self, mac_address: str) -> bool:
        """Mark a device as on. Returns True on success."""
        device = self._devices.get(mac_address)
        if device is None:
            return False
        device.is_on = True
        self.save()
        return True

    def turn_off(self, mac_address: str) -> bool:
        """Mark a device as off. Returns True on success."""
        device = self._devices.get(mac_address)
        if device is None:
            return False
        device.is_on = False
        self.save()
        return True

    def toggle(self, mac_address: str) -> Optional[bool]:
        """Toggle device state. Returns new state or None if not found."""
        device = self._devices.get(mac_address)
        if device is None:
            return None
        device.is_on = not device.is_on
        self.save()
        return device.is_on

    # ------------------------------------------------------------------
    # Price control settings
    # ------------------------------------------------------------------

    def set_price_control(
        self,
        mac_address: str,
        enabled: bool,
        min_daily_hours: int = 0,
        price_threshold: Optional[float] = None,
    ) -> bool:
        """Configure price-based automation for a device."""
        device = self._devices.get(mac_address)
        if device is None:
            return False
        device.price_controlled = enabled
        device.min_daily_hours = min_daily_hours
        if price_threshold is not None:
            device.price_threshold = price_threshold
        self.save()
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def find_by_ip(self, ip_address: str) -> Optional[Device]:
        for d in self._devices.values():
            if d.ip_address == ip_address:
                return d
        return None
