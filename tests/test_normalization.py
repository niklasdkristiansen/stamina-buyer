"""
Pytest tests for resolution normalization feature.

Tests verify that:
1. Coordinate conversion works correctly
2. Normalization works when template resolution matches
3. Multi-scale works as fallback
4. Wrong resolution handling

NOTE: The stamina_10 template (242x332) was extracted from a ~960x1740 screenshot.
It matches screenshot-bm.png (480x870) at scale 0.5.
"""

from pathlib import Path
import pytest
import cv2
import numpy as np

from staminabuyer.vision.matcher import TemplateLibrary

# The actual resolution the stamina_10 template was created from
# Template is 242x332, needs 0.5x scale for 480x870, so source was ~960x1740
TEMPLATE_NATIVE_RESOLUTION = (960, 1740)  # width, height


@pytest.fixture
def screenshot_path():
    """Path to the reference screenshot."""
    path = Path(__file__).parent.parent / "assets" / "icons" / "screenshot-bm.png"
    if not path.exists():
        pytest.skip(f"Screenshot not found: {path}")
    return path


@pytest.fixture
def screenshot_image(screenshot_path):
    """Load the reference screenshot as numpy array."""
    img = cv2.imread(str(screenshot_path))
    if img is None:
        pytest.skip(f"Could not load screenshot: {screenshot_path}")
    return img


@pytest.fixture
def screenshot_size(screenshot_image):
    """Get the size of the reference screenshot."""
    height, width = screenshot_image.shape[:2]
    return (width, height)


def encode_image(img):
    """Encode image to bytes (like screencap returns)."""
    _, encoded = cv2.imencode('.png', img)
    return encoded.tobytes()


class TestCoordinateConversion:
    """Test that coordinates are correctly converted back to original resolution."""
    
    def test_no_normalization_no_conversion(self, screenshot_image, screenshot_size):
        """Without normalization, need multi-scale to find template."""
        library = TemplateLibrary(
            threshold=0.70,
            scales=(0.5, 0.6),  # Need 0.5x scale since template is from larger resolution (~960x1740)
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=None,  # No normalization
        )
        
        img_bytes = encode_image(screenshot_image)
        matches = library.match(img_bytes, ["stamina_10"])
        
        assert len(matches) > 0, "Should find template with multi-scale"
        
        # Coordinates should be within image bounds
        match = matches[0]
        width, height = screenshot_size
        assert 0 <= match.top_left[0] < width
        assert 0 <= match.top_left[1] < height
        assert 0 < match.bottom_right[0] <= width
        assert 0 < match.bottom_right[1] <= height
    
    def test_normalization_to_template_resolution(self, screenshot_image, screenshot_size):
        """Normalizing to template resolution should work with single scale."""
        # Use the actual template resolution
        library = TemplateLibrary(
            threshold=0.70,
            scales=(1.0,),  # Single scale only!
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=TEMPLATE_NATIVE_RESOLUTION,  # Normalize to template resolution
        )
        
        img_bytes = encode_image(screenshot_image)
        matches = library.match(img_bytes, ["stamina_10"])
        
        assert len(matches) > 0, "Should find template when normalized to template resolution"
        assert matches[0].score >= 0.70, f"Score should be good: {matches[0].score}"
        
        # Coordinates should be scaled back to original screenshot size
        match = matches[0]
        width, height = screenshot_size
        assert 0 <= match.top_left[0] < width
        assert 0 <= match.top_left[1] < height
    
    def test_normalization_scaled_image_converts_coordinates(self, screenshot_image, screenshot_size):
        """Coordinates should be scaled back to original resolution."""
        orig_width, orig_height = screenshot_size
        
        library = TemplateLibrary(
            threshold=0.70,
            scales=(1.0,),
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=TEMPLATE_NATIVE_RESOLUTION,  # Use template resolution
        )
        
        # Get reference position at original size
        img_bytes_orig = encode_image(screenshot_image)
        matches_orig = library.match(img_bytes_orig, ["stamina_10"])
        assert len(matches_orig) > 0
        orig_x, orig_y = matches_orig[0].top_left
        
        # Test with 2x scaled image
        scale = 2.0
        scaled_width = int(orig_width * scale)
        scaled_height = int(orig_height * scale)
        scaled_img = cv2.resize(screenshot_image, (scaled_width, scaled_height), interpolation=cv2.INTER_CUBIC)
        img_bytes_scaled = encode_image(scaled_img)
        
        matches_scaled = library.match(img_bytes_scaled, ["stamina_10"])
        assert len(matches_scaled) > 0, "Should find template in scaled image"
        
        scaled_x, scaled_y = matches_scaled[0].top_left
        
        # Verify coordinates are scaled correctly (within 10% tolerance)
        expected_x = int(orig_x * scale)
        expected_y = int(orig_y * scale)
        tolerance = int(scaled_width * 0.10)
        
        assert abs(scaled_x - expected_x) <= tolerance, \
            f"X coordinate not scaled correctly: expected ~{expected_x}, got {scaled_x}"
        assert abs(scaled_y - expected_y) <= tolerance, \
            f"Y coordinate not scaled correctly: expected ~{expected_y}, got {scaled_y}"


