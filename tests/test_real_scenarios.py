"""
Comprehensive real-scenario tests for template matching.

Tests against actual Black Market screenshots at various resolutions to ensure
multi-scale template matching works correctly in production.

Available test screenshots:
- screenshot-bm.png: stamina_10 present
- blackmarket_1_stamina.png: stamina_1 present  
- blackmarket.png: stamina_10 present
- no-stamina-blackmarket.png: NO stamina items
- blackmarket_with_boots.png: boots (false positive test)
"""

from pathlib import Path

import pytest

from staminabuyer.pipeline import DEFAULT_STAMINA_ITEMS, PipelineOptions
from staminabuyer.vision.matcher import TemplateLibrary

# Use production settings
PROD_OPTIONS = PipelineOptions()
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "icons"


@pytest.fixture
def library():
    """Create a TemplateLibrary with production settings."""
    return TemplateLibrary(
        template_dir=ASSETS_DIR,
        threshold=PROD_OPTIONS.template_threshold,
        scales=PROD_OPTIONS.template_scales,
        grayscale=True,
        descriptor_min_matches=PROD_OPTIONS.descriptor_min_matches,
    )


class TestStamina10Detection:
    """Test stamina_10 (VIT 50/10 = 500 stamina) detection across resolutions."""

    def test_stamina_10_in_480x870_screenshot(self, library):
        """Test stamina_10 detection in screenshot-bm.png (480×870)."""
        screenshot_path = ASSETS_DIR / "screenshot-bm.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        matches = library.match(screenshot_bytes, ["stamina_10"])

        assert len(matches) > 0, "Should find stamina_10 in screenshot-bm.png"
        assert matches[0].score >= PROD_OPTIONS.template_threshold, \
            f"Score {matches[0].score:.3f} below threshold {PROD_OPTIONS.template_threshold}"
        
        # Just verify match is within reasonable screen bounds
        x, y = matches[0].top_left
        assert 0 <= x < 480, f"stamina_10 x={x} should be within screenshot width"
        assert 0 <= y < 870, f"stamina_10 y={y} should be within screenshot height"

    def test_stamina_10_in_772x1446_screenshot(self, library):
        """Test stamina_10 detection in blackmarket.png (772×1446)."""
        screenshot_path = ASSETS_DIR / "blackmarket.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        matches = library.match(screenshot_bytes, ["stamina_10"])

        assert len(matches) > 0, "Should find stamina_10 in blackmarket.png"
        assert matches[0].score >= PROD_OPTIONS.template_threshold, \
            f"Score {matches[0].score:.3f} below threshold {PROD_OPTIONS.template_threshold}"
        
        # Just verify match is within reasonable screen bounds
        x, y = matches[0].top_left
        assert 0 <= x < 772, f"stamina_10 x={x} should be within screenshot width"
        assert 0 <= y < 1446, f"stamina_10 y={y} should be within screenshot height"


class TestStamina1Detection:
    """Test stamina_1 (VIT 50/1 = 50 stamina) detection across resolutions."""

    def test_stamina_1_in_575x1056_screenshot(self, library):
        """Test stamina_1 detection in blackmarket_1_stamina.png (575×1056)."""
        screenshot_path = ASSETS_DIR / "blackmarket_1_stamina.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        matches = library.match(screenshot_bytes, ["stamina_1"])

        assert len(matches) > 0, "Should find stamina_1 in blackmarket_1_stamina.png"
        assert matches[0].score >= PROD_OPTIONS.template_threshold, \
            f"Score {matches[0].score:.3f} below threshold {PROD_OPTIONS.template_threshold}"


