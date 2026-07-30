"""Pure hit-gate: N hits within a window fires, then a cooldown before it can
fire again. No asyncio, no network, no I/O -- mqtt_out.py wraps this with the
actual MQTT publish.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class EventRule:
    hits: int
    window_s: float
    cooldown_s: float


class HysteresisGate:
    def __init__(
        self,
        rules: dict[tuple[int, str], EventRule],
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self._rules = rules
        self._now = now_fn
        self._hits: dict[tuple[int, str], list[float]] = defaultdict(list)
        self._last_fired: dict[tuple[int, str], float] = {}

    def record_hit(self, key: tuple[int, str], ts: float | None = None) -> bool:
        """Record a raw hit for (unit_id, event). Returns True iff this hit
        causes the event to fire right now (hit-count threshold met within the
        window, and cooldown since the last fire has elapsed)."""
        ts = self._now() if ts is None else ts
        rule = self._rules[key]
        hits = self._hits[key]
        hits.append(ts)

        cutoff = ts - rule.window_s
        while hits and hits[0] < cutoff:
            hits.pop(0)

        if len(hits) < rule.hits:
            return False
        if ts - self._last_fired.get(key, -math.inf) < rule.cooldown_s:
            return False

        self._last_fired[key] = ts
        hits.clear()
        return True
