from pathlib import Path

from staminabuyer.pipeline import PipelineOptions
from staminabuyer.vision.matcher import TemplateLibrary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets" / "icons"

# IMPORTANT: Use the exact same parameters as production to ensure tests are valid
_prod_options = PipelineOptions()
SCALES = _prod_options.template_scales
THRESHOLD = _prod_options.template_threshold
DESCRIPTOR_MIN_MATCHES = _prod_options.descriptor_min_matches
NORMALIZE_RES = _prod_options.normalize_resolution
TEMPLATE_SOURCE_RES = _prod_options.template_source_resolution


def _gem_tap_coordinates(match, vertical_ratio: float = 0.9) -> tuple[int, int]:
    width = match.bottom_right[0] - match.top_left[0]
    height = match.bottom_right[1] - match.top_left[1]
    tap_x = match.top_left[0] + width // 2
    tap_y = match.top_left[1] + int(height * vertical_ratio)
    tap_y = min(match.bottom_right[1] - 1, max(match.top_left[1], tap_y))
    return tap_x, tap_y


def test_stamina_10_template_aligns_with_gem_button() -> None:
    """Ensure the stamina_10 template match lands on the 3,000 gem button."""

    library = TemplateLibrary(
        template_dir=ASSETS_DIR,
        threshold=THRESHOLD,
        scales=SCALES,
        grayscale=True,
        descriptor_min_matches=DESCRIPTOR_MIN_MATCHES,
        normalize_resolution=NORMALIZE_RES,
        template_source_resolution=TEMPLATE_SOURCE_RES,
    )
    frame_bytes = (ASSETS_DIR / "screenshot-bm.png").read_bytes()

    matches = library.match(frame_bytes, ["stamina_10"])
    assert matches, f"Expected to find the stamina_10 card in the Black Market screenshot. Library has templates: {list(library._templates.keys())}"

    match = matches[0]
    tap_x, tap_y = _gem_tap_coordinates(match)

    # Tap should stay within the horizontal bounds of the card.
    assert match.top_left[0] <= tap_x <= match.bottom_right[0], f"Tap X {tap_x} not in bounds [{match.top_left[0]}, {match.bottom_right[0]}]"

    # Tap must land inside the bottom 15% of the card (gem price area).
    height = match.bottom_right[1] - match.top_left[1]
    gem_zone_start = match.bottom_right[1] - int(height * 0.15)
    assert tap_y >= gem_zone_start, f"Tap Y {tap_y} not in gem zone (starts at {gem_zone_start}). Match: top={match.top_left[1]}, bottom={match.bottom_right[1]}, height={height}"


def test_non_stamina_template_does_not_match_stamina_frame() -> None:
    """Ensure distractor icons do not match the Black Market screenshot."""

    library = TemplateLibrary(
        template_dir=ASSETS_DIR,
        threshold=THRESHOLD,
        scales=SCALES,
        grayscale=True,
        descriptor_min_matches=DESCRIPTOR_MIN_MATCHES,
        normalize_resolution=NORMALIZE_RES,
        template_source_resolution=TEMPLATE_SOURCE_RES,
    )
    frame_bytes = (ASSETS_DIR / "screenshot-bm.png").read_bytes()
    matches = library.match(frame_bytes, ["not-stamina"])
    assert not matches, f"Distractor icon unexpectedly matched stamina screenshot. Found {len(matches)} matches."


def test_stamina_missing_when_not_present() -> None:
    """Verify stamina template does not appear in the no-stamina screenshot."""

    library = TemplateLibrary(
        template_dir=ASSETS_DIR,
        threshold=THRESHOLD,
        scales=SCALES,
        grayscale=True,
        descriptor_min_matches=DESCRIPTOR_MIN_MATCHES,
        normalize_resolution=NORMALIZE_RES,
        template_source_resolution=TEMPLATE_SOURCE_RES,
    )
    frame_bytes = (ASSETS_DIR / "no-stamina-blackmarket.png").read_bytes()
    matches = library.match(frame_bytes, ["stamina_10"])
    assert not matches, f"Found {len(matches)} stamina matches in a screenshot where it should be absent."
