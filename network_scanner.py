"""
Network Scanner – discovers devices on the local WLAN/LAN.

Performs a parallel ping sweep over the detected /24 subnet, then
enriches the results with MAC addresses from the ARP table and
reverse-DNS hostnames.  No external dependencies are required – only
the Python standard library is used.
"""
import ipaddress
import logging
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum hosts per scan (a /24 subnet has 254 usable addresses)
MAX_HOSTS = 254

# Icon mapping used when importing a discovered device
ICON_MAP: dict[str, str] = {
    "phone": "📱",
    "tv": "📺",
    "printer": "🖨️",
    "router": "📡",
    "computer": "💻",
    "tablet": "📱",
    "camera": "📷",
    "smart_device": "🔌",
    "other": "🔧",
}


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_local_ip() -> str:
    """Return the primary local IP address of this host."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _ping_host(ip: str, timeout: int = 1) -> bool:
    """Return True if the host responds to a single ICMP ping."""
    try:
        if sys.platform == "win32":
            args = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
        else:
            args = ["ping", "-c", "1", "-W", str(timeout), ip]
        result = subprocess.run(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 2,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _get_arp_table() -> dict[str, str]:
    """Return a mapping of {ip: mac} read from the OS ARP table."""
    mac_map: dict[str, str] = {}
    try:
        output = subprocess.check_output(
            ["arp", "-a"], text=True, timeout=5, stderr=subprocess.DEVNULL
        )
        for line in output.splitlines():
            if sys.platform == "win32":
                # Windows: "  192.168.1.1    aa-bb-cc-dd-ee-ff  dynamic"
                parts = line.split()
                if len(parts) >= 2 and parts[0].count(".") == 3:
                    mac_map[parts[0]] = parts[1].replace("-", ":")
            else:
                # Linux/macOS: "hostname (192.168.1.1) at aa:bb:cc:dd:ee:ff ..."
                if " at " in line and "(" in line:
                    ip_part = line.split("(")[1].split(")")[0]
                    mac_part = line.split(" at ")[1].split()[0]
                    if mac_part.lower() not in ("incomplete", "<incomplete>"):
                        mac_map[ip_part] = mac_part
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        pass
    return mac_map


def _resolve_hostname(ip: str) -> Optional[str]:
    """Reverse-resolve the hostname for an IP address (best-effort)."""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return None


def _guess_device_type(hostname: Optional[str], mac: Optional[str]) -> str:
    """Heuristically classify a device from its hostname.

    The *mac* parameter is accepted for future MAC OUI vendor-based
    classification but is not yet used.
    """
    _ = mac  # reserved for future MAC OUI lookup
    if hostname:
        hn = hostname.lower()
        # Check TV before phone so "samsung-tv" is classified as TV, not phone
        if any(k in hn for k in ("tv", "television", "apple-tv", "firetv", "roku", "chromecast")):
            return "tv"
        if any(k in hn for k in ("phone", "iphone", "android", "pixel", "galaxy")):
            return "phone"
        if any(k in hn for k in ("printer", "print", "hp", "epson", "canon", "brother")):
            return "printer"
        if any(k in hn for k in ("router", "gateway", "ap", "access-point", "fritzbox", "mikrotik")):
            return "router"
        if any(k in hn for k in ("laptop", "macbook", "desktop", "pc", "thinkpad", "surface")):
            return "computer"
        if any(k in hn for k in ("tablet", "ipad", "kindle")):
            return "tablet"
        if any(k in hn for k in ("camera", "cam", "hikvision", "dahua", "nest-cam")):
            return "camera"
        if any(k in hn for k in ("thermostat", "hue", "smart", "iot", "esp", "sonoff", "tasmota", "shelly")):
            return "smart_device"
    return "other"


# ─── Public API ───────────────────────────────────────────────────────────────

def get_local_network() -> str:
    """Return the detected local /24 network as a CIDR string (e.g. '192.168.1.0/24')."""
    local_ip = _get_local_ip()
    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    return str(network)


def scan_network(timeout: int = 1, max_workers: int = 50) -> list[dict]:
    """
    Scan the local /24 subnet and return discovered hosts.

    Each host dict contains:
        ip       – IPv4 address string
        mac      – MAC address string or None
        hostname – reverse-DNS name or None
        type     – heuristic device type string
        name     – display name ("hostname (ip)" or just "ip")

    The scan uses parallel ICMP pings; no root/admin privileges are required
    on most platforms (Linux requires either cap_net_raw or running as root for
    raw sockets, but subprocess ping works for regular users).
    """
    local_ip = _get_local_ip()
    if local_ip == "127.0.0.1":
        logger.warning("Could not determine local IP address; returning empty scan result")
        return []

    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    hosts = [str(h) for h in network.hosts()][:MAX_HOSTS]

    logger.info("Scanning %s (%d hosts)…", network, len(hosts))

    # Parallel ping sweep
    reachable: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(_ping_host, ip, timeout): ip for ip in hosts}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                if future.result():
                    reachable.append(ip)
            except Exception:  # noqa: BLE001
                pass

    # Refresh ARP table (populate by pinging all hosts first)
    arp_table = _get_arp_table()

    discovered: list[dict] = []
    for ip in sorted(reachable, key=lambda x: ipaddress.ip_address(x)):
        mac = arp_table.get(ip)
        hostname = _resolve_hostname(ip)
        device_type = _guess_device_type(hostname, mac)
        display_name = hostname or ip
        discovered.append({
            "ip": ip,
            "mac": mac,
            "hostname": hostname,
            "type": device_type,
            "name": f"{display_name} ({ip})" if hostname else ip,
        })

    logger.info("Scan complete: %d device(s) found", len(discovered))
    return discovered
