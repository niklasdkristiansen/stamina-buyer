"""
Comprehensive real-scenario tests for template matching.

Tests against actual Black Market screenshots at various resolutions to ensure
multi-scale template matching works correctly in production.

Available test screenshots:
- screenshot-bm.png (480×870): stamina_10 in top-right
- blackmarket_1_stamina.png (575×1056): stamina_1 in top-right  
- blackmarket.png (772×1446): stamina_10 in bottom-left
- no-stamina-blackmarket.png (558×1146): NO stamina items
- blackmarket_with_boots.png (563×1021): boots (false positive test)
"""

from pathlib import Path

import pytest

from staminabuyer.pipeline import PipelineOptions, STAMINA_ITEMS
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
        normalize_resolution=PROD_OPTIONS.normalize_resolution,
        template_source_resolution=PROD_OPTIONS.template_source_resolution,
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
        
        # Verify position is in top-right area (stamina_10 is top-right in this screenshot)
        x, y = matches[0].top_left
        assert x > 200, f"stamina_10 should be in right half, got x={x}"
        assert y < 400, f"stamina_10 should be in top half, got y={y}"

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
        
        # In blackmarket.png, stamina_10 is in bottom-left area
        x, y = matches[0].top_left
        assert x < 300, f"stamina_10 should be in left third, got x={x}"
        assert y > 500, f"stamina_10 should be in bottom half, got y={y}"


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


class TestBoughtItemDetection:
    """Test detection of already-purchased items."""

    def test_stamina_10_bought_template_exists(self, library):
        """Verify stamina_10_bought template is loaded."""
        assert library.has_template("stamina_10_bought"), \
            "stamina_10_bought template should be loaded"

    def test_stamina_1_bought_template_exists(self, library):
        """Verify stamina_1_bought template is loaded."""
        assert library.has_template("stamina_1_bought"), \
            "stamina_1_bought template should be loaded"

    def test_bought_indicator_matches_bought_screenshot(self, library):
        """Test that bought template matches bought item screenshot."""
        bought_path = ASSETS_DIR / "stamina_10_bought.png"
        if not bought_path.exists():
            pytest.skip(f"Bought screenshot not found: {bought_path}")

        bought_bytes = bought_path.read_bytes()
        
        # Use lower threshold for bought detection (as per pipeline logic)
        library_low = TemplateLibrary(
            template_dir=ASSETS_DIR,
            threshold=0.3,  # Lower threshold for bought detection
            scales=PROD_OPTIONS.template_scales,
            grayscale=True,
            descriptor_min_matches=PROD_OPTIONS.descriptor_min_matches,
        )
        
        matches = library_low.match(bought_bytes, ["stamina_10_bought"])
        assert len(matches) > 0, "Should find stamina_10_bought indicator in bought screenshot"


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
        
        # Refresh button should be in bottom area
        y = matches[0].top_left[1]
        assert y > 600, f"Refresh button should be near bottom, got y={y}"


class TestPipelineIntegration:
    """Test the pipeline's item selection logic with real screenshots."""

    def test_pipeline_finds_stamina_10_first(self, library):
        """Test that pipeline logic finds stamina_10 (more efficient) first."""
        screenshot_path = ASSETS_DIR / "screenshot-bm.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        
        # Simulate pipeline logic - try each stamina type in priority order
        for stamina_item in STAMINA_ITEMS:
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

    def test_gem_button_coordinates_within_bounds(self, library):
        """Test that gem button tap coordinates are within matched item bounds."""
        screenshot_path = ASSETS_DIR / "screenshot-bm.png"
        if not screenshot_path.exists():
            pytest.skip(f"Screenshot not found: {screenshot_path}")

        screenshot_bytes = screenshot_path.read_bytes()
        matches = library.match(screenshot_bytes, ["stamina_10"])
        
        assert len(matches) > 0, "Should find stamina_10"
        match = matches[0]
        
        # Calculate tap coordinates (90% down, center horizontal)
        width = match.bottom_right[0] - match.top_left[0]
        height = match.bottom_right[1] - match.top_left[1]
        tap_x = match.top_left[0] + width // 2
        tap_y = match.top_left[1] + int(height * 0.9)
        
        # Verify tap is within bounds
        assert match.top_left[0] <= tap_x <= match.bottom_right[0], \
            f"Tap X {tap_x} not in bounds [{match.top_left[0]}, {match.bottom_right[0]}]"
        assert match.top_left[1] <= tap_y <= match.bottom_right[1], \
            f"Tap Y {tap_y} not in bounds [{match.top_left[1]}, {match.bottom_right[1]}]"


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
            "stamina_10_bought",
            "stamina_1",
            "stamina_1_bought",
            "refresh",
            "to_confirm",
        ]
        
        for template_name in required_templates:
            assert library.has_template(template_name), \
                f"Required template '{template_name}' not loaded"

    def test_template_scales_configured(self, library):
        """Verify multi-scale matching is configured."""
        assert len(library.scales) > 1, \
            f"Expected multiple scales for multi-scale matching, got {library.scales}"
        # Templates extracted from ~480×870 source, need scales UP for larger screenshots
        assert 0.5 in library.scales or 0.6 in library.scales, \
            "Should have scales for smaller screenshots (scale down)"
        assert 1.0 in library.scales, \
            "Should have 1.0 scale for same-resolution matching"
        assert 1.5 in library.scales or 1.7 in library.scales or 2.0 in library.scales, \
            "Should have large scales for bigger screenshots (772×1446 needs ~1.6x)"

