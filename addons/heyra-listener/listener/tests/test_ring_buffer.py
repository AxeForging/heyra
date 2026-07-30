import numpy as np
import pytest

from listener.ring_buffer import RingBuffer


def test_read_last_none_before_enough_data():
    rb = RingBuffer(capacity=100)
    rb.write(np.arange(50, dtype=np.int16))
    assert rb.read_last(60) is None
    assert rb.read_last(50) is not None


def test_write_and_read_last_matches():
    rb = RingBuffer(capacity=100)
    rb.write(np.arange(30, dtype=np.int16))
    got = rb.read_last(30)
    assert np.array_equal(got, np.arange(30, dtype=np.int16))


def test_wrap_boundary():
    rb = RingBuffer(capacity=10)
    rb.write(np.arange(8, dtype=np.int16))  # 0..7, write_pos=8
    rb.write(np.array([100, 101, 102], dtype=np.int16))  # wraps: write_pos=11
    # last 5 samples written were [5,6,7,100,101,102][-5:] = [6,7,100,101,102]
    got = rb.read_last(5)
    assert np.array_equal(got, np.array([6, 7, 100, 101, 102], dtype=np.int16))


def test_read_range_sequential():
    rb = RingBuffer(capacity=20)
    rb.write(np.arange(20, dtype=np.int16))
    assert np.array_equal(rb.read_range(0, 5), np.arange(0, 5, dtype=np.int16))
    assert np.array_equal(rb.read_range(5, 5), np.arange(5, 10, dtype=np.int16))


def test_read_range_future_raises():
    rb = RingBuffer(capacity=20)
    rb.write(np.arange(10, dtype=np.int16))
    with pytest.raises(ValueError):
        rb.read_range(5, 10)  # end=15 > write_pos=10


def test_read_range_overwritten_raises():
    rb = RingBuffer(capacity=10)
    # Realistic usage: many small writes, not one write bigger than capacity.
    for _ in range(5):
        rb.write(np.arange(5, dtype=np.int16))  # write_pos=25, only last 10 retained
    with pytest.raises(ValueError):
        rb.read_range(0, 5)  # long gone
