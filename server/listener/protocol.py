"""Parsing for the frozen udp_audio_streamer wire format (see repo root CLAUDE.md).

Zero asyncio/network here -- pure bytes-in, dataclass-out. Mirrors the same
struct pattern already used by firmware/tools/udp_dump.py.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

MAGIC = 0x41544D45
HEADER_FMT = "<IBBHI"  # magic, unit_id, flags, seq, timestamp_ms
HEADER_LEN = struct.calcsize(HEADER_FMT)  # 12
PAYLOAD_SAMPLES = 512
PAYLOAD_BYTES = PAYLOAD_SAMPLES * 2  # 1024
FLAG_PAUSED = 0x01


@dataclass(frozen=True)
class Header:
    unit_id: int
    flags: int
    seq: int
    timestamp_ms: int

    @property
    def paused(self) -> bool:
        return bool(self.flags & FLAG_PAUSED)


@dataclass(frozen=True)
class Packet:
    header: Header
    payload: np.ndarray | None  # int16[512], or None for paused header-only packets


def parse_packet(data: bytes) -> Packet | None:
    """Parse one UDP datagram. Returns None on bad magic or an unexpected length --
    fails closed rather than trying to salvage a malformed packet."""
    if len(data) not in (HEADER_LEN, HEADER_LEN + PAYLOAD_BYTES):
        return None
    magic, unit_id, flags, seq, timestamp_ms = struct.unpack_from(HEADER_FMT, data, 0)
    if magic != MAGIC:
        return None
    payload = None
    if len(data) == HEADER_LEN + PAYLOAD_BYTES:
        payload = np.frombuffer(data, dtype="<i2", count=PAYLOAD_SAMPLES, offset=HEADER_LEN)
    return Packet(Header(unit_id, flags, seq, timestamp_ms), payload)
