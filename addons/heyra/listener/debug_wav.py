"""Opt-in rolling debug WAV capture. Disabled by default -- no audio is ever
persisted to disk unless debug.enabled: true in config.yaml. Overwrites the
previous file each rotation (a rolling window, not an accumulating archive).
"""
from __future__ import annotations

import asyncio
import logging
import os
import wave

from listener.ingest import UnitState
from listener.ring_buffer import RingBuffer

log = logging.getLogger("listener.debug_wav")

SAMPLE_RATE = 16000
# Must be well under the hot-path ring's retention (ingest.ring_seconds, default 2.0s)
# so no audio is ever missed between mirror ticks.
MIRROR_INTERVAL_S = 1.0


class DebugWavRotator:
    def __init__(self, unit: UnitState, output_dir: str, rotate_seconds: float):
        self.unit = unit
        self.output_dir = output_dir
        self.ring = RingBuffer(capacity=int(rotate_seconds * SAMPLE_RATE))
        self._mirrored_pos = unit.ring.write_pos

    def mirror_new_samples(self) -> None:
        hot = self.unit.ring
        available = hot.write_pos - self._mirrored_pos
        if available <= 0:
            return
        # If we've fallen behind the hot ring's own retention, we've already lost
        # that audio -- just resync forward rather than raising.
        if available > hot.capacity:
            self._mirrored_pos = hot.write_pos - hot.capacity
            available = hot.capacity
        self.ring.write(hot.read_range(self._mirrored_pos, available))
        self._mirrored_pos += available

    def write_window(self) -> None:
        window = self.ring.read_last(self.ring.capacity)
        if window is None:
            return  # not enough audio captured yet since startup
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"unit_{self.unit.unit_id}.wav")
        tmp_path = path + ".tmp"
        with wave.open(tmp_path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(SAMPLE_RATE)
            f.writeframes(window.tobytes())
        os.replace(tmp_path, path)  # atomic swap, no reader ever sees a partial file


async def debug_wav_loop(units: dict[int, UnitState], output_dir: str, rotate_seconds: float) -> None:
    rotators = {uid: DebugWavRotator(u, output_dir, rotate_seconds) for uid, u in units.items()}
    elapsed = 0.0
    while True:
        await asyncio.sleep(MIRROR_INTERVAL_S)
        elapsed += MIRROR_INTERVAL_S
        for rotator in rotators.values():
            rotator.mirror_new_samples()
        if elapsed >= rotate_seconds:
            elapsed = 0.0
            for rotator in rotators.values():
                rotator.write_window()
