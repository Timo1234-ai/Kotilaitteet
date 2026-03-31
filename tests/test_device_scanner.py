"""Tests for device_scanner.py"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from kotilaitteet.device_scanner import (
    _lookup_vendor,
    _normalize_mac,
    _resolve_hostname,
    _scan_with_arp_table,
    scan_network,
)
from kotilaitteet.models import NetworkDevice


class TestNormalizeMac:
    def test_colon_format(self):
        assert _normalize_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"

    def test_dash_format(self):
        assert _normalize_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"

    def test_no_separator(self):
        assert _normalize_mac("AABBCCDDEEFF") == "aa:bb:cc:dd:ee:ff"

    def test_already_normalized(self):
        assert _normalize_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"


class TestLookupVendor:
    def test_known_vendor(self):
        # TP-Link OUI
        vendor = _lookup_vendor("50:c7:bf:00:00:00")
        assert vendor == "TP-Link"

    def test_unknown_vendor(self):
        vendor = _lookup_vendor("ff:ff:ff:ff:ff:ff")
        assert vendor == ""

    def test_raspberry_pi(self):
        vendor = _lookup_vendor("b8:27:3b:00:00:00")
        assert vendor == "Raspberry Pi"


class TestResolveHostname:
    def test_failure_returns_empty(self):
        # 192.0.2.1 is TEST-NET and will not resolve
        result = _resolve_hostname("192.0.2.1")
        assert result == ""


class TestScanWithArpTable:
    _SAMPLE_ARP_OUTPUT_LINUX = """\
Address                  HWtype  HWaddress           Flags Mask            Iface
192.168.1.1              ether   b0:be:76:aa:bb:cc   C                     eth0
192.168.1.50             ether   50:c7:bf:11:22:33   C                     eth0
"""

    _SAMPLE_ARP_OUTPUT_WIN = """\
Interface: 192.168.1.100 --- 0x3
  Internet Address      Physical Address      Type
  192.168.1.1           b0-be-76-aa-bb-cc     dynamic
  192.168.1.50          50-c7-bf-11-22-33     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
"""

    def test_parses_linux_arp(self):
        mock_result = MagicMock()
        mock_result.stdout = self._SAMPLE_ARP_OUTPUT_LINUX
        with (
            patch("subprocess.run", return_value=mock_result),
            patch("kotilaitteet.device_scanner.socket.gethostbyaddr", side_effect=OSError),
        ):
            devices = _scan_with_arp_table()
        assert len(devices) == 2
        ips = {d.ip_address for d in devices}
        assert "192.168.1.1" in ips
        assert "192.168.1.50" in ips

    def test_skips_broadcast(self):
        mock_result = MagicMock()
        mock_result.stdout = self._SAMPLE_ARP_OUTPUT_WIN
        with (
            patch("subprocess.run", return_value=mock_result),
            patch("kotilaitteet.device_scanner.socket.gethostbyaddr", side_effect=OSError),
        ):
            devices = _scan_with_arp_table()
        ips = {d.ip_address for d in devices}
        assert "192.168.1.255" not in ips

    def test_handles_subprocess_failure(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            devices = _scan_with_arp_table()
        assert devices == []


class TestScanNetwork:
    def test_falls_back_to_arp_when_nmap_unavailable(self):
        mock_nd = NetworkDevice(
            ip_address="192.168.1.10",
            mac_address="aa:bb:cc:dd:ee:ff",
        )
        with (
            patch("kotilaitteet.device_scanner._scan_with_nmap", return_value=[]),
            patch("kotilaitteet.device_scanner._ping_sweep"),
            patch("kotilaitteet.device_scanner._scan_with_arp_table", return_value=[mock_nd]),
        ):
            result = scan_network("192.168.1.0/24")
        assert len(result) == 1
        assert result[0].ip_address == "192.168.1.10"

    def test_uses_nmap_when_available(self):
        mock_nd = NetworkDevice(
            ip_address="192.168.1.5",
            mac_address="11:22:33:44:55:66",
        )
        with patch("kotilaitteet.device_scanner._scan_with_nmap", return_value=[mock_nd]):
            result = scan_network("192.168.1.0/24")
        assert len(result) == 1
        assert result[0].ip_address == "192.168.1.5"

    def test_auto_detect_network(self):
        """scan_network with no args should auto-detect and not raise."""
        with (
            patch("kotilaitteet.device_scanner._get_local_network", return_value="192.168.1.0/24"),
            patch("kotilaitteet.device_scanner._scan_with_nmap", return_value=[]),
            patch("kotilaitteet.device_scanner._ping_sweep"),
            patch("kotilaitteet.device_scanner._scan_with_arp_table", return_value=[]),
        ):
            result = scan_network()
        assert isinstance(result, list)
