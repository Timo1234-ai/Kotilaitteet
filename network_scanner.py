"""
Network Scanner – discovers devices on the local WLAN/LAN.

Performs a parallel ping sweep over the detected /24 subnet, then
enriches the results with MAC addresses from the ARP table and
reverse-DNS hostnames.  No external dependencies are required – only
the Python standard library is used.
"""
import ipaddress
import logging
import re
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

def get_available_networks() -> list[dict]:
    """Return all available local IPv4 network interfaces (excluding loopback).

    Each entry contains:
        interface – network interface name (best-effort)
        ip        – IPv4 address of this host on that interface
        network   – CIDR string for the subnet (e.g. '192.168.1.0/24')

    Falls back to the primary interface detected by :func:`_get_local_ip` when
    platform-specific enumeration fails.
    """
    networks: list[dict] = []
    seen_networks: set[str] = set()

    def _add(interface: str, ip: str, prefix: int = 24) -> None:
        if ip.startswith("127.") or ip.startswith("169.254."):
            return
        try:
            net = str(ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False))
        except ValueError:
            net = str(ipaddress.IPv4Network(f"{ip}/24", strict=False))
        if net not in seen_networks:
            seen_networks.add(net)
            networks.append({"interface": interface, "ip": ip, "network": net})

    try:
        if sys.platform == "win32":
            output = subprocess.check_output(
                ["ipconfig"], text=True, timeout=5, stderr=subprocess.DEVNULL
            )
            current_iface = "unknown"
            for line in output.splitlines():
                iface_match = re.match(r"^(\S.*adapter .+):$", line)
                if iface_match:
                    current_iface = iface_match.group(1).strip()
                ip_match = re.search(r"IPv4 Address[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", line)
                if ip_match:
                    _add(current_iface, ip_match.group(1))
        else:
            # Try 'ip -4 addr show' (Linux), fall back to 'ifconfig' (macOS/BSD)
            try:
                output = subprocess.check_output(
                    ["ip", "-4", "addr", "show"],
                    text=True, timeout=5, stderr=subprocess.DEVNULL,
                )
                current_iface = "unknown"
                for line in output.splitlines():
                    iface_match = re.match(r"^\d+:\s+(\S+):", line)
                    if iface_match:
                        current_iface = iface_match.group(1)
                    addr_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", line)
                    if addr_match:
                        _add(current_iface, addr_match.group(1), int(addr_match.group(2)))
            except (subprocess.CalledProcessError, FileNotFoundError, OSError):
                output = subprocess.check_output(
                    ["ifconfig"], text=True, timeout=5, stderr=subprocess.DEVNULL
                )
                current_iface = "unknown"
                for line in output.splitlines():
                    iface_match = re.match(r"^(\S+)", line)
                    if iface_match and not line.startswith(" "):
                        current_iface = iface_match.group(1).rstrip(":")
                    addr_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)\s+netmask\s+(\S+)", line)
                    if addr_match:
                        ip = addr_match.group(1)
                        netmask = addr_match.group(2)
                        try:
                            prefix = ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
                        except ValueError:
                            prefix = 24
                        _add(current_iface, ip, prefix)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Network interface enumeration failed: %s", exc)

    # Fallback: use the primary IP determined by routing table
    if not networks:
        primary_ip = _get_local_ip()
        if primary_ip != "127.0.0.1":
            _add("default", primary_ip)

    return networks


def get_local_network() -> str:
    """Return the detected local /24 network as a CIDR string (e.g. '192.168.1.0/24')."""
    local_ip = _get_local_ip()
    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    return str(network)


def scan_network(
    timeout: int = 1,
    max_workers: int = 50,
    network: Optional[str] = None,
) -> list[dict]:
    """
    Scan a /24 subnet and return discovered hosts.

    Parameters:
        timeout    – per-host ping timeout in seconds
        max_workers – parallel worker threads
        network    – CIDR string of the network to scan (e.g. '192.168.1.0/24').
                     When omitted the local /24 subnet is detected automatically.

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
    if network:
        try:
            net_obj = ipaddress.IPv4Network(network, strict=False)
        except ValueError:
            logger.warning("Invalid network %r; falling back to local detection", network)
            net_obj = None
    else:
        net_obj = None

    if net_obj is None:
        local_ip = _get_local_ip()
        if local_ip == "127.0.0.1":
            logger.warning("Could not determine local IP address; returning empty scan result")
            return []
        net_obj = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)

    hosts = [str(h) for h in net_obj.hosts()][:MAX_HOSTS]

    logger.info("Scanning %s (%d hosts)…", net_obj, len(hosts))

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
