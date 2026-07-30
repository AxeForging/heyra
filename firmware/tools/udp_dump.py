#!/usr/bin/env python3
"""Phase 1 verification helper: dumps udp_audio_streamer packets and checks them
against the frozen packet format (see CLAUDE.md). Disposable diagnostic only --
not part of the Phase 2 server.
"""
import socket
import struct
import sys
import time

MAGIC = 0x41544D45
HEADER_FMT = "<IBBHI"  # magic, unit_id, flags, seq, timestamp_ms
HEADER_LEN = struct.calcsize(HEADER_FMT)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 6969
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    print(f"listening on UDP {port}")

    last_seq = None
    count = 0
    gaps = 0
    window_start = time.monotonic()

    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) < HEADER_LEN:
            print(f"short packet ({len(data)} bytes) from {addr}, ignoring")
            continue
        magic, unit_id, flags, seq, timestamp_ms = struct.unpack_from(HEADER_FMT, data, 0)
        if magic != MAGIC:
            print(f"bad magic {magic:#x} from {addr}, ignoring")
            continue

        if last_seq is not None and seq != (last_seq + 1) & 0xFFFF:
            gaps += 1
            print(f"seq gap: {last_seq} -> {seq}")
        last_seq = seq
        count += 1

        now = time.monotonic()
        if now - window_start >= 1.0:
            paused = "yes" if flags & 0x01 else "no"
            print(
                f"rate={count}/s unit={unit_id} seq={seq} paused={paused} "
                f"gaps_total={gaps} payload={len(data) - HEADER_LEN}B"
            )
            count = 0
            window_start = now


if __name__ == "__main__":
    main()