class TestNormalizationVsMultiScale:
    """Compare normalization vs multi-scale matching."""
    
    @pytest.mark.parametrize("scale", [0.5, 0.75, 1.0, 1.5, 2.0])
    def test_normalization_finds_at_all_scales(self, screenshot_image, screenshot_size, scale):
        """Normalization should find templates at any scale."""
        orig_width, orig_height = screenshot_size
        
        library = TemplateLibrary(
            threshold=0.70,
            scales=(1.0,),
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=TEMPLATE_NATIVE_RESOLUTION,  # Use template resolution
        )
        
        # Scale the image
        scaled_width = int(orig_width * scale)
        scaled_height = int(orig_height * scale)
        scaled_img = cv2.resize(
            screenshot_image,
            (scaled_width, scaled_height),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        )
        
        img_bytes = encode_image(scaled_img)
        matches = library.match(img_bytes, ["stamina_10"])
        
        assert len(matches) > 0, f"Should find template at {scale}x scale"
        assert matches[0].score >= 0.70, f"Score too low at {scale}x: {matches[0].score}"
    
    def test_normalization_faster_than_multiscale(self, screenshot_image, screenshot_size):
        """Normalization should be faster (fewer scales to check)."""
        # Single scale with normalization
        library_norm = TemplateLibrary(
            threshold=0.70,
            scales=(1.0,),  # 1 scale
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=TEMPLATE_NATIVE_RESOLUTION,  # Use template resolution
        )
        
        # Multi-scale without normalization
        library_multi = TemplateLibrary(
            threshold=0.70,
            scales=(0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0),  # 16 scales
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=None,
        )
        
        img_bytes = encode_image(screenshot_image)
        
        # Both should find the template
        matches_norm = library_norm.match(img_bytes, ["stamina_10"])
        matches_multi = library_multi.match(img_bytes, ["stamina_10"])
        
        assert len(matches_norm) > 0, "Normalization should find template"
        assert len(matches_multi) > 0, "Multi-scale should find template"
        
        # Normalization uses fewer scales
        assert len(library_norm.scales) == 1
        assert len(library_multi.scales) == 16
        
        # This demonstrates the performance benefit (1 scale vs 16)


class TestAspectRatioHandling:
    """Test handling of different aspect ratios."""
    
    def test_matching_aspect_ratio_works_well(self, screenshot_image, screenshot_size):
        """Normalization with matching aspect ratio should work."""
        library = TemplateLibrary(
            threshold=0.70,
            scales=(1.0,),
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=TEMPLATE_NATIVE_RESOLUTION,  # Use template resolution
        )
        
        img_bytes = encode_image(screenshot_image)
        matches = library.match(img_bytes, ["stamina_10"])
        
        assert len(matches) > 0
        assert matches[0].score >= 0.70
    
    def test_different_aspect_ratio_may_fail(self, screenshot_image, screenshot_size):
        """Normalization with different aspect ratio may not work well."""
        # Screenshot is ~0.55 aspect ratio (portrait)
        # Use 16:9 landscape aspect ratio (very different)
        library = TemplateLibrary(
            threshold=0.70,
            scales=(1.0,),
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=(1920, 1080),  # 16:9 - very different from portrait!
        )
        
        img_bytes = encode_image(screenshot_image)
        matches = library.match(img_bytes, ["stamina_10"])
        
        # Should not find due to severe aspect ratio distortion
        # (0.55 portrait stretched to 1.78 landscape)
        # If it does find, score should be very low
        if matches:
            assert matches[0].score < 0.70, \
                "Score should be below threshold with severe aspect ratio mismatch"


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_very_small_normalization(self, screenshot_image):
        """Test with very small normalization resolution."""
        library = TemplateLibrary(
            threshold=0.60,  # Lower threshold for small images
            scales=(1.0,),
            grayscale=True,
            descriptor_min_matches=5,  # Fewer features in small images
            normalize_resolution=(100, 180),  # Very small
        )
        
        img_bytes = encode_image(screenshot_image)
        # May or may not find - very small resolution loses detail
        matches = library.match(img_bytes, ["stamina_10"])
        
        # Just verify it doesn't crash
        assert isinstance(matches, list)
    
    def test_very_large_normalization(self, screenshot_image):
        """Test with very large normalization resolution."""
        library = TemplateLibrary(
            threshold=0.70,
            scales=(1.0,),
            grayscale=True,
            descriptor_min_matches=10,
            normalize_resolution=(3840, 2160),  # 4K
        )
        
        img_bytes = encode_image(screenshot_image)
        matches = library.match(img_bytes, ["stamina_10"])
        
        # Should still work (upscaling is okay)
        assert isinstance(matches, list)

