"""Data models for Kotilaitteet."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Device:
    """Represents a home electronic device."""

    name: str
    ip_address: str
    mac_address: str
    device_type: str = "unknown"
    is_on: bool = False
    # If True the device is allowed to be scheduled by price-based automation
    price_controlled: bool = False
    # Minimum daily runtime in hours when price-controlled
    min_daily_hours: int = 0
    # Maximum price threshold (c/kWh) above which the device should be off
    price_threshold: Optional[float] = None
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Device":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ScheduleEntry:
    """A single on/off recommendation for a device at a specific hour."""

    device_mac: str
    hour: int  # 0-23 local time (Europe/Helsinki)
    date: str  # ISO date string YYYY-MM-DD
    recommended_state: bool  # True = on, False = off
    price_cents_per_kwh: float
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleEntry":
        return cls(**data)


@dataclass
class NetworkDevice:
    """A device discovered on the local network (may not be registered)."""

    ip_address: str
    mac_address: str
    hostname: str = ""
    vendor: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
