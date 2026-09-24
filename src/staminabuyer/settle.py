"""Detect when the emulator screen has finished reacting to a tap.

A fixed sleep after tapping refresh is either too short (the server hasn't
answered yet, so we read the stale market and refresh again, burning gems)
or too long (wasted time on every refresh). Instead we:

1. Grab two frames *before* the tap to measure the screen's ambient motion
   (timers ticking, glow effects) so it isn't mistaken for the UI reacting.
2. Wait a minimum delay after the tap.
3. Poll until the screen has visibly changed from the pre-tap baseline and
   then held still for ``stable_seconds``, or until ``timeout_seconds``.

Frames are compared as small greyscale thumbnails, so each comparison is
cheap compared with the screen capture itself.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

#: Thumbnail width used for frame comparison. Small enough that compression
#: noise and sub-pixel jitter average out.
SIGNATURE_WIDTH = 160
#: Grey-level difference above which a thumbnail pixel counts as changed.
PIXEL_DELTA = 16
#: Weight of the newest sample in the running average of wait times.
_AVERAGE_WEIGHT = 0.3


def frame_signature(frame: bytes) -> np.ndarray | None:
    """Decode ``frame`` into a small greyscale thumbnail, or ``None`` if undecodable."""
    try:
        gray = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    except (TypeError, ValueError, cv2.error):
        return None
    if gray is None:
        return None
    height, width = gray.shape[:2]
    if width > SIGNATURE_WIDTH:
        new_height = max(1, round(height * SIGNATURE_WIDTH / width))
        gray = cv2.resize(gray, (SIGNATURE_WIDTH, new_height), interpolation=cv2.INTER_AREA)
    return gray


def changed_fraction(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of thumbnail pixels that differ noticeably between ``a`` and ``b``."""
    if a.shape != b.shape:
        return 1.0
    return float(np.count_nonzero(cv2.absdiff(a, b) > PIXEL_DELTA)) / a.size


@dataclass(slots=True)
class SettleBaseline:
    """What the screen looked like just before a tap."""

    signature: np.ndarray
    #: Changed-pixel fraction between two back-to-back idle frames.
    noise: float


@dataclass(slots=True)
class SettleResult:
    waited: float
    #: The screen moved away from the pre-tap baseline at some point.
    changed: bool
    #: ...and then held still for ``stable_seconds``. False means we timed out.
    settled: bool


class ScreenSettler:
    """Waits for the screen to change and then stop changing after a tap."""

    def __init__(
        self,
        *,
        stable_seconds: float,
        timeout_seconds: float,
        poll_seconds: float,
        change_threshold: float,
        stable_threshold: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.stable_seconds = max(0.0, stable_seconds)
        self.timeout_seconds = max(0.0, timeout_seconds)
        self.poll_seconds = max(0.01, poll_seconds)
        self.change_threshold = change_threshold
        self.stable_threshold = stable_threshold
        self._clock = clock
        self._sleep = sleep
        self._averages: dict[str, float] = {}

    def average(self, label: str) -> float | None:
        """Running average of settled wait times for ``label``, if any were observed."""
        return self._averages.get(label)

    def capture_baseline(self, capture: Callable[[], bytes]) -> SettleBaseline | None:
        """Sample the pre-tap screen. Returns ``None`` if frames can't be decoded."""
        first = frame_signature(capture())
        if first is None:
            return None
        self._sleep(self.poll_seconds)
        second = frame_signature(capture())
        if second is None:
            return None
        return SettleBaseline(signature=second, noise=changed_fraction(first, second))

    def wait(
        self,
        capture: Callable[[], bytes],
        baseline: SettleBaseline,
        min_wait: float,
        label: str,
        on_poll: Callable[[], None] | None = None,
    ) -> SettleResult:
        """Block until the screen settles after a tap, or ``timeout_seconds`` passes.

        ``on_poll`` is called between waits (e.g. to raise on cancellation).
        """
        start = self._clock()
        self._sleep_until(start + max(0.0, min_wait), on_poll)

        # Ambient motion measured before the tap must not count as motion
        # (otherwise we never settle) or as the UI changing (otherwise we
        # settle before the server has answered).
        stable_limit = max(self.stable_threshold, baseline.noise * 2)
        change_limit = max(self.change_threshold, stable_limit * 2)

        changed = False
        previous: np.ndarray | None = None
        last_motion = start
        while True:
            if on_poll:
                on_poll()
            signature = frame_signature(capture())
            now = self._clock()
            if signature is not None:
                if not changed and changed_fraction(signature, baseline.signature) > change_limit:
                    changed = True
                    last_motion = now
                if previous is not None and changed_fraction(signature, previous) > stable_limit:
                    last_motion = now
                previous = signature
                if changed and now - last_motion >= self.stable_seconds:
                    waited = now - start
                    self._record(label, waited)
                    return SettleResult(waited=waited, changed=True, settled=True)

            if now - start >= self.timeout_seconds:
                return SettleResult(waited=now - start, changed=changed, settled=False)
            self._sleep(self.poll_seconds)

    def _sleep_until(self, deadline: float, on_poll: Callable[[], None] | None) -> None:
        while True:
            if on_poll:
                on_poll()
            remaining = deadline - self._clock()
            if remaining <= 0:
                return
            self._sleep(min(remaining, 0.25))

    def _record(self, label: str, waited: float) -> None:
        previous = self._averages.get(label)
        self._averages[label] = (
            waited if previous is None else previous + _AVERAGE_WEIGHT * (waited - previous)
        )
