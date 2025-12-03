"""Template matching utilities that operate fully in-memory."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


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
    ) -> None:
        self.template_dir = template_dir or get_assets_path()
        self.threshold = threshold
        self.scales = tuple(sorted({scale for scale in (scales or (1.0,)) if scale > 0}))
        if not self.scales:
            self.scales = (1.0,)
        self.grayscale = grayscale
        if not 0.0 < descriptor_ratio <= 1.0:
            raise ValueError("descriptor_ratio must be within (0, 1].")
        if descriptor_min_matches < 0:
            raise ValueError("descriptor_min_matches must be non-negative.")
        self.descriptor_ratio = descriptor_ratio
        self.descriptor_min_matches = descriptor_min_matches
        self._orb = cv2.ORB_create()
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self._templates: dict[str, dict[float, TemplateVariant]] = {}
        self._logger = logging.getLogger(__name__)
        self.reload()

    def reload(self) -> None:
        self._templates.clear()
        self._logger.info(f"Loading templates from: {self.template_dir}")
        
        if not self.template_dir.exists():
            self._logger.warning(f"Template directory does not exist: {self.template_dir}")
            return
        
        template_files = list(self.template_dir.glob("*.png"))
        self._logger.info(f"Found {len(template_files)} template files")
        
        for path in template_files:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                self._logger.warning(f"Could not read template: {path}")
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
            self._logger.debug(f"Loaded template '{path.stem}' with {len(variants)} scale variants")
        
        self._logger.info(f"Successfully loaded {len(self._templates)} templates: {list(self._templates.keys())}")

    def has_template(self, icon_name: str) -> bool:
        """Return True when a template is available for the given icon."""

        return icon_name in self._templates

    def _decode_frame(self, frame: bytes) -> tuple[np.ndarray, np.ndarray]:
        array = np.frombuffer(frame, dtype=np.uint8)
        color_frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if color_frame is None:
            raise ValueError("Unable to decode framebuffer for matching.")
        prepared = self._prepare_frame(color_frame)
        return color_frame, prepared

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

    def match(self, frame: bytes, icon_names: Iterable[str]) -> list[MatchResult]:
        color_frame, decoded = self._decode_frame(frame)
        self._logger.info(f"Matching in frame of size {decoded.shape} against templates: {list(icon_names)}")
        matches: list[MatchResult] = []
        best_score = 0.0
        best_icon = None
        best_scale = 1.0
        for icon_name in icon_names:
            variants = self._templates.get(icon_name)
            if not variants:
                self._logger.warning(f"Template '{icon_name}' missing from library.")
                continue
            self._logger.info(f"Trying template '{icon_name}' with {len(variants)} scale variants (threshold={self.threshold})")
            for scale, variant in variants.items():
                template = variant.match_image
                if decoded.shape[0] < template.shape[0] or decoded.shape[1] < template.shape[1]:
                    continue
                res = cv2.matchTemplate(decoded, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                self._logger.debug(f"  Scale {scale:.2f}x: score={max_val:.4f} (threshold={self.threshold})")
                if max_val > best_score:
                    best_score = max_val
                    best_icon = icon_name
                    best_scale = scale
                if max_val >= self.threshold:
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
                        self.threshold,
                    )
        if not matches and best_icon:
            self._logger.info(
                "Best match was '%s' (scale %.2f) at score %.3f but below threshold %.3f.",
                best_icon,
                best_scale,
                best_score,
                self.threshold,
            )
        return matches

    def _passes_descriptor_check(
        self,
        frame_color: np.ndarray,
        variant: TemplateVariant,
        top_left: tuple[int, int],
        width: int,
        height: int,
    ) -> bool:
        if variant.descriptors is None or len(variant.descriptors) < self.descriptor_min_matches:
            # Template lacks enough features, so skip the descriptor filter.
            return True
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
        return good >= self.descriptor_min_matches
