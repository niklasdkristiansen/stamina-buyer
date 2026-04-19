"""Template matching utilities that operate fully in-memory."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rich.console import Console


def get_assets_path() -> Path:
    """
    Get the correct path to assets, whether running from source or as PyInstaller executable.

    Returns:
        Path to the assets directory
    """
    # When running as a PyInstaller bundle, assets are in sys._MEIPASS
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as PyInstaller executable
        base_path = Path(sys._MEIPASS)
        return base_path / "assets" / "icons"
    else:
        # Running from source - go up from this file to project root
        # matcher.py is in src/staminabuyer/vision/
        # We want to go to project_root/assets/icons
        return Path(__file__).parent.parent.parent.parent / "assets" / "icons"


@dataclass(slots=True)
class MatchResult:
    icon: str
    score: float
    top_left: tuple[int, int]
    bottom_right: tuple[int, int]
    scale: float = 1.0


def _within_tolerance(value: float, target: float, relative_tolerance: float) -> bool:
    """True if ``value`` is within ``relative_tolerance`` (fraction) of ``target``."""
    if target <= 0:
        return False
    return abs(value - target) / target <= relative_tolerance


def _iou(a: "MatchResult", b: "MatchResult") -> float:
    """Intersection-over-Union of two MatchResult bboxes."""
    ax1, ay1 = a.top_left
    ax2, ay2 = a.bottom_right
    bx1, by1 = b.top_left
    bx2, by2 = b.bottom_right
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area == 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0 else 0.0


def _non_max_suppress(matches: list["MatchResult"], iou_threshold: float) -> list["MatchResult"]:
    """Greedy NMS: keep highest-scoring match, drop overlaps above the threshold.

    Assumes ``matches`` is already sorted by descending score.
    """
    kept: list[MatchResult] = []
    for candidate in matches:
        if any(_iou(candidate, existing) > iou_threshold for existing in kept):
            continue
        kept.append(candidate)
    return kept


@dataclass(slots=True)
class TemplateVariant:
    """Stores scaled template data plus feature descriptors for secondary verification."""

    match_image: np.ndarray
    color_image: np.ndarray
    descriptors: np.ndarray | None


class TemplateLibrary:
    """Loads template icons and runs normalized template matching against frames."""

    def __init__(
        self,
        template_dir: Path | None = None,
        threshold: float = 0.7,
        scales: Sequence[float] | None = None,
        grayscale: bool = True,
        descriptor_ratio: float = 0.75,
        descriptor_min_matches: int = 10,
        console: "Console | None" = None,
        reference_width: int | None = None,
    ) -> None:
        """Create a template library.

        Args:
            template_dir: Directory containing `<icon>.png` files.
            threshold: Default minimum correlation score for a match.
            scales: Template scale variants to prepare. Defaults to a dense
                sweep from 0.40 to 2.00. Callers that do anchor calibration
                first should pass a narrower band plus rely on `scale_hint`
                in :meth:`match`.
            grayscale: Match on grayscale templates (typical, more robust).
            descriptor_ratio: Lowe's ratio for ORB descriptor filtering.
            descriptor_min_matches: Minimum good ORB matches required for a
                template-match candidate to pass secondary verification.
                Set to 0 to skip the descriptor check entirely.
            console: Optional Rich console for human-readable progress logs.
            reference_width: Legacy. If set, captured frames are rescaled to
                this logical width before matching. Anchor-based calibration
                (see :meth:`calibrate_scale`) supersedes this for most setups,
                but the knob is preserved for fixed-size deployments.
        """
        self.template_dir = template_dir or get_assets_path()
        self.threshold = threshold
        # 0.02 steps hit scale-sensitive sweet spots across the full supported range.
        default_scales = tuple(round(0.4 + i * 0.02, 2) for i in range(81))  # 0.40 → 2.00
        self.scales = tuple(sorted({scale for scale in (scales or default_scales) if scale > 0}))
        if not self.scales:
            self.scales = (1.0,)
        self.grayscale = grayscale
        if not 0.0 < descriptor_ratio <= 1.0:
            raise ValueError("descriptor_ratio must be within (0, 1].")
        if descriptor_min_matches < 0:
            raise ValueError("descriptor_min_matches must be non-negative.")
        self.descriptor_ratio = descriptor_ratio
        self.descriptor_min_matches = descriptor_min_matches
        self.reference_width = reference_width
        self._orb = cv2.ORB_create()
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self._templates: dict[str, dict[float, TemplateVariant]] = {}
        self._logger = logging.getLogger(__name__)
        self._console = console
        self.reload()

    def reload(self) -> None:
        """(Re)load every `<name>.png` in the template directory as an icon."""
        self._templates.clear()
        self._logger.info("Loading templates from: %s", self.template_dir)

        if not self.template_dir.exists():
            self._logger.warning("Template directory does not exist: %s", self.template_dir)
            return

        template_files = list(self.template_dir.glob("*.png"))
        self._logger.info("Found %d template files", len(template_files))

        for path in template_files:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                self._logger.warning("Could not read template: %s", path)
                continue

            prepared = self._prepare_template(image)
            variants: dict[float, TemplateVariant] = {}
            for scale in self.scales:
                match_image = self._scale_template(prepared, scale)
                color_image = self._scale_template(image, scale)
                descriptor_image = (
                    match_image
                    if match_image.ndim == 2
                    else cv2.cvtColor(match_image, cv2.COLOR_BGR2GRAY)
                )
                _, descriptors = self._orb.detectAndCompute(descriptor_image, None)
                variants[scale] = TemplateVariant(
                    match_image=match_image, color_image=color_image, descriptors=descriptors
                )
            self._templates[path.stem] = variants
            h, w = image.shape[:2]
            self._logger.debug(
                "Loaded template '%s' (%d×%d) with %d scale variants",
                path.stem, w, h, len(variants),
            )

        self._logger.info(
            "Successfully loaded %d templates: %s",
            len(self._templates),
            list(self._templates.keys()),
        )

    def has_template(self, icon_name: str) -> bool:
        """Return True when a template is available for the given icon."""

        return icon_name in self._templates

    def _decode_frame(
        self,
        frame: bytes,
        frame_scale: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
        """Decode a PNG/JPEG ``frame`` and (optionally) normalize it to template scale.

        Two normalization modes are supported:

        - ``frame_scale`` (per-call, preferred): the UI in ``frame`` is rendered
          at ``frame_scale`` relative to the templates. The frame is resized by
          ``1/frame_scale`` so that the UI appears at canonical (template)
          scale, and callers can then match at scale ≈ 1.0. This is the output
          of :meth:`calibrate_scale` and produces reliable results at any
          window size covered by the anchor sweep.
        - ``reference_width`` (library-level, legacy): if set on the library,
          frames are resized so their width equals ``reference_width``. Kept
          for fixed-size deployments where anchor calibration is unavailable.

        ``frame_scale`` takes precedence over ``reference_width`` when both are set.

        Returns:
            ``(color_frame, prepared_frame, (scale_x, scale_y))`` where
            ``(scale_x, scale_y)`` maps coordinates from the (possibly resized)
            working frame back to the original screenshot. When no resize
            happened, both values are ``1.0``.
        """
        array = np.frombuffer(frame, dtype=np.uint8)
        color_frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if color_frame is None:
            raise ValueError("Unable to decode framebuffer for matching.")

        orig_height, orig_width = color_frame.shape[:2]
        if self._console:
            self._console.log(f"[cyan]Screenshot: {orig_width}×{orig_height}[/cyan]")

        if frame_scale is not None and frame_scale > 0 and abs(frame_scale - 1.0) > 1e-3:
            # Resize the frame so the UI is at canonical (template) scale.
            # Downscaling the frame by 1/S puts everything at ≈template size.
            target_width = max(1, int(round(orig_width / frame_scale)))
            target_height = max(1, int(round(orig_height / frame_scale)))
            interpolation = cv2.INTER_AREA if frame_scale > 1.0 else cv2.INTER_CUBIC
            color_frame = cv2.resize(
                color_frame, (target_width, target_height), interpolation=interpolation
            )
            if self._console:
                self._console.log(
                    f"[cyan]Frame-normalized (UI scale {frame_scale:.3f}x): "
                    f"{orig_width}×{orig_height} → {target_width}×{target_height}[/cyan]"
                )
            return (
                color_frame,
                self._prepare_frame(color_frame),
                (orig_width / target_width, orig_height / target_height),
            )

        if not self.reference_width or orig_width == self.reference_width:
            return color_frame, self._prepare_frame(color_frame), (1.0, 1.0)

        # Legacy aspect-preserving rescale. Anchor calibration usually obviates
        # this, but it remains available for fixed-size setups where anchor
        # detection is expensive or unreliable.
        scale_factor = self.reference_width / orig_width
        target_width = self.reference_width
        target_height = int(orig_height * scale_factor)
        color_frame = cv2.resize(
            color_frame,
            (target_width, target_height),
            interpolation=cv2.INTER_AREA if scale_factor < 1.0 else cv2.INTER_CUBIC,
        )
        if self._console:
            self._console.log(
                f"[cyan]Normalized to reference width: {orig_width}×{orig_height} → "
                f"{target_width}×{target_height} (scale: {scale_factor:.3f}x)[/cyan]"
            )
        return (
            color_frame,
            self._prepare_frame(color_frame),
            (orig_width / target_width, orig_height / target_height),
        )

    def _prepare_template(self, image: np.ndarray) -> np.ndarray:
        if self.grayscale:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    def _prepare_frame(self, image: np.ndarray) -> np.ndarray:
        if self.grayscale:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    def _scale_template(self, image: np.ndarray, scale: float) -> np.ndarray:
        if scale == 1.0:
            return image
        height, width = image.shape[:2]
        new_width = max(1, int(round(width * scale)))
        new_height = max(1, int(round(height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        return cv2.resize(image, (new_width, new_height), interpolation=interpolation)

    def match(
        self,
        frame: bytes,
        icon_names: Iterable[str],
        threshold: float | None = None,
        nms_iou_threshold: float = 0.3,
        scale_hint: float | None = None,
        scale_tolerance: float = 0.05,
        frame_scale: float | None = None,
    ) -> list[MatchResult]:
        """
        Match templates against a frame and return candidates sorted best-first.

        Args:
            frame: Screenshot bytes (PNG/JPEG).
            icon_names: Template names to search for.
            threshold: Optional override for match threshold (uses library default if None).
            nms_iou_threshold: IoU threshold for non-maximum suppression of
                overlapping matches (same icon at adjacent scales, or different
                icons landing on the same cell). Set to 1.0 to disable.
            scale_hint: If provided, only template variants within
                ``scale_tolerance`` of this scale are evaluated. After
                :meth:`calibrate_scale` + ``frame_scale`` normalization the UI
                is at canonical scale, so callers typically pass ``1.0``.
            scale_tolerance: Relative tolerance around ``scale_hint`` (fraction,
                not absolute). Ignored when ``scale_hint`` is None.
            frame_scale: If provided, the frame is resized by ``1/frame_scale``
                before matching so the UI appears at template (canonical)
                scale. Match coordinates are automatically transformed back
                into the original frame's coordinate space. Typically set to
                the ``scale`` returned by :meth:`calibrate_scale`.

        Returns:
            Matches sorted by descending score. Overlapping matches (IoU above
            ``nms_iou_threshold``) are suppressed so ``matches[0]`` is always
            the single best candidate.
        """
        effective_threshold = threshold if threshold is not None else self.threshold
        color_frame, decoded, (scale_x, scale_y) = self._decode_frame(
            frame, frame_scale=frame_scale
        )
        matches: list[MatchResult] = []
        best_score = 0.0
        best_icon = None
        best_scale = 1.0
        for icon_name in icon_names:
            variants = self._templates.get(icon_name)
            if not variants:
                if self._console:
                    self._console.log(f"[yellow]Template '{icon_name}' missing from library.[/yellow]")
                continue
            for scale, variant in variants.items():
                if scale_hint is not None and not _within_tolerance(
                    scale, scale_hint, scale_tolerance
                ):
                    continue
                template = variant.match_image
                if decoded.shape[0] < template.shape[0] or decoded.shape[1] < template.shape[1]:
                    continue
                res = cv2.matchTemplate(decoded, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val > best_score:
                    best_score = max_val
                    best_icon = icon_name
                    best_scale = scale
                if max_val >= effective_threshold:
                    h, w = template.shape[:2]
                    top_left = max_loc
                    bottom_right = (top_left[0] + w, top_left[1] + h)

                    if self.descriptor_min_matches:
                        if not self._passes_descriptor_check(
                            color_frame, variant, top_left, w, h
                        ):
                            self._logger.debug(
                                "Rejected icon '%s' (scale %.2f) due to insufficient feature matches.",
                                icon_name,
                                scale,
                            )
                            continue

                    # Convert coordinates back to original resolution if we normalized
                    if scale_x != 1.0 or scale_y != 1.0:
                        top_left = (
                            int(top_left[0] * scale_x),
                            int(top_left[1] * scale_y)
                        )
                        bottom_right = (
                            int(bottom_right[0] * scale_x),
                            int(bottom_right[1] * scale_y)
                        )

                    matches.append(
                        MatchResult(
                            icon=icon_name,
                            score=float(max_val),
                            top_left=top_left,
                            bottom_right=bottom_right,
                            scale=scale,
                        )
                    )
                    self._logger.debug(
                        "Matched icon '%s' (scale %.2f) with score %.3f at %s -> %s.",
                        icon_name,
                        scale,
                        max_val,
                        top_left,
                        bottom_right,
                    )
                else:
                    self._logger.debug(
                        "Icon '%s' (scale %.2f) max score %.3f below threshold %.3f.",
                        icon_name,
                        scale,
                        max_val,
                        effective_threshold,
                    )
        if not matches and best_icon:
            msg = f"❌ No match: best was '{best_icon}' @ scale {best_scale:.2f}x, score {best_score:.3f} (threshold: {effective_threshold:.2f})"
            if self._console:
                self._console.log(f"[yellow]{msg}[/yellow]")
            else:
                self._logger.info(msg)
        elif not matches:
            if self._console:
                self._console.log("[yellow]❌ No templates matched at all[/yellow]")

        matches.sort(key=lambda m: m.score, reverse=True)
        if nms_iou_threshold < 1.0 and len(matches) > 1:
            matches = _non_max_suppress(matches, nms_iou_threshold)
        return matches

    def calibrate_scale(
        self,
        frame: bytes,
        anchor_icons: Sequence[str],
        min_score: float = 0.6,
    ) -> MatchResult | None:
        """Find the best-scoring anchor match in ``frame`` to calibrate scale.

        The returned match's ``scale`` is the factor the UI is rendered at
        relative to the stored templates. Feed it back into :meth:`match` via
        ``scale_hint`` to match subsequent icons efficiently and without a
        wide multi-scale sweep.

        Args:
            frame: Screenshot bytes.
            anchor_icons: Candidate anchor templates (first match wins among
                those meeting ``min_score``). Typical picks are stable UI
                chrome like the "refresh" button that only appears on the
                target screen.
            min_score: Minimum correlation score required to trust the match.

        Returns:
            The best anchor MatchResult, or ``None`` if no anchor was
            confident enough. Callers should treat ``None`` as "probably on
            the wrong screen".
        """
        # We intentionally do NOT pass scale_hint here; this is the calibration step.
        matches = self.match(frame, anchor_icons, threshold=min_score)
        if not matches:
            return None
        return matches[0]

    def mean_saturation(self, frame: bytes, match: MatchResult) -> float:
        """Return the mean HSV saturation of the match's ROI in the decoded frame.

        Used for detecting 'greyed out' states (bought items, disabled buttons)
        without needing a separate per-state template. Regular stamina cards
        measure ~145, purchased/desaturated ones ~35, so a threshold around
        80 cleanly separates the two.

        The match's coordinates are in the *original* frame's space (match
        returns coordinates post-denormalization), so we decode the frame
        without any normalization here and index directly.
        """
        color_frame, _, _ = self._decode_frame(frame)
        x1, y1 = match.top_left
        x2, y2 = match.bottom_right
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(color_frame.shape[1], x2)
        y2 = min(color_frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        roi = color_frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        return float(np.mean(hsv[..., 1]))

    def _passes_descriptor_check(
        self,
        frame_color: np.ndarray,
        variant: TemplateVariant,
        top_left: tuple[int, int],
        width: int,
        height: int,
    ) -> bool:
        # ``variant.descriptors is None`` means ORB found nothing on the
        # template itself — we genuinely cannot verify, so we accept the match
        # on score alone. We also short-circuit when the template has fewer
        # than three descriptors, since any match count is statistically
        # meaningless at that point. For every other case we require at least
        # ``min(len(descriptors), descriptor_min_matches)`` good matches. This
        # closes a v2.3.0 loophole where small scaled templates silently
        # bypassed verification and produced cross-card false positives.
        if variant.descriptors is None:
            return True
        num_descriptors = len(variant.descriptors)
        if num_descriptors < 3:
            return True
        required_matches = min(num_descriptors, self.descriptor_min_matches)
        x, y = top_left
        roi = frame_color[y : y + height, x : x + width]
        if roi.shape[:2] != (height, width):
            return False
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, roi_descriptors = self._orb.detectAndCompute(roi_gray, None)
        if roi_descriptors is None or len(roi_descriptors) == 0:
            return False
        matches = self._bf.knnMatch(variant.descriptors, roi_descriptors, k=2)
        good = 0
        for pair in matches:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.distance < self.descriptor_ratio * n.distance:
                good += 1
        return good >= required_matches
