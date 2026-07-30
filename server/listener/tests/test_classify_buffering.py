import asyncio
from unittest.mock import Mock

import numpy as np
import pytest

from listener.classify import FRAME_SAMPLES, HOP_SAMPLES, classify_unit_loop, score_events
from listener.config import EventConfig
from listener.hysteresis import EventRule
from listener.ingest import UnitState
from listener.ring_buffer import RingBuffer


def make_events():
    return {
        "doorbell": EventConfig("doorbell", threshold=0.5, class_indices=(1, 2), rule=EventRule(1, 1, 60), diagnostics_only=False, off_delay_s=15),
    }


def test_score_events_picks_max_across_class_indices():
    scores = np.zeros(521, dtype=np.float32)
    scores[1] = 0.3
    scores[2] = 0.9
    result = score_events(scores, make_events())
    assert result["doorbell"] == pytest.approx(0.9)


async def _run_loop_briefly(unit, model, hit_queue, events_cfg):
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    task = asyncio.create_task(classify_unit_loop(unit, model, executor, hit_queue, events_cfg))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    executor.shutdown(wait=False)


async def test_invoke_not_called_before_enough_samples():
    unit = UnitState(unit_id=1, room="kitchen", ring=RingBuffer(32000))
    model = Mock()
    model.invoke.return_value = np.zeros(521, dtype=np.float32)
    hit_queue = asyncio.Queue()

    # Write fewer samples than FRAME_SAMPLES -- invoke() must never be called.
    unit.ring.write(np.zeros(FRAME_SAMPLES - 100, dtype=np.int16))
    unit.classify_event.set()
    await _run_loop_briefly(unit, model, hit_queue, make_events())
    model.invoke.assert_not_called()


async def test_invoke_called_once_per_hop():
    unit = UnitState(unit_id=1, room="kitchen", ring=RingBuffer(32000))
    model = Mock()
    model.invoke.return_value = np.zeros(521, dtype=np.float32)
    hit_queue = asyncio.Queue()

    # write_pos == FRAME_SAMPLES (15600) crosses exactly 2 hop boundaries (7680, 15360)
    # before falling short of a 3rd (15600 - 15360 = 240 < HOP_SAMPLES).
    unit.ring.write(np.zeros(FRAME_SAMPLES, dtype=np.int16))
    unit.classify_event.set()
    await _run_loop_briefly(unit, model, hit_queue, make_events())
    assert model.invoke.call_count == 2


async def test_hit_emitted_when_threshold_crossed():
    unit = UnitState(unit_id=1, room="kitchen", ring=RingBuffer(32000))
    model = Mock()
    scores = np.zeros(521, dtype=np.float32)
    scores[1] = 0.99
    model.invoke.return_value = scores
    hit_queue = asyncio.Queue()

    unit.ring.write(np.zeros(FRAME_SAMPLES, dtype=np.int16))
    unit.classify_event.set()
    await _run_loop_briefly(unit, model, hit_queue, make_events())
    assert not hit_queue.empty()
    hit = hit_queue.get_nowait()
    assert hit.unit_id == 1
    assert hit.event == "doorbell"
    assert hit.score == pytest.approx(0.99)
