"""Discovers Heyra units on the LAN via mDNS, so the Add-on can push a unit_id to a
device directly instead of requiring a separate visit to the device's own local page --
one place to set it, not two.

Modeled on esphome's own zeroconf.py (the same mechanism its dashboard uses for
"discovered devices"), reimplemented against the plain zeroconf package directly rather
than importing the full esphome package just for this one helper -- esphome was
deliberately dropped from this image (see Dockerfile/CLAUDE.md).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

log = logging.getLogger("heyra.discovery")

# Real ESPHome mDNS service type, confirmed against esphome/zeroconf.py's own
# ESPHOME_SERVICE_TYPE -- what esphome's own dashboard browses for "discovered devices".
SERVICE_TYPE = "_esphomelib._tcp.local."
# Matches firmware/common.yaml's esphome.name ("heyra-atom-echo") + name_add_mac_suffix
# -- filters out unrelated ESPHome devices on the same network advertising the same
# service type.
NAME_PREFIX = "heyra-atom-echo-"
MAC_SUFFIX_LEN = 6
_HEX_CHARS = set("0123456789abcdef")


def _is_heyra_device(device_name: str) -> bool:
    if not device_name.startswith(NAME_PREFIX):
        return False
    suffix = device_name[len(NAME_PREFIX):]
    return len(suffix) == MAC_SUFFIX_LEN and all(c in _HEX_CHARS for c in suffix)


@dataclass
class DiscoveredDevice:
    hostname: str  # e.g. "heyra-atom-echo-a1b2c3.local"


class Discovery:
    """Long-lived mDNS browser -- callback-updated, not a blocking per-request scan."""

    def __init__(self) -> None:
        self.devices: dict[str, DiscoveredDevice] = {}
        self._aiozc: AsyncZeroconf | None = None
        self._browser: AsyncServiceBrowser | None = None

    async def start(self) -> None:
        try:
            self._aiozc = AsyncZeroconf()
        except Exception:
            # Zeroconf init can raise OSError etc -- discovery is a nice-to-have on top
            # of the device-status view, not something that should crash the app.
            log.warning("mDNS discovery failed to start", exc_info=True)
            return
        self._browser = AsyncServiceBrowser(
            self._aiozc.zeroconf, SERVICE_TYPE, handlers=[self._on_change]
        )

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.async_cancel()
        if self._aiozc is not None:
            await self._aiozc.async_close()

    def _on_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        device_name = name.partition(".")[0]
        if not _is_heyra_device(device_name):
            return
        hostname = f"{device_name}.local"
        if state_change == ServiceStateChange.Removed:
            self.devices.pop(hostname, None)
        else:
            self.devices[hostname] = DiscoveredDevice(hostname=hostname)


discovery = Discovery()
