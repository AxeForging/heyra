"""UDP ingest: demuxes packets by unit_id into per-unit ring buffers, tracks
health (seq gaps, online/offline/paused), and wakes classify/keyword consumers.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field

from listener import protocol
from listener.protocol import Packet
from listener.ring_buffer import RingBuffer

log = logging.getLogger("listener.ingest")

# Recent-events window for the Ingress panel's event log -- in-memory only, not a
# permanent history store (Home Assistant's own Logbook already retains that per
# entity). 200 is generous for a "what just happened" feed without unbounded growth.
EVENT_LOG_MAXLEN = 200


@dataclass
class Hit:
    """A raw event candidate produced by classify.py or keywords.py, before
    hysteresis gating. ts is wall-clock (time.time()), meaningful to humans/HA."""
    unit_id: int
    event: str
    score: float
    ts: float


@dataclass
class EventRecord:
    """A gated hit that actually got published (past hysteresis) -- what the Ingress
    panel's event log shows. room is resolved once at record time so the UI never
    needs to cross-reference unit_id -> room itself."""
    unit_id: int
    room: str
    event: str
    score: float
    ts: float


def new_event_log() -> deque[EventRecord]:
    return deque(maxlen=EVENT_LOG_MAXLEN)


@dataclass
class UnitState:
    unit_id: int
    room: str
    ring: RingBuffer
    classify_event: asyncio.Event = field(default_factory=asyncio.Event)
    keyword_event: asyncio.Event = field(default_factory=asyncio.Event)
    last_seq: int | None = None
    last_packet_monotonic: float = -math.inf
    packets_total: int = 0
    gap_count: int = 0
    paused: bool = False
    online: bool = False
    last_published_status: str | None = None

    def record_packet(self, pkt: Packet) -> None:
        self.packets_total += 1
        self.last_packet_monotonic = time.monotonic()
        self.paused = pkt.header.paused

        seq = pkt.header.seq
        if self.last_seq is not None:
            expected = (self.last_seq + 1) & 0xFFFF
            if seq != expected:
                # Wrap-safe count of how many packets were actually missed.
                self.gap_count += (seq - expected) & 0xFFFF
        self.last_seq = seq

        if pkt.payload is not None:
            self.ring.write(pkt.payload)
            self.classify_event.set()
            self.keyword_event.set()

    def status(self) -> str:
        if not self.online:
            return "offline"
        return "paused" if self.paused else "online"


def is_offline(last_seen: float, now: float, timeout_s: float) -> bool:
    return (now - last_seen) > timeout_s


class IngestProtocol(asyncio.DatagramProtocol):
    def __init__(self, units: dict[int, UnitState]):
        self.units = units
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        pkt = protocol.parse_packet(data)
        if pkt is None:
            log.debug("dropped malformed packet from %s (%d bytes)", addr, len(data))
            return
        unit = self.units.get(pkt.header.unit_id)
        if unit is None:
            log.warning("packet from unknown unit_id=%d (%s), not in config.yaml", pkt.header.unit_id, addr)
            return
        unit.record_packet(pkt)

    def error_received(self, exc: Exception) -> None:
        log.warning("UDP socket error: %s", exc)


async def health_sweep_loop(units: dict[int, UnitState], publisher, offline_timeout_s: float, interval_s: float = 1.0) -> None:
    while True:
        await asyncio.sleep(interval_s)
        now = time.monotonic()
        for unit in units.values():
            unit.online = not is_offline(unit.last_packet_monotonic, now, offline_timeout_s)
            status = unit.status()
            if status != unit.last_published_status:
                unit.last_published_status = status
                await publisher.publish_status(unit.room, status)
