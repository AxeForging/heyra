"""YAMNet sliding-window classification loop, one per unit.

The pre-converted single-shot .tflite classification model takes a fixed
[15600] float32 waveform (0.975s @ 16kHz) and returns one [521] score vector
per invoke() -- it does NOT do YAMNet's internal multi-frame windowing, so the
0.48s hop sliding window is implemented here at the application layer.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import Executor

import numpy as np
import tflite_runtime.interpreter as tflite

from listener.config import EventConfig
from listener.ingest import Hit, UnitState

log = logging.getLogger("listener.classify")

FRAME_SAMPLES = 15600  # YAMNet .tflite single-shot input: 0.975s @ 16kHz
HOP_SAMPLES = 7680  # 0.48s @ 16kHz


class YamnetModel:
    def __init__(self, model_path: str):
        self._interp = tflite.Interpreter(model_path=model_path)
        self._interp.allocate_tensors()
        self._input_index = self._interp.get_input_details()[0]["index"]
        self._output_index = self._interp.get_output_details()[0]["index"]

    def invoke(self, waveform: np.ndarray) -> np.ndarray:
        """waveform: float32[15600] in [-1, 1]. Returns float32[521] class scores."""
        self._interp.set_tensor(self._input_index, waveform)
        self._interp.invoke()
        return self._interp.get_tensor(self._output_index)[0]  # squeeze the [1, 521] batch dim


def score_events(scores: np.ndarray, events_cfg: dict[str, EventConfig]) -> dict[str, float]:
    return {
        name: float(scores[list(rule.class_indices)].max())
        for name, rule in events_cfg.items()
        if rule.class_indices
    }


async def classify_unit_loop(
    unit: UnitState,
    model: YamnetModel,
    executor: Executor,
    hit_queue: asyncio.Queue[Hit],
    events_cfg: dict[str, EventConfig],
) -> None:
    loop = asyncio.get_running_loop()
    last_pos = 0
    while True:
        await unit.classify_event.wait()
        unit.classify_event.clear()
        while unit.ring.write_pos - last_pos >= HOP_SAMPLES:
            last_pos += HOP_SAMPLES
            window = unit.ring.read_last(FRAME_SAMPLES)
            if window is None:
                continue  # startup pre-roll, not enough history yet
            waveform = window.astype(np.float32) / 32768.0
            try:
                scores = await loop.run_in_executor(executor, model.invoke, waveform)
            except Exception:
                log.exception("YAMNet invoke() failed for unit %d, skipping this window", unit.unit_id)
                continue
            ts = time.time()
            for event, score in score_events(scores, events_cfg).items():
                if score >= events_cfg[event].threshold:
                    hit_queue.put_nowait(Hit(unit.unit_id, event, score, ts))
