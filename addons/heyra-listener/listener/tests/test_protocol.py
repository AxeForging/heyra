import struct

import numpy as np

from listener import protocol


def _pack(magic, unit_id, flags, seq, ts, payload_bytes=b""):
    return struct.pack(protocol.HEADER_FMT, magic, unit_id, flags, seq, ts) + payload_bytes


def test_valid_full_packet():
    samples = np.arange(protocol.PAYLOAD_SAMPLES, dtype="<i2")
    data = _pack(protocol.MAGIC, 1, 0, 42, 12345, samples.tobytes())
    pkt = protocol.parse_packet(data)
    assert pkt is not None
    assert pkt.header.unit_id == 1
    assert pkt.header.seq == 42
    assert pkt.header.timestamp_ms == 12345
    assert not pkt.header.paused
    assert pkt.payload is not None
    assert np.array_equal(pkt.payload, samples)


def test_valid_paused_packet_has_no_payload():
    data = _pack(protocol.MAGIC, 1, protocol.FLAG_PAUSED, 7, 999)
    pkt = protocol.parse_packet(data)
    assert pkt is not None
    assert pkt.header.paused
    assert pkt.payload is None


def test_bad_magic_rejected():
    samples = np.zeros(protocol.PAYLOAD_SAMPLES, dtype="<i2")
    data = _pack(0xDEADBEEF, 1, 0, 0, 0, samples.tobytes())
    assert protocol.parse_packet(data) is None


def test_wrong_length_rejected():
    samples = np.zeros(protocol.PAYLOAD_SAMPLES, dtype="<i2")
    full = _pack(protocol.MAGIC, 1, 0, 0, 0, samples.tobytes())
    for bad in (full[:-1], full + b"\x00", full[: protocol.HEADER_LEN - 1], full[: protocol.HEADER_LEN + 1]):
        assert protocol.parse_packet(bad) is None
