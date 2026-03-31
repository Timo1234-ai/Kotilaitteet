"""Command-line interface for Kotilaitteet home device manager."""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import List, Optional

from .device_manager import DeviceManager
from .device_scanner import scan_network
from .electricity import fetch_prices, price_summary, cheapest_hours
from .models import Device
from .scheduler import build_daily_schedule, current_recommendations

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


def _color(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


def _state_str(on: bool) -> str:
    return _color("ON ", _GREEN) if on else _color("OFF", _RED)


def _print_device_table(devices: List[Device]) -> None:
    if not devices:
        print("  (no devices registered)")
        return
    header = f"{'Name':<20} {'IP':<16} {'MAC':<18} {'Type':<14} {'State':<5} {'Price ctrl'}"
    print(_color(header, _BOLD))
    print("-" * 80)
    for d in devices:
        pc = _color("yes", _GREEN) if d.price_controlled else "no"
        print(
            f"{d.name:<20} {d.ip_address:<16} {d.mac_address:<18} "
            f"{d.device_type:<14} {_state_str(d.is_on):<5}  {pc}"
        )


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Scan the local network for connected devices."""
    print(f"Scanning network{' ' + args.network if args.network else ''}…")
    found = scan_network(args.network or None)
    if not found:
        print("No devices found. Make sure you have nmap installed or run as root/sudo.")
        return 0
    print(f"\nFound {len(found)} device(s):\n")
    header = f"{'IP':<16} {'MAC':<18} {'Hostname':<30} {'Vendor'}"
    print(_color(header, _BOLD))
    print("-" * 80)
    for nd in found:
        reg = manager.get_device(nd.mac_address)
        reg_marker = _color(" [registered]", _CYAN) if reg else ""
        print(
            f"{nd.ip_address:<16} {nd.mac_address:<18} {(nd.hostname or '-'):<30} "
            f"{nd.vendor or '-'}{reg_marker}"
        )
    return 0


def cmd_list(args: argparse.Namespace, manager: DeviceManager) -> int:
    """List all registered devices."""
    devices = manager.list_devices()
    print(f"\nRegistered devices ({len(devices)}):\n")
    _print_device_table(devices)
    return 0


def cmd_add(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Register a device."""
    device = Device(
        name=args.name,
        ip_address=args.ip,
        mac_address=args.mac.lower(),
        device_type=args.type or "unknown",
        notes=args.notes or "",
    )
    manager.add_device(device)
    print(f"Device '{device.name}' added successfully.")
    return 0


def cmd_remove(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Remove a registered device."""
    mac = args.mac.lower()
    if manager.remove_device(mac):
        print(f"Device with MAC {mac} removed.")
        return 0
    print(f"Device with MAC {mac} not found.")
    return 1


def cmd_on(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Turn a device on."""
    device = _resolve_device(args, manager)
    if device is None:
        return 1
    manager.turn_on(device.mac_address)
    print(f"Device '{device.name}' → {_state_str(True)}")
    return 0


def cmd_off(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Turn a device off."""
    device = _resolve_device(args, manager)
    if device is None:
        return 1
    manager.turn_off(device.mac_address)
    print(f"Device '{device.name}' → {_state_str(False)}")
    return 0


def cmd_toggle(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Toggle a device's state."""
    device = _resolve_device(args, manager)
    if device is None:
        return 1
    new_state = manager.toggle(device.mac_address)
    print(f"Device '{device.name}' → {_state_str(new_state)}")
    return 0


def cmd_price_control(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Configure price-based automation for a device."""
    device = _resolve_device(args, manager)
    if device is None:
        return 1
    enabled = args.enable
    manager.set_price_control(
        device.mac_address,
        enabled=enabled,
        min_daily_hours=args.hours or 0,
        price_threshold=args.threshold,
    )
    state_word = _color("enabled", _GREEN) if enabled else _color("disabled", _RED)
    print(f"Price control {state_word} for '{device.name}'.")
    if enabled:
        if args.hours:
            print(f"  Minimum daily runtime: {args.hours} h")
        if args.threshold is not None:
            print(f"  Price threshold: {args.threshold:.2f} c/kWh")
    return 0


def cmd_prices(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Show today's electricity prices."""
    print("Fetching electricity prices…")
    try:
        prices = fetch_prices()
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    today = datetime.date.today()
    day_prices = [p for p in prices if p.hour_start.date() == today]
    if not day_prices:
        print("No price data available for today.")
        return 0

    summary = price_summary(day_prices)
    print(f"\nToday's electricity prices ({today}):\n")
    header = f"{'Hour':<8} {'Price (c/kWh)':<16}"
    print(_color(header, _BOLD))
    print("-" * 28)
    for p in day_prices:
        price_str = f"{p.price_cents_kwh:>8.2f} c/kWh"
        if p.price_cents_kwh == summary["min"]:
            price_str = _color(price_str, _GREEN)
        elif p.price_cents_kwh == summary["max"]:
            price_str = _color(price_str, _RED)
        print(f"  {p.hour_start.strftime('%H:%M'):<6} {price_str}")

    print()
    print(f"  Min : {summary['min']:.2f} c/kWh")
    print(f"  Max : {summary['max']:.2f} c/kWh")
    print(f"  Avg : {summary['avg']:.2f} c/kWh")

    if args.cheapest:
        n = min(args.cheapest, len(day_prices))
        cheap = cheapest_hours(n, day_prices, today)
        hours_str = ", ".join(p.hour_start.strftime("%H:%M") for p in cheap)
        print(
            f"\n  {n} cheapest hour(s): {_color(hours_str, _GREEN)}"
        )
    return 0


def cmd_schedule(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Show or apply the price-based schedule for today."""
    print("Fetching electricity prices…")
    try:
        prices = fetch_prices()
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    target_date = datetime.date.today()
    schedule = build_daily_schedule(manager, target_date, prices)

    if not schedule:
        print("No price-controlled devices configured.")
        print("Use 'kotilaitteet price-control --enable --mac <MAC>' to enable a device.")
        return 0

    for mac, entries in schedule.items():
        device = manager.get_device(mac)
        dname = device.name if device else mac
        print(f"\nSchedule for '{_color(dname, _BOLD)}' ({target_date}):\n")
        header = f"  {'Hour':<8} {'State':<6} {'Price (c/kWh)':<16} Reason"
        print(_color(header, _BOLD))
        print("  " + "-" * 70)
        for entry in entries:
            state = _state_str(entry.recommended_state)
            print(
                f"  {entry.hour:02d}:00   {state}   "
                f"{entry.price_cents_per_kwh:>8.2f}        {entry.reason}"
            )

    if args.apply:
        print("\nApplying schedule for current hour…")
        recs = current_recommendations(manager, prices)
        for rec in recs:
            d = rec["device"]
            if rec["recommended_state"]:
                manager.turn_on(d.mac_address)
                print(f"  {d.name}: {_state_str(True)}  ({rec['reason']})")
            else:
                manager.turn_off(d.mac_address)
                print(f"  {d.name}: {_state_str(False)}  ({rec['reason']})")
    return 0


def cmd_status(args: argparse.Namespace, manager: DeviceManager) -> int:
    """Show current status and price."""
    try:
        prices = fetch_prices()
        recs = current_recommendations(manager, prices)
    except RuntimeError:
        prices = []
        recs = []

    devices = manager.list_devices()
    print("\nDevice status:\n")
    _print_device_table(devices)

    if recs:
        print("\nCurrent recommendations:\n")
        for rec in recs:
            d = rec["device"]
            action = "Turn ON" if rec["recommended_state"] else "Turn OFF"
            print(f"  {d.name}: {action} – {rec['reason']}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_device(
    args: argparse.Namespace, manager: DeviceManager
) -> Optional[Device]:
    if hasattr(args, "mac") and args.mac:
        d = manager.get_device(args.mac.lower())
        if d is None:
            print(f"Device with MAC '{args.mac}' not found.")
        return d
    if hasattr(args, "name") and args.name:
        d = manager.get_device_by_name(args.name)
        if d is None:
            print(f"Device named '{args.name}' not found.")
        return d
    print("Provide --mac or --name to identify the device.")
    return None


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kotilaitteet",
        description="Kotilaitteet – Home device manager with electricity price control",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="Path to the device database file (default: ~/.kotilaitteet/devices.json)",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # -- scan --
    p_scan = sub.add_parser("scan", help="Scan WLAN for connected devices")
    p_scan.add_argument("--network", metavar="CIDR", help="Network to scan, e.g. 192.168.1.0/24")

    # -- list --
    sub.add_parser("list", help="List registered devices")

    # -- status --
    sub.add_parser("status", help="Show device status and current recommendations")

    # -- add --
    p_add = sub.add_parser("add", help="Register a device")
    p_add.add_argument("--name", required=True, help="Human-readable name")
    p_add.add_argument("--ip", required=True, help="IP address")
    p_add.add_argument("--mac", required=True, help="MAC address")
    p_add.add_argument("--type", metavar="TYPE", help="Device type (e.g. heater, washer)")
    p_add.add_argument("--notes", help="Optional notes")

    # -- remove --
    p_rem = sub.add_parser("remove", help="Remove a registered device")
    p_rem.add_argument("--mac", required=True, help="MAC address of device to remove")

    # -- on --
    p_on = sub.add_parser("on", help="Turn a device on")
    _add_device_identifier(p_on)

    # -- off --
    p_off = sub.add_parser("off", help="Turn a device off")
    _add_device_identifier(p_off)

    # -- toggle --
    p_tog = sub.add_parser("toggle", help="Toggle a device on/off")
    _add_device_identifier(p_tog)

    # -- prices --
    p_price = sub.add_parser("prices", help="Show today's electricity spot prices")
    p_price.add_argument(
        "--cheapest", type=int, metavar="N",
        help="Also highlight the N cheapest hours"
    )

    # -- price-control --
    p_pc = sub.add_parser("price-control", help="Configure price-based automation")
    _add_device_identifier(p_pc)
    p_pc.add_argument("--enable", action="store_true", default=False)
    p_pc.add_argument("--disable", dest="enable", action="store_false")
    p_pc.add_argument(
        "--hours", type=int, metavar="N",
        help="Minimum daily runtime in hours"
    )
    p_pc.add_argument(
        "--threshold", type=float, metavar="CENTS",
        help="Price threshold in c/kWh (device is off when price exceeds this)"
    )

    # -- schedule --
    p_sched = sub.add_parser("schedule", help="Show/apply price-based schedule")
    p_sched.add_argument(
        "--apply", action="store_true",
        help="Apply the schedule recommendation for the current hour"
    )

    return parser


def _add_device_identifier(p: argparse.ArgumentParser) -> None:
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--mac", help="MAC address")
    group.add_argument("--name", help="Device name")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_COMMAND_MAP = {
    "scan": cmd_scan,
    "list": cmd_list,
    "status": cmd_status,
    "add": cmd_add,
    "remove": cmd_remove,
    "on": cmd_on,
    "off": cmd_off,
    "toggle": cmd_toggle,
    "prices": cmd_prices,
    "price-control": cmd_price_control,
    "schedule": cmd_schedule,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manager = DeviceManager(db_path=args.db)
    handler = _COMMAND_MAP.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args, manager)


if __name__ == "__main__":
    sys.exit(main())
