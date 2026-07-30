"""Per-unit circular audio buffer.

A pre-allocated numpy int16 array with a monotonic write cursor, not a deque of
raw bytes -- both classify.py ("last N samples") and keywords.py (sequential
chunks) want array slices, and a byte-deque would force a concat + frombuffer
on every single read. Single writer (the event-loop thread), readers only ever
read behind write_pos, so no lock is needed -- worst case a reader spans a
write mid-flight at a wrap boundary and gets one stale 32ms slice inside a
much larger window, immaterial for audio classification.
"""
from __future__ import annotations

import numpy as np


class RingBuffer:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._buf = np.zeros(capacity, dtype=np.int16)
        self._cap = capacity
        self.write_pos = 0  # total samples ever written, monotonically increasing

    @property
    def capacity(self) -> int:
        return self._cap

    def write(self, samples: np.ndarray) -> None:
        n = len(samples)
        if n == 0:
            return
        if n > self._cap:
            # Only the tail matters if a single write is somehow larger than the
            # whole buffer -- keep the most recent capacity-worth of samples.
            samples = samples[-self._cap:]
            n = self._cap
        start = self.write_pos % self._cap
        end = start + n
        if end <= self._cap:
            self._buf[start:end] = samples
        else:
            first_len = self._cap - start
            self._buf[start:] = samples[:first_len]
            self._buf[: end - self._cap] = samples[first_len:]
        self.write_pos += n

    def read_last(self, n: int) -> np.ndarray | None:
        """Return the most recent n samples, or None if fewer than n have ever
        been written (startup pre-roll)."""
        if n > self._cap:
            raise ValueError(f"requested {n} samples exceeds buffer capacity {self._cap}")
        if self.write_pos < n:
            return None
        return self.read_range(self.write_pos - n, n)

    def read_range(self, start: int, n: int) -> np.ndarray:
        """Return n samples starting at absolute position `start`. Raises if the
        range has already been overwritten or hasn't been written yet."""
        if n > self._cap:
            raise ValueError(f"requested {n} samples exceeds buffer capacity {self._cap}")
        if start < 0:
            raise ValueError("start must be non-negative")
        end = start + n
        if end > self.write_pos:
            raise ValueError(f"range [{start}, {end}) is in the future (write_pos={self.write_pos})")
        if self.write_pos - start > self._cap:
            raise ValueError(f"range [{start}, {end}) has already been overwritten")
        buf_start = start % self._cap
        buf_end = buf_start + n
        if buf_end <= self._cap:
            return self._buf[buf_start:buf_end].copy()
        first_len = self._cap - buf_start
        return np.concatenate((self._buf[buf_start:], self._buf[: buf_end - self._cap]))
