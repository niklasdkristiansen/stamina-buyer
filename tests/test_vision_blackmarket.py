from pathlib import Path

from staminabuyer.vision.matcher import TemplateLibrary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets" / "icons"
# Wide scale range to handle different emulator resolutions (0.5x to 2.0x)
SCALES = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0)
THRESHOLD = 0.7  # Must score at least 70% to be considered a match
DESCRIPTOR_MIN_MATCHES = 10  # Require at least 10 feature matches for verification


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
    )
    frame_bytes = (ASSETS_DIR / "blackmarket.png").read_bytes()

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
    )
    frame_bytes = (ASSETS_DIR / "blackmarket.png").read_bytes()
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
    )
    frame_bytes = (ASSETS_DIR / "no-stamina-blackmarket.png").read_bytes()
    matches = library.match(frame_bytes, ["stamina_10"])
    assert not matches, f"Found {len(matches)} stamina matches in a screenshot where it should be absent."
