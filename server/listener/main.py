"""Entry point: python -m listener.main. Wires ingest, classify, keywords,
mqtt_out, and healthz together per config.yaml.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from listener.classify import YamnetModel, classify_unit_loop
from listener.config import load_config
from listener.debug_wav import debug_wav_loop
from listener.healthz import start_healthz_server
from listener.hysteresis import HysteresisGate
from listener.ingest import Hit, IngestProtocol, UnitState, health_sweep_loop
from listener.keywords import KeywordSpotter, keyword_unit_loop
from listener.mqtt_out import MqttPublisher, hit_consumer_loop
from listener.ring_buffer import RingBuffer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("listener.main")

CONFIG_PATH = os.environ.get("HEYRA_CONFIG", "/app/config.yaml")


async def main() -> None:
    config = load_config(CONFIG_PATH)
    log.info("loaded config: %d unit(s), %d event(s)", len(config.units), len(config.events))

    ring_capacity = int(config.ingest.ring_seconds * 16000)
    units: dict[int, UnitState] = {
        unit_id: UnitState(unit_id=unit_id, room=room, ring=RingBuffer(ring_capacity))
        for unit_id, room in config.units.items()
    }
    room_lookup = dict(config.units)
    all_events = dict(config.events)
    for kw in config.keyword_spotting:
        all_events[kw.event.name] = kw.event

    executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
    hit_queue: asyncio.Queue[Hit] = asyncio.Queue()
    gate = HysteresisGate(config.gate_rules)

    publisher = MqttPublisher(
        config.mqtt.host, config.mqtt.port, config.mqtt.client_id, config.mqtt.discovery_prefix
    )

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: IngestProtocol(units),
        local_addr=(config.ingest.bind_host, config.ingest.port),
    )
    log.info("listening for UDP audio on %s:%d", config.ingest.bind_host, config.ingest.port)

    await start_healthz_server(units, port=config.healthz.port)
    log.info("healthz listening on :%d", config.healthz.port)

    yamnet_model = YamnetModel(config.yamnet_model_path)
    tasks = [
        asyncio.create_task(publisher.run()),
        asyncio.create_task(health_sweep_loop(units, publisher, config.ingest.offline_timeout_s)),
        asyncio.create_task(hit_consumer_loop(hit_queue, gate, publisher, room_lookup, all_events)),
    ]
    for unit in units.values():
        tasks.append(asyncio.create_task(classify_unit_loop(unit, yamnet_model, executor, hit_queue, config.events)))
        for kw in config.keyword_spotting:
            if not kw.enabled:
                continue
            if not os.path.exists(kw.model_path):
                log.warning("keyword model for '%s' not found at %s, skipping -- see docs/wake-word-training.md",
                            kw.event.name, kw.model_path)
                continue
            spotter = KeywordSpotter(kw.model_path, kw.inference_framework)
            tasks.append(asyncio.create_task(keyword_unit_loop(unit, spotter, executor, hit_queue, kw.event)))
    if config.debug.enabled:
        tasks.append(asyncio.create_task(debug_wav_loop(units, config.debug.output_dir, config.debug.rotate_seconds)))
        log.warning("debug WAV capture enabled -- writing rolling audio to %s", config.debug.output_dir)

    # Give the MQTT connection a moment to establish before publishing discovery.
    await asyncio.sleep(2)
    await publisher.publish_all_discovery(config)
    log.info("published HA discovery configs")

    try:
        transport_task = asyncio.Event()
        await transport_task.wait()  # run forever
    finally:
        transport.close()
        executor.shutdown(wait=False)
        for t in tasks:
            t.cancel()


if __name__ == "__main__":
    asyncio.run(main())
