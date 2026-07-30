from listener.hysteresis import EventRule, HysteresisGate


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def advance(self, dt):
        self.t += dt

    def __call__(self):
        return self.t


def make_gate(hits=3, window_s=10.0, cooldown_s=60.0, clock=None):
    clock = clock or FakeClock()
    rules = {(1, "baby_cry"): EventRule(hits=hits, window_s=window_s, cooldown_s=cooldown_s)}
    return HysteresisGate(rules, now_fn=clock), clock


def test_fires_once_hit_threshold_reached():
    gate, clock = make_gate(hits=3, window_s=10)
    key = (1, "baby_cry")
    assert gate.record_hit(key) is False
    clock.advance(1)
    assert gate.record_hit(key) is False
    clock.advance(1)
    assert gate.record_hit(key) is True


def test_hits_spread_beyond_window_never_fire():
    gate, clock = make_gate(hits=3, window_s=10)
    key = (1, "baby_cry")
    assert gate.record_hit(key) is False
    clock.advance(20)  # first hit expires out of the window
    assert gate.record_hit(key) is False
    clock.advance(1)
    assert gate.record_hit(key) is False  # only 2 hits within the last 10s


def test_cooldown_blocks_immediate_refire():
    gate, clock = make_gate(hits=1, window_s=10, cooldown_s=60)
    key = (1, "baby_cry")
    assert gate.record_hit(key) is True
    clock.advance(5)
    assert gate.record_hit(key) is False  # still within cooldown


def test_fires_again_after_cooldown_elapses():
    gate, clock = make_gate(hits=1, window_s=10, cooldown_s=60)
    key = (1, "baby_cry")
    assert gate.record_hit(key) is True
    clock.advance(61)
    assert gate.record_hit(key) is True


def test_single_hit_rule_fires_immediately():
    gate, clock = make_gate(hits=1, window_s=1, cooldown_s=60)
    key = (1, "baby_cry")
    assert gate.record_hit(key) is True
