import asyncio
import json

from listener.healthz import start_healthz_server
from listener.ingest import EventRecord, UnitState, new_event_log
from listener.ring_buffer import RingBuffer


async def test_healthz_returns_snapshot():
    unit = UnitState(unit_id=1, room="kitchen", ring=RingBuffer(32000))
    unit.online = True
    unit.packets_total = 5
    units = {1: unit}
    event_log = new_event_log()
    event_log.append(EventRecord(unit_id=1, room="kitchen", event="baby_cry", score=0.9, ts=1234.5))

    server = await start_healthz_server(units, event_log, host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
        await writer.drain()
        status_line = await reader.readline()
        assert b"200" in status_line
        headers = b""
        while (line := await reader.readline()) not in (b"\r\n", b""):
            headers += line
        body = await reader.read()
        data = json.loads(body)
        assert data["status"] == "ok"
        assert data["units"]["1"]["room"] == "kitchen"
        assert data["units"]["1"]["online"] is True
        assert data["units"]["1"]["packets_total"] == 5
        assert data["events"] == [{"unit_id": 1, "room": "kitchen", "event": "baby_cry", "score": 0.9, "ts": 1234.5}]
        writer.close()
    finally:
        server.close()
        await server.wait_closed()