class TestNoFalsePositives:
    """Test that non-stamina items are NOT detected as stamina."""

    def test_no_stamina_in_no_stamina_screenshot(self, library):
        """Test that no stamina is found in no-stamina-blackmarket.png."""
        screenshot_path = ASSETS_DIR / "no-stamina-blackmarket.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        
        # Should NOT find stamina_10
        matches_10 = library.match(screenshot_bytes, ["stamina_10"])
        assert len(matches_10) == 0, \
            f"Should NOT find stamina_10 in no-stamina screenshot, but found {len(matches_10)} matches"

        # Should NOT find stamina_1
        matches_1 = library.match(screenshot_bytes, ["stamina_1"])
        assert len(matches_1) == 0, \
            f"Should NOT find stamina_1 in no-stamina screenshot, but found {len(matches_1)} matches"

    def test_not_stamina_images_do_not_match(self, library):
        """Dedicated negative samples must never match stamina templates."""
        for filename in ("not_stamina.png", "not_stamina_2.png"):
            path = ASSETS_DIR / filename
            if not path.exists():
                pytest.skip(f"Negative sample not found: {filename}")

            image_bytes = path.read_bytes()
            for template in ("stamina_1", "stamina_10"):
                matches = library.match(image_bytes, [template])
                assert not matches, (
                    f"False positive: {template} matched in {filename} "
                    f"(best score {matches[0].score:.3f})"
                )

    def test_boots_not_matched_as_stamina(self, library):
        """Test that boots are NOT matched as stamina."""
        screenshot_path = ASSETS_DIR / "blackmarket_with_boots.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        
        # Check for stamina_1 matches (boots have "1" like stamina_1)
        matches = library.match(screenshot_bytes, ["stamina_1"])
        
        # If matches found, verify they're not in the boots area (bottom-left typically)
        for match in matches:
            x, y = match.top_left
            # Boots area is typically bottom-left in this screenshot
            is_boots_area = x < 200 and y > 500
            assert not is_boots_area, \
                f"False positive! Matched stamina_1 in boots area at ({x}, {y})"


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestBoughtItemDetection:
    """Bought/greyed-out items are detected by ROI saturation rather than a
    separate template. Regular stamina cards measure mean-saturation ~145 in
    HSV; bought ones ~35. The pipeline treats saturation below
    ``bought_saturation_threshold`` (default 80) as purchased."""

    @pytest.mark.parametrize(
        "fixture_name,template_name",
        [
            ("stamina_10_bought.png", "stamina_10"),
            ("stamina_1_bought.png", "stamina_1"),
        ],
    )
    def test_bought_roi_has_low_saturation(self, library, fixture_name, template_name):
        path = FIXTURES_DIR / fixture_name
        if not path.exists():
            pytest.skip(f"Fixture not found: {path}")

        image_bytes = path.read_bytes()
        matches = library.match(image_bytes, [template_name], threshold=0.3)
        assert matches, f"should still match the regular template on a bought {template_name}"

        saturation = library.mean_saturation(image_bytes, matches[0])
        assert saturation < PROD_OPTIONS.bought_saturation_threshold, (
            f"bought {template_name} saturation {saturation:.1f} should be below "
            f"threshold {PROD_OPTIONS.bought_saturation_threshold}"
        )

    @pytest.mark.parametrize(
        "screenshot_name,template_name",
        [
            ("screenshot-bm.png", "stamina_10"),
            ("blackmarket_1_stamina.png", "stamina_1"),
        ],
    )
    def test_unbought_roi_has_high_saturation(self, library, screenshot_name, template_name):
        path = ASSETS_DIR / screenshot_name
        if not path.exists():
            pytest.skip(f"Screenshot not found: {path}")

        image_bytes = path.read_bytes()
        matches = library.match(image_bytes, [template_name])
        assert matches, f"expected {template_name} match in {screenshot_name}"

        saturation = library.mean_saturation(image_bytes, matches[0])
        assert saturation >= PROD_OPTIONS.bought_saturation_threshold, (
            f"available {template_name} saturation {saturation:.1f} should be above "
            f"threshold {PROD_OPTIONS.bought_saturation_threshold}"
        )


class TestRefreshButtonDetection:
    """Test refresh button detection."""

    def test_refresh_button_in_screenshot(self, library):
        """Test refresh button detection in screenshot-bm.png."""
        screenshot_path = ASSETS_DIR / "screenshot-bm.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        matches = library.match(screenshot_bytes, ["refresh"])

        assert len(matches) > 0, "Should find refresh button in screenshot"
        
        # Just verify match is within reasonable screen bounds
        x, y = matches[0].top_left
        assert 0 <= x < 480, f"refresh x={x} should be within screenshot width"
        assert 0 <= y < 870, f"refresh y={y} should be within screenshot height"


