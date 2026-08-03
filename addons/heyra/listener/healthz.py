"""Hand-rolled minimal HTTP server for GET /healthz. One static-shape JSON
route doesn't justify pulling in fastapi/uvicorn on top of the ML stack
already in this image.
"""
from __future__ import annotations

import asyncio
import json
import time

from collections import deque

from listener.ingest import EventRecord, UnitState


def build_snapshot(units: dict[int, UnitState], event_log: "deque[EventRecord]" = ()) -> dict:
    now = time.monotonic()
    return {
        "status": "ok",
        "units": {
            str(u.unit_id): {
                "room": u.room,
                "online": u.online,
                "paused": u.paused,
                "last_packet_age_s": round(now - u.last_packet_monotonic, 2) if u.packets_total else None,
                "packets_total": u.packets_total,
                "gap_count": u.gap_count,
            }
            for u in units.values()
        },
        "events": [
            {"unit_id": e.unit_id, "room": e.room, "event": e.event, "score": e.score, "ts": e.ts}
            for e in event_log
        ],
    }


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, snapshot_fn) -> None:
    try:
        try:
            await asyncio.wait_for(reader.readline(), timeout=2.0)  # request line, contents unused
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                if line in (b"\r\n", b"\n", b""):
                    break
        except (asyncio.TimeoutError, ConnectionError):
            return
        body = json.dumps(snapshot_fn()).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: %d\r\n"
            b"Connection: close\r\n\r\n%b" % (len(body), body)
        )
        await writer.drain()
    finally:
        writer.close()


async def start_healthz_server(
    units: dict[int, UnitState],
    event_log: "deque[EventRecord]" = (),
    host: str = "0.0.0.0",
    port: int = 8080,
) -> asyncio.AbstractServer:
    return await asyncio.start_server(lambda r, w: _handle(r, w, lambda: build_snapshot(units, event_log)), host, port)
