"""Unit tests for the matcher's sorting and non-max suppression behavior."""

from __future__ import annotations

from staminabuyer.vision.matcher import MatchResult, _iou, _non_max_suppress


def _mr(icon: str, score: float, x: int, y: int, w: int = 80, h: int = 100) -> MatchResult:
    return MatchResult(
        icon=icon,
        score=score,
        top_left=(x, y),
        bottom_right=(x + w, y + h),
    )


class TestIoU:
    def test_disjoint_boxes_are_zero(self):
        a = _mr("a", 1.0, 0, 0)
        b = _mr("b", 1.0, 500, 500)
        assert _iou(a, b) == 0.0

    def test_identical_boxes_are_one(self):
        a = _mr("a", 1.0, 10, 10)
        b = _mr("b", 1.0, 10, 10)
        assert _iou(a, b) == 1.0

    def test_half_overlap_ratio_matches_formula(self):
        a = _mr("a", 1.0, 0, 0, w=100, h=100)
        b = _mr("b", 1.0, 50, 0, w=100, h=100)
        # Intersection 50x100 = 5000; union 2*10000 - 5000 = 15000
        assert _iou(a, b) == 5000 / 15000


class TestNonMaxSuppression:
    def test_keeps_highest_score_when_overlapping(self):
        high = _mr("stamina_10", 0.9, 100, 100)
        low = _mr("stamina_10", 0.7, 105, 102)  # nearly same location
        result = _non_max_suppress([high, low], iou_threshold=0.3)
        assert result == [high]

    def test_keeps_non_overlapping_matches(self):
        a = _mr("stamina_10", 0.9, 100, 100)
        b = _mr("stamina_10", 0.85, 500, 500)
        result = _non_max_suppress([a, b], iou_threshold=0.3)
        assert result == [a, b]

    def test_preserves_order_of_kept_matches(self):
        first = _mr("a", 0.95, 0, 0)
        second = _mr("b", 0.90, 300, 0)
        third = _mr("c", 0.85, 600, 0)
        assert _non_max_suppress([first, second, third], iou_threshold=0.3) == [
            first,
            second,
            third,
        ]


class TestMatcherReturnsBestFirst:
    """End-to-end check that TemplateLibrary.match sorts results best-first."""

    def test_match_results_are_sorted_descending(self):
        from pathlib import Path

        from staminabuyer.vision.matcher import TemplateLibrary

        assets = Path(__file__).parent.parent / "assets" / "icons"
        library = TemplateLibrary(template_dir=assets, threshold=0.3, grayscale=True)

        screenshot = (assets / "screenshot-bm.png").read_bytes()
        matches = library.match(screenshot, ["stamina_10"], threshold=0.3)

        assert matches, "expected at least one stamina_10 match"
        scores = [m.score for m in matches]
        assert scores == sorted(scores, reverse=True), (
            f"matches should be sorted descending by score, got {scores}"
        )
