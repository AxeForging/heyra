import struct

import numpy as np
import pytest

from listener import protocol
from listener.ingest import IngestProtocol, UnitState, is_offline
from listener.ring_buffer import RingBuffer


def make_unit(unit_id=1, room="kitchen", capacity=32000):
    return UnitState(unit_id=unit_id, room=room, ring=RingBuffer(capacity))


def pack(unit_id, flags, seq, ts=0, with_payload=True):
    payload = np.zeros(protocol.PAYLOAD_SAMPLES, dtype="<i2").tobytes() if with_payload else b""
    return struct.pack(protocol.HEADER_FMT, protocol.MAGIC, unit_id, flags, seq, ts) + payload


def test_is_offline_pure():
    assert is_offline(last_seen=0.0, now=10.0, timeout_s=5.0) is True
    assert is_offline(last_seen=8.0, now=10.0, timeout_s=5.0) is False


def test_datagram_received_updates_unit_and_sets_events():
    unit = make_unit()
    proto = IngestProtocol({1: unit})
    proto.datagram_received(pack(1, 0, seq=0), ("1.2.3.4", 1234))
    assert unit.packets_total == 1
    assert unit.gap_count == 0
    assert unit.last_seq == 0
    assert unit.classify_event.is_set()
    assert unit.keyword_event.is_set()
    assert unit.ring.write_pos == protocol.PAYLOAD_SAMPLES


def test_seq_gap_detected():
    unit = make_unit()
    proto = IngestProtocol({1: unit})
    proto.datagram_received(pack(1, 0, seq=5), ("h", 1))
    proto.datagram_received(pack(1, 0, seq=8), ("h", 1))  # expected 6, got 8 -> 2 missed
    assert unit.gap_count == 2


def test_seq_wraparound_not_counted_as_gap():
    unit = make_unit()
    proto = IngestProtocol({1: unit})
    proto.datagram_received(pack(1, 0, seq=65535), ("h", 1))
    proto.datagram_received(pack(1, 0, seq=0), ("h", 1))  # correct wraparound continuation
    assert unit.gap_count == 0


def test_paused_packet_sets_paused_and_does_not_touch_ring():
    unit = make_unit()
    proto = IngestProtocol({1: unit})
    before = unit.ring.write_pos
    proto.datagram_received(pack(1, protocol.FLAG_PAUSED, seq=0, with_payload=False), ("h", 1))
    assert unit.paused is True
    assert unit.ring.write_pos == before
    assert not unit.classify_event.is_set()  # no payload -> no wakeup


def test_unknown_unit_id_ignored():
    unit = make_unit(unit_id=1)
    proto = IngestProtocol({1: unit})
    proto.datagram_received(pack(99, 0, seq=0), ("h", 1))  # not in units dict
    assert unit.packets_total == 0


def test_malformed_packet_ignored():
    unit = make_unit()
    proto = IngestProtocol({1: unit})
    proto.datagram_received(b"garbage", ("h", 1))
    assert unit.packets_total == 0
