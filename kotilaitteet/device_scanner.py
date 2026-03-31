"""Automatic WLAN device discovery using ARP and nmap."""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys
from typing import List

from .models import NetworkDevice

# Regex patterns for parsing ARP table and nmap output
_ARP_LINE_RE = re.compile(
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+(?:ether\s+)?(?P<mac>[0-9a-f:A-F-]{11,17})",
)
_MAC_NORMALIZE_RE = re.compile(r"[^0-9a-fA-F]")

# OUI lookup table (partial – covers common consumer vendors)
_OUI_TABLE: dict[str, str] = {
    "b8273b": "Raspberry Pi",
    "dc:a6:32": "Raspberry Pi",
    "e4:5f:01": "Raspberry Pi",
    "f0:9f:c2": "Ubiquiti",
    "00:17:88": "Philips Hue",
    "18:b4:30": "Nest",
    "50:c7:bf": "TP-Link",
    "b0:be:76": "TP-Link",
    "c4:e9:84": "TP-Link",
    "d8:07:b6": "TP-Link",
    "3c:84:6a": "TP-Link",
    "a0:f3:c1": "TP-Link",
    "14:91:82": "TP-Link",
    "b4:b0:24": "Shelly",
    "c4:5b:be": "Shelly",
    "84:f7:03": "Shelly",
    "d8:f1:5b": "Apple",
    "a4:83:e7": "Apple",
    "00:50:f2": "Microsoft",
    "d4:01:c3": "Samsung",
    "b0:72:bf": "Samsung",
}


def _normalize_mac(mac: str) -> str:
    """Return lower-case colon-separated MAC address."""
    clean = _MAC_NORMALIZE_RE.sub("", mac).lower()
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


def _lookup_vendor(mac: str) -> str:
    """Return vendor name from OUI prefix, or empty string."""
    mac = mac.lower()
    prefix6 = mac.replace(":", "")[:6]
    prefix8 = mac[:8]
    return (
        _OUI_TABLE.get(prefix8)
        or _OUI_TABLE.get(prefix6)
        or ""
    )


def _resolve_hostname(ip: str) -> str:
    """Try a reverse DNS lookup; return empty string on failure."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, OSError):
        return ""


def _get_local_network() -> str:
    """Best-effort detection of the local WLAN subnet (e.g. 192.168.1.0/24)."""
    try:
        # Use a UDP connect trick – no packets are sent
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        net = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        return str(net)
    except OSError:
        return "192.168.1.0/24"


# ---------------------------------------------------------------------------
# Platform-specific ARP scanners
# ---------------------------------------------------------------------------

def _scan_with_nmap(network: str) -> List[NetworkDevice]:
    """Run nmap host-discovery scan and return discovered devices."""
    try:
        result = subprocess.run(
            ["nmap", "-sn", "-T4", network, "--oG", "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired:
        return []

    devices: List[NetworkDevice] = []
    ip_re = re.compile(r"Host: (\d+\.\d+\.\d+\.\d+)\s+\(([^)]*)\)")
    mac_re = re.compile(r"MAC Address: ([0-9A-F:]{17})\s*\(([^)]*)\)")

    current_ip = current_host = ""
    for line in result.stdout.splitlines():
        ip_m = ip_re.search(line)
        mac_m = mac_re.search(line)
        if ip_m:
            current_ip = ip_m.group(1)
            current_host = ip_m.group(2)
        if mac_m and current_ip:
            mac = _normalize_mac(mac_m.group(1))
            vendor = mac_m.group(2) or _lookup_vendor(mac)
            devices.append(
                NetworkDevice(
                    ip_address=current_ip,
                    mac_address=mac,
                    hostname=current_host or _resolve_hostname(current_ip),
                    vendor=vendor,
                )
            )
            current_ip = current_host = ""
    return devices


def _scan_with_arp_table() -> List[NetworkDevice]:
    """Read the system ARP table (works without nmap)."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["arp", "-a"], capture_output=True, text=True, timeout=10
            )
        else:
            result = subprocess.run(
                ["arp", "-a", "-n"], capture_output=True, text=True, timeout=10
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    devices: List[NetworkDevice] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        m = _ARP_LINE_RE.search(line)
        if not m:
            continue
        ip = m.group("ip")
        mac_raw = m.group("mac")
        # Skip broadcast / multicast entries
        if ip.endswith(".255") or mac_raw in ("ff:ff:ff:ff:ff:ff", "FF-FF-FF-FF-FF-FF"):
            continue
        mac = _normalize_mac(mac_raw)
        if mac in seen:
            continue
        seen.add(mac)
        devices.append(
            NetworkDevice(
                ip_address=ip,
                mac_address=mac,
                hostname=_resolve_hostname(ip),
                vendor=_lookup_vendor(mac),
            )
        )
    return devices


def _ping_sweep(network: str) -> None:
    """Send ICMP pings to populate the ARP cache (best-effort)."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["for", "/L", "%i", "in", "(1,1,254)", "do", "@ping", "-n", "1",
                 "-w", "100", f"{network.rsplit('.', 1)[0]}.%i"],
                shell=True,
                capture_output=True,
                timeout=30,
            )
        else:
            net = ipaddress.IPv4Network(network, strict=False)
            # Only sweep if <= /24 to avoid very large ranges
            if net.prefixlen >= 24:
                subprocess.run(
                    ["ping", "-c", "1", "-W", "1", "-b",
                     str(net.broadcast_address)],
                    capture_output=True,
                    timeout=5,
                )
    except Exception:
        pass


def scan_network(network: str | None = None) -> List[NetworkDevice]:
    """Discover devices on the local network.

    Tries nmap first (more accurate); falls back to reading the ARP table after
    a lightweight ping sweep to populate the cache.

    Args:
        network: CIDR range to scan, e.g. ``"192.168.1.0/24"``.
                 Auto-detected when *None*.

    Returns:
        List of :class:`NetworkDevice` objects found on the network.
    """
    if network is None:
        network = _get_local_network()

    # Try nmap first
    devices = _scan_with_nmap(network)
    if devices:
        return devices

    # Fallback: ping sweep + ARP table
    _ping_sweep(network)
    return _scan_with_arp_table()
