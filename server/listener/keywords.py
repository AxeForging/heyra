"""openWakeWord keyword-spotting loop, one per unit.

Unlike classify.py, chunks here must be consumed strictly sequentially and
non-overlapping -- openWakeWord maintains internal streaming melspectrogram/
embedding state across predict() calls, so skipping ahead (classify.py's
graceful-degradation trick) would corrupt that state instead of just losing
a little freshness.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import Executor

import numpy as np
import openwakeword

from listener.config import EventConfig
from listener.ingest import Hit, UnitState

log = logging.getLogger("listener.keywords")

CHUNK_SAMPLES = 1280  # 80ms @ 16kHz, openWakeWord's native chunk size


class KeywordSpotter:
    def __init__(self, model_path: str, inference_framework: str = "tflite"):
        self._model_path = model_path
        self._inference_framework = inference_framework
        self._model = self._new_model()

    def _new_model(self) -> "openwakeword.Model":
        return openwakeword.Model(wakeword_models=[self._model_path], inference_framework=self._inference_framework)

    def predict(self, chunk: np.ndarray) -> dict[str, float]:
        return self._model.predict(chunk)

    def reset(self) -> None:
        """Discard internal streaming state and start fresh -- cheaper and safer
        than trying to replay a gap after falling behind the ring buffer."""
        self._model = self._new_model()


async def keyword_unit_loop(
    unit: UnitState,
    spotter: KeywordSpotter,
    executor: Executor,
    hit_queue: asyncio.Queue[Hit],
    cfg: EventConfig,
) -> None:
    loop = asyncio.get_running_loop()
    last_pos = 0
    while True:
        await unit.keyword_event.wait()
        unit.keyword_event.clear()
        while unit.ring.write_pos - last_pos >= CHUNK_SAMPLES:
            try:
                chunk = unit.ring.read_range(last_pos, CHUNK_SAMPLES)
            except ValueError:
                log.warning("unit %d fell behind the ring buffer, resyncing keyword spotter", unit.unit_id)
                last_pos = unit.ring.write_pos - CHUNK_SAMPLES
                spotter.reset()
                continue
            last_pos += CHUNK_SAMPLES
            try:
                scores = await loop.run_in_executor(executor, spotter.predict, chunk)
            except Exception:
                log.exception("openWakeWord predict() failed for unit %d, skipping this chunk", unit.unit_id)
                continue
            ts = time.time()
            if max(scores.values(), default=0.0) >= cfg.threshold:
                hit_queue.put_nowait(Hit(unit.unit_id, cfg.name, max(scores.values()), ts))