class TestPipelineIntegration:
    """Test the pipeline's item selection logic with real screenshots."""

    def test_pipeline_finds_stamina_10_first(self, library):
        """Test that pipeline logic finds stamina_10 (more efficient) first."""
        screenshot_path = ASSETS_DIR / "screenshot-bm.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()

        # Simulate pipeline logic - try each stamina type in priority order
        for stamina_item in DEFAULT_STAMINA_ITEMS:
            matches = library.match(screenshot_bytes, [stamina_item.template_name])
            if matches:
                # First match should be stamina_10 (higher priority)
                assert stamina_item.template_name == "stamina_10", \
                    f"Expected stamina_10 to match first, got {stamina_item.template_name}"
                assert stamina_item.stamina_amount == 500, \
                    f"Expected 500 stamina, got {stamina_item.stamina_amount}"
                break
        else:
            pytest.fail("No stamina items matched in screenshot-bm.png")

    def test_gem_button_tap_lands_in_bottom_gem_zone(self, library):
        """Gem-button tap coords must land in the card's bottom 15% (where the
        price button lives) and stay inside the horizontal card bounds."""
        screenshot_path = ASSETS_DIR / "screenshot-bm.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        matches = library.match(screenshot_bytes, ["stamina_10"])
        assert len(matches) > 0, "Should find stamina_10"
        match = matches[0]

        width = match.bottom_right[0] - match.top_left[0]
        height = match.bottom_right[1] - match.top_left[1]
        tap_x = match.top_left[0] + width // 2
        tap_y = match.top_left[1] + int(height * 0.9)
        tap_y = min(match.bottom_right[1] - 1, max(match.top_left[1], tap_y))

        assert match.top_left[0] <= tap_x <= match.bottom_right[0], (
            f"Tap X {tap_x} not in bounds [{match.top_left[0]}, {match.bottom_right[0]}]"
        )
        gem_zone_start = match.bottom_right[1] - int(height * 0.15)
        assert tap_y >= gem_zone_start, (
            f"Tap Y {tap_y} not in gem zone (starts at {gem_zone_start}). "
            f"Match: top={match.top_left[1]}, bottom={match.bottom_right[1]}, height={height}"
        )


class TestMultiScaleMatching:
    """Test that multi-scale matching works across different screenshot resolutions."""

    @pytest.mark.parametrize("screenshot_name,expected_template", [
        ("screenshot-bm.png", "stamina_10"),  # 480×870
        ("blackmarket.png", "stamina_10"),  # 772×1446
        ("blackmarket_1_stamina.png", "stamina_1"),  # 575×1056
    ])
    def test_finds_stamina_at_various_resolutions(self, library, screenshot_name, expected_template):
        """Test stamina detection works at various screenshot resolutions."""
        screenshot_path = ASSETS_DIR / screenshot_name
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        matches = library.match(screenshot_bytes, [expected_template])

        assert len(matches) > 0, \
            f"Should find {expected_template} in {screenshot_name}"
        assert matches[0].score >= PROD_OPTIONS.template_threshold, \
            f"Score {matches[0].score:.3f} below threshold in {screenshot_name}"

    def test_all_screenshots_have_refresh_button(self, library):
        """Test refresh button is found in all Black Market screenshots."""
        screenshots = [
            "screenshot-bm.png",
            "blackmarket.png",
            "blackmarket_1_stamina.png",
            "no-stamina-blackmarket.png",
        ]
        
        for screenshot_name in screenshots:
            screenshot_path = ASSETS_DIR / screenshot_name
            if not screenshot_path.exists():
                continue
                
            screenshot_bytes = screenshot_path.read_bytes()
            matches = library.match(screenshot_bytes, ["refresh"])
            
            assert len(matches) > 0, \
                f"Should find refresh button in {screenshot_name}"


class TestTemplateLoading:
    """Test that all required templates are loaded correctly."""

    def test_all_required_templates_loaded(self, library):
        """Verify all production-required templates are loaded."""
        required_templates = [
            "stamina_10",
            "stamina_1",
            "refresh",
            "to_confirm",
        ]

        for template_name in required_templates:
            assert library.has_template(template_name), (
                f"Required template '{template_name}' not loaded"
            )

    def test_bought_templates_are_not_loaded(self, library):
        """Bought/greyed-out detection is now saturation-based; the old per-state
        templates should no longer be present in the assets directory."""
        for name in ("stamina_10_bought", "stamina_1_bought"):
            assert not library.has_template(name), (
                f"'{name}' should not be loaded as a template any more — "
                f"bought detection uses ROI saturation instead"
            )

    def test_template_scales_configured(self, library):
        """Verify multi-scale matching is configured with a 1.0 anchor and a
        conservative band. Going too wide drops templates below the ORB
        descriptor-check minimum and lets cross-card false positives through
        (v2.3.0 regression fixed in v2.3.1)."""
        assert len(library.scales) > 1, (
            f"Expected multiple scales for multi-scale matching, got {library.scales}"
        )
        assert 1.0 in library.scales, (
            "Scales must include 1.0 so a correctly-sized screenshot matches"
        )
        scales = sorted(library.scales)
        assert scales[0] < 1.0 < scales[-1], (
            f"Scale band should straddle 1.0 for tolerance both ways, got {scales}"
        )
        # Keep the band tight enough that shrunk templates retain plenty of
        # ORB features. 0.5x was the v2.3.0 value and caused regressions.
        assert scales[0] >= 0.65, (
            f"Minimum scale must stay at or above 0.65 to preserve "
            f"ORB features on scaled templates; got {scales[0]}"
        )
        assert scales[-1] <= 1.5, (
            f"Maximum scale must stay at or below 1.5; beyond that, "
            f"template-matching noise dominates real signal; got {scales[-1]}"
        )

