"""Tests for anchor-based scale calibration.

Anchor calibration lets the pipeline work at any UI scale without relying on
a hard-coded ``reference_width``. We verify both the low-level matcher API
(``calibrate_scale`` + ``scale_hint``) and the pipeline behavior on
artificially rescaled screenshots.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from staminabuyer.vision.matcher import TemplateLibrary, _within_tolerance

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "icons"

# Scale sweep wide enough for the rescale tests below.
WIDE_SCALES = tuple(round(s, 2) for s in np.arange(0.5, 2.01, 0.05))


@pytest.fixture(scope="module")
def library() -> TemplateLibrary:
    return TemplateLibrary(
        template_dir=ASSETS_DIR,
        threshold=0.3,
        scales=WIDE_SCALES,
        grayscale=True,
    )


def _rescale_png(original_path: Path, factor: float) -> bytes:
    """Load ``original_path``, resize by ``factor``, return PNG bytes."""
    img = cv2.imread(str(original_path))
    assert img is not None, f"could not read {original_path}"
    h, w = img.shape[:2]
    new_w = max(1, int(w * factor))
    new_h = max(1, int(h * factor))
    interp = cv2.INTER_AREA if factor < 1.0 else cv2.INTER_CUBIC
    resized = cv2.resize(img, (new_w, new_h), interpolation=interp)
    ok, buf = cv2.imencode(".png", resized)
    assert ok, "cv2.imencode failed"
    return buf.tobytes()


class TestWithinTolerance:
    def test_identical_values_within_tolerance(self):
        assert _within_tolerance(1.0, 1.0, 0.05)

    def test_inside_tolerance_band(self):
        # 1.03 is 3% off from 1.0 — inside a 5% tolerance.
        assert _within_tolerance(1.03, 1.0, 0.05)

    def test_outside_tolerance_band(self):
        # 1.10 is 10% off from 1.0 — outside a 5% tolerance.
        assert not _within_tolerance(1.10, 1.0, 0.05)

    def test_nonpositive_target_is_false(self):
        assert not _within_tolerance(0.5, 0.0, 0.1)
        assert not _within_tolerance(0.5, -1.0, 0.1)


class TestCalibrateScale:
    @pytest.mark.parametrize(
        "screenshot",
        [
            "screenshot-bm.png",
            "blackmarket.png",
            "blackmarket_1_stamina.png",
            "no-stamina-blackmarket.png",
        ],
    )
    def test_anchor_detected_on_native_screens(self, library, screenshot):
        path = ASSETS_DIR / screenshot
        if not path.exists():
            pytest.skip(f"missing {path}")

        result = library.calibrate_scale(
            path.read_bytes(), anchor_icons=["refresh"], min_score=0.6
        )
        assert result is not None
        # At native resolution the templates match at scale 1.0 (±small).
        assert 0.98 <= result.scale <= 1.02
        assert result.score >= 0.9

    @pytest.mark.parametrize("factor", [0.70, 0.85, 1.0, 1.25, 1.5, 1.75, 2.0])
    def test_anchor_scale_follows_rescale(self, library, factor):
        """Rescale a Black Market screenshot and verify the anchor's detected
        scale equals the rescale factor (within snap-to-nearest-scale)."""
        base = ASSETS_DIR / "screenshot-bm.png"
        if not base.exists():
            pytest.skip(f"missing {base}")

        frame = _rescale_png(base, factor)
        result = library.calibrate_scale(frame, anchor_icons=["refresh"], min_score=0.6)
        assert result is not None, f"anchor should be found at factor {factor}"
        # Result snaps to the nearest configured scale step (0.05 apart).
        assert abs(result.scale - factor) <= 0.05, (
            f"expected anchor scale ≈ {factor}, got {result.scale}"
        )

    def test_returns_none_on_screen_without_anchor(self, library):
        """If no anchor icon can be located, calibration returns None
        (i.e. 'probably on the wrong screen')."""
        anchor_path = ASSETS_DIR / "stamina_10.png"
        if not anchor_path.exists():
            pytest.skip(f"missing {anchor_path}")

        # A cropped stamina icon is too small to plausibly contain the refresh button.
        result = library.calibrate_scale(
            anchor_path.read_bytes(), anchor_icons=["refresh"], min_score=0.9
        )
        assert result is None


class TestScaleHintedMatch:
    def test_scale_hint_filters_to_matching_variants(self, library):
        base = ASSETS_DIR / "screenshot-bm.png"
        if not base.exists():
            pytest.skip(f"missing {base}")
        frame = _rescale_png(base, 1.5)

        # Match with the correct hint — should find stamina_10 at ~1.5.
        with_hint = library.match(
            frame, ["stamina_10"], threshold=0.3, scale_hint=1.5, scale_tolerance=0.1
        )
        assert with_hint, "stamina_10 should match when hint is correct"
        assert abs(with_hint[0].scale - 1.5) <= 0.1

        # Hint is far outside every configured variant (WIDE_SCALES tops out
        # at 2.0), so no template should even be evaluated.
        with_wrong_hint = library.match(
            frame, ["stamina_10"], threshold=0.3, scale_hint=3.0, scale_tolerance=0.05
        )
        assert not with_wrong_hint, (
            "scale_hint outside tolerance should prevent any variant from being tried"
        )

    def test_scale_hint_none_searches_full_range(self, library):
        base = ASSETS_DIR / "screenshot-bm.png"
        if not base.exists():
            pytest.skip(f"missing {base}")
        frame = _rescale_png(base, 1.5)

        matches = library.match(frame, ["stamina_10"], threshold=0.3)
        assert matches
        assert abs(matches[0].scale - 1.5) <= 0.05


class TestPipelineCalibrationIntegration:
    """End-to-end-ish: stub the client factory so we can feed custom frames
    into the pipeline without touching mss/pyautogui."""

    def _build_runner(self, frame_sequence):
        from staminabuyer.pipeline import PipelineOptions, PipelineRunner

        # Stub screen-capture client that yields a pre-baked sequence of frames.
        class _StubClient:
            def __init__(self, frames):
                self._frames = list(frames)
                self.taps: list[tuple[int, int]] = []

            def screencap(self):
                if len(self._frames) > 1:
                    return self._frames.pop(0)
                return self._frames[0]

            def tap(self, x, y):  # pragma: no cover - not exercised here
                self.taps.append((x, y))

        stub_client = _StubClient(frame_sequence)
        options = PipelineOptions(
            dry_run=False,
            max_retries=1,
            template_scales=WIDE_SCALES,
            anchor_icons=("refresh",),
            anchor_min_score=0.6,
            scale_tolerance=0.1,
        )
        runner = PipelineRunner(
            options=options,
            client_factory=lambda title: stub_client,  # type: ignore[arg-type]
        )
        return runner, stub_client

    @pytest.mark.parametrize("factor", [1.0, 1.5, 2.0])
    def test_calibration_updates_scale_on_rescaled_frame(self, factor):
        base = ASSETS_DIR / "screenshot-bm.png"
        if not base.exists():
            pytest.skip(f"missing {base}")

        runner, stub = self._build_runner([_rescale_png(base, factor)])
        frame = stub.screencap()

        calibrated = runner._calibrate_from_frame(frame)
        assert calibrated is not None
        assert abs(calibrated - factor) <= 0.1, (
            f"expected calibrated scale ≈ {factor}, got {calibrated}"
        )
        assert runner._calibrated_scale == calibrated
