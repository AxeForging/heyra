"""Run with: pytest addons/heyra/ (needs zeroconf installed)."""
from unittest.mock import Mock

from zeroconf import ServiceStateChange

from app.discovery import Discovery, _is_heyra_device


def test_is_heyra_device_matches_name_plus_mac_suffix():
    assert _is_heyra_device("heyra-atom-echo-a1b2c3")


def test_is_heyra_device_rejects_wrong_prefix():
    assert not _is_heyra_device("some-other-esphome-device-a1b2c3")


def test_is_heyra_device_rejects_wrong_suffix_length():
    assert not _is_heyra_device("heyra-atom-echo-a1b2c")


def test_is_heyra_device_rejects_non_hex_suffix():
    assert not _is_heyra_device("heyra-atom-echo-zzzzzz")


def test_discovery_adds_device_on_service_added():
    d = Discovery()
    d._on_change(Mock(), "_esphomelib._tcp.local.", "heyra-atom-echo-a1b2c3.local.", ServiceStateChange.Added)
    assert "heyra-atom-echo-a1b2c3.local" in d.devices


def test_discovery_removes_device_on_service_removed():
    d = Discovery()
    d._on_change(Mock(), "_esphomelib._tcp.local.", "heyra-atom-echo-a1b2c3.local.", ServiceStateChange.Added)
    d._on_change(Mock(), "_esphomelib._tcp.local.", "heyra-atom-echo-a1b2c3.local.", ServiceStateChange.Removed)
    assert "heyra-atom-echo-a1b2c3.local" not in d.devices


def test_discovery_ignores_unrelated_esphome_devices():
    d = Discovery()
    d._on_change(Mock(), "_esphomelib._tcp.local.", "some-other-device-a1b2c3.local.", ServiceStateChange.Added)
    assert d.devices == {}
