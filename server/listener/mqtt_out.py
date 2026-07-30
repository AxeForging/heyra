"""Async MQTT publish + HA discovery. Thin wrapper around HysteresisGate --
hit_consumer_loop is the only place gating and publishing meet.
"""
from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt

from listener.config import Config, EventConfig
from listener.hysteresis import HysteresisGate
from listener.ingest import Hit

log = logging.getLogger("listener.mqtt_out")


class MqttPublisher:
    def __init__(self, host: str, port: int, client_id: str, discovery_prefix: str):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.discovery_prefix = discovery_prefix
        self._client: aiomqtt.Client | None = None

    async def run(self) -> None:
        """Reconnect loop. This instance only publishes, never subscribes."""
        while True:
            try:
                async with aiomqtt.Client(self.host, self.port, identifier=self.client_id) as client:
                    self._client = client
                    log.info("connected to mqtt %s:%d", self.host, self.port)
                    await asyncio.Event().wait()  # idle until cancelled or connection drops
            except aiomqtt.MqttError as e:
                log.warning("mqtt connection error: %s, retrying in 5s", e)
                self._client = None
                await asyncio.sleep(5)

    async def _publish(self, topic: str, payload: dict | str, retain: bool = False) -> None:
        if self._client is None:
            log.debug("mqtt not connected yet, dropping publish to %s", topic)
            return
        body = json.dumps(payload) if isinstance(payload, dict) else payload
        await self._client.publish(topic, body, retain=retain)

    async def publish_event(self, room: str, payload: dict) -> None:
        await self._publish(f"acoustic/{room}/event", payload, retain=False)

    async def publish_status(self, room: str, status: str) -> None:
        await self._publish(f"acoustic/{room}/status", status, retain=True)

    async def publish_diag(self, room: str, subtopic: str, payload: dict) -> None:
        await self._publish(f"acoustic/diag/{room}/{subtopic}", payload, retain=False)

    async def publish_discovery(self, room: str, event_name: str, cfg: EventConfig) -> None:
        unique_id = f"heyra_{room}_{event_name}"
        discovery_payload = {
            "name": f"{room.title()} {event_name.replace('_', ' ').title()}",
            "unique_id": unique_id,
            "state_topic": f"acoustic/{room}/event",
            "value_template": (
                "{{ 'ON' if value_json.event == '" + event_name + "' else this.state }}"
            ),
            "payload_on": "ON",
            "payload_off": "OFF",
            "off_delay": cfg.off_delay_s,
            "availability_topic": f"acoustic/{room}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": {
                "identifiers": [f"heyra_{room}"],
                "name": f"Heyra {room.title()}",
                "manufacturer": "Heyra",
            },
        }
        topic = f"{self.discovery_prefix}/binary_sensor/{unique_id}/config"
        await self._publish(topic, discovery_payload, retain=True)

    async def publish_status_sensor_discovery(self, room: str) -> None:
        """Plain sensor mirroring the raw online/offline/paused status string --
        'paused' doesn't fit binary_sensor's available/not_available semantics."""
        unique_id = f"heyra_{room}_status"
        payload = {
            "name": f"{room.title()} Status",
            "unique_id": unique_id,
            "state_topic": f"acoustic/{room}/status",
            "device": {"identifiers": [f"heyra_{room}"], "name": f"Heyra {room.title()}", "manufacturer": "Heyra"},
        }
        await self._publish(f"{self.discovery_prefix}/sensor/{unique_id}/config", payload, retain=True)

    async def publish_all_discovery(self, config: Config) -> None:
        all_events = dict(config.events)
        all_events[config.keyword_spotting.event.name] = config.keyword_spotting.event
        for room in set(config.units.values()):
            await self.publish_status_sensor_discovery(room)
            for event_name, cfg in all_events.items():
                if cfg.diagnostics_only:
                    continue  # log-only events (e.g. thump) never get a discovery entity
                await self.publish_discovery(room, event_name, cfg)


async def hit_consumer_loop(
    hit_queue: asyncio.Queue[Hit],
    gate: HysteresisGate,
    publisher: MqttPublisher,
    room_lookup: dict[int, str],
    events_cfg: dict[str, EventConfig],
) -> None:
    while True:
        hit = await hit_queue.get()
        if gate.record_hit((hit.unit_id, hit.event)):
            room = room_lookup.get(hit.unit_id)
            if room is None:
                log.warning("hit for unknown unit_id=%d, dropping", hit.unit_id)
                continue
            cfg = events_cfg[hit.event]
            payload = {"event": hit.event, "score": hit.score, "unit_id": hit.unit_id, "ts": hit.ts}
            if cfg.diagnostics_only:
                await publisher.publish_diag(room, hit.event, payload)
            else:
                await publisher.publish_event(room, payload)
