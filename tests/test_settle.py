"""Tests for screen-settle detection after taps."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from staminabuyer.settle import ScreenSettler, changed_fraction, frame_signature


def _png(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return buf.tobytes()


def _screen(cards: int = 0, flicker: bool = False) -> bytes:
    """Synthetic 320×480 'market': ``cards`` selects which card layout is shown,
    ``flicker`` toggles a small ambient-animation patch."""
    image = np.full((480, 320, 3), 40, dtype=np.uint8)
    if cards:
        rng = np.random.default_rng(cards)
        image[80:400, 20:300] = rng.integers(0, 255, size=(320, 280, 3), dtype=np.uint8)
    if flicker:
        image[10:18, 10:26] = 255  # ~0.1% of the frame
    return _png(image)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Timeline:
    """Capture callable returning whichever frame is scheduled for the current time."""

    def __init__(self, clock: FakeClock, schedule: list[tuple[float, bytes]]) -> None:
        self._clock = clock
        self._schedule = sorted(schedule, key=lambda item: item[0])

    def __call__(self) -> bytes:
        current = self._schedule[0][1]
        for start, frame in self._schedule:
            if self._clock.now >= start:
                current = frame
        return current


def _settler(clock: FakeClock, **overrides) -> ScreenSettler:
    params = dict(
        stable_seconds=0.4,
        timeout_seconds=5.0,
        poll_seconds=0.1,
        change_threshold=0.02,
        stable_threshold=0.005,
        clock=clock,
        sleep=clock.sleep,
    )
    params.update(overrides)
    return ScreenSettler(**params)


class TestSignature:
    def test_undecodable_frame_returns_none(self):
        assert frame_signature(b"not a png") is None
        assert frame_signature(object()) is None  # type: ignore[arg-type]

    def test_identical_frames_have_no_change(self):
        a = frame_signature(_screen(cards=1))
        b = frame_signature(_screen(cards=1))
        assert changed_fraction(a, b) == 0.0

    def test_new_cards_register_as_large_change(self):
        a = frame_signature(_screen(cards=1))
        b = frame_signature(_screen(cards=2))
        assert changed_fraction(a, b) > 0.2

    def test_mismatched_shapes_count_as_fully_changed(self):
        assert changed_fraction(np.zeros((4, 4), np.uint8), np.zeros((5, 4), np.uint8)) == 1.0


class TestScreenSettler:
    def test_waits_through_server_latency_until_new_cards_settle(self):
        """The screen stays unchanged for 1.5s after the tap (server round-trip),
        animates until 2.0s, then holds still. A fixed 1s wait would read the
        stale market; the settler must wait for the new cards."""
        clock = FakeClock()
        old, animating, new = _screen(cards=1), _screen(cards=3), _screen(cards=2)
        capture = Timeline(clock, [(0.0, old), (1.6, animating), (1.8, new)])
        settler = _settler(clock)

        baseline = settler.capture_baseline(capture)
        assert baseline is not None
        clock.now = 0.2  # tap happens after the baseline samples
        result = settler.wait(capture, baseline, min_wait=1.0, label="refresh")

        assert result.changed and result.settled
        assert capture() == new
        # Settled = last motion (≈1.8s after start) + stable window (0.4s).
        assert 1.8 + 0.4 - 0.2 <= result.waited <= 1.8 + 0.4 - 0.2 + 0.25

    def test_times_out_when_nothing_changes(self):
        clock = FakeClock()
        capture = Timeline(clock, [(0.0, _screen(cards=1))])
        settler = _settler(clock, timeout_seconds=3.0)

        baseline = settler.capture_baseline(capture)
        result = settler.wait(capture, baseline, min_wait=0.5, label="refresh")

        assert not result.changed
        assert not result.settled
        assert result.waited == pytest.approx(3.0, abs=0.15)
        assert settler.average("refresh") is None

    def test_times_out_when_screen_never_stops_changing(self):
        clock = FakeClock()
        frames = [(0.0, _screen(cards=1))] + [
            (0.5 + 0.05 * i, _screen(cards=10 + i)) for i in range(100)
        ]
        capture = Timeline(clock, frames)
        settler = _settler(clock, timeout_seconds=3.0)

        baseline = settler.capture_baseline(capture)
        result = settler.wait(capture, baseline, min_wait=0.2, label="refresh")

        assert result.changed
        assert not result.settled

    def test_ambient_animation_does_not_prevent_settling(self):
        """A flickering patch present before and after the tap is measured as
        noise, so the settler still settles once the cards stop changing."""
        clock = FakeClock()
        flicker = [(0.1 * i, _screen(cards=1, flicker=i % 2 == 0)) for i in range(10)]
        after = [(1.0 + 0.1 * i, _screen(cards=2, flicker=i % 2 == 0)) for i in range(60)]
        capture = Timeline(clock, flicker + after)
        settler = _settler(clock, stable_threshold=0.0001)

        baseline = settler.capture_baseline(capture)
        assert baseline is not None and baseline.noise > 0
        result = settler.wait(capture, baseline, min_wait=0.3, label="refresh")

        assert result.settled

    def test_min_wait_is_respected_even_if_screen_settles_sooner(self):
        clock = FakeClock()
        capture = Timeline(clock, [(0.0, _screen(cards=1)), (0.2, _screen(cards=2))])
        settler = _settler(clock)

        baseline = settler.capture_baseline(capture)
        start = clock.now
        result = settler.wait(capture, baseline, min_wait=2.0, label="purchase")

        assert result.settled
        assert result.waited >= 2.0
        assert clock.now - start >= 2.0

    def test_tracks_running_average_per_label(self):
        clock = FakeClock()
        settler = _settler(clock)
        waits = []
        for switch_at in (0.5, 1.5):
            start = clock.now
            capture = Timeline(
                clock, [(0.0, _screen(cards=1)), (start + switch_at, _screen(cards=2))]
            )
            baseline = settler.capture_baseline(capture)
            waits.append(settler.wait(capture, baseline, min_wait=0.0, label="refresh").waited)

        average = settler.average("refresh")
        assert average is not None
        assert min(waits) < average < max(waits)
        assert settler.average("purchase") is None

    def test_on_poll_exceptions_propagate(self):
        """Cancellation is signalled by raising from on_poll, including during min_wait."""
        clock = FakeClock()
        capture = Timeline(clock, [(0.0, _screen(cards=1))])
        settler = _settler(clock)
        baseline = settler.capture_baseline(capture)

        class Cancelled(Exception):
            pass

        def cancel():
            if clock.now > 0.5:
                raise Cancelled

        with pytest.raises(Cancelled):
            settler.wait(capture, baseline, min_wait=3.0, label="refresh", on_poll=cancel)
        assert clock.now < 1.0

    def test_undecodable_frames_yield_no_baseline(self):
        clock = FakeClock()
        settler = _settler(clock)
        assert settler.capture_baseline(lambda: b"garbage") is None
