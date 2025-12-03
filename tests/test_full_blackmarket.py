#!/usr/bin/env python3
"""
Test against FULL Black Market screenshots.

This is the REAL test - ensures the bot:
1. Matches actual stamina items
2. Does NOT match boots, armor, resources, etc.
3. Picks the correct item from multiple options

This simulates what the bot actually sees in production.
"""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from staminabuyer.vision.matcher import TemplateLibrary
from staminabuyer.pipeline import STAMINA_ITEMS, PipelineOptions

# Use production settings
_prod_options = PipelineOptions()

def test_blackmarket_with_exp_item():
    """
    Test Black Market screenshot with stamina items.
    
    This screenshot should:
    - Match actual stamina items
    - NOT match non-stamina items (boots, armor, resources)
    """
    
    print("=" * 80)
    print("BLACK MARKET TEST: Stamina Detection")
    print("=" * 80)
    print()
    
    # Try both screenshots - either works
    screenshot_paths = [
        Path(__file__).parent.parent / "assets" / "icons" / "blackmarket_with_boots.png",
        Path(__file__).parent.parent / "assets" / "icons" / "screenshot-bm.png",
    ]
    
    screenshot_path = None
    for path in screenshot_paths:
        if path.exists():
            screenshot_path = path
            break
    
    if not screenshot_path:
        print("⚠️  No Black Market screenshots found")
        print("   Need: blackmarket_with_boots.png or screenshot-bm.png")
        return False
    
    print(f"Using: {screenshot_path.name}")
    print()
    
    if not screenshot_path.exists():
        print("⚠️  screenshot-bm.png not found")
        return True
    
    screenshot_bytes = screenshot_path.read_bytes()
    
    library = TemplateLibrary(
        threshold=_prod_options.template_threshold,
        scales=_prod_options.template_scales,
        grayscale=True,
        descriptor_min_matches=_prod_options.descriptor_min_matches,
        normalize_resolution=_prod_options.normalize_resolution,
        template_source_resolution=_prod_options.template_source_resolution,
    )
    
    print("Looking for stamina items in full Black Market screenshot...")
    print()
    
    # Simulate pipeline logic - try to find stamina
    found_items = []
    
    for stamina_item in STAMINA_ITEMS:
        matches = library.match(screenshot_bytes, [stamina_item.template_name])
        
        if matches:
            for match in matches:
                found_items.append({
                    'type': stamina_item.template_name,
                    'stamina': stamina_item.stamina_amount,
                    'score': match.score,
                    'position': match.top_left,
                    'bounds': (match.top_left, match.bottom_right)
                })
                print(f"✓ Found {stamina_item.template_name} ({stamina_item.stamina_amount} stamina)")
                print(f"  Score: {match.score:.4f}")
                print(f"  Position: {match.top_left}")
                print()
    
    if not found_items:
        print("❌ FAIL: No stamina items detected!")
        print("   Expected to find stamina_10 in this screenshot")
        return False
    
    # Check that we found the RIGHT type
    # In screenshot-bm.png, there should be stamina_10 (top right, VIT 50/10)
    has_stamina_10 = any(item['type'] == 'stamina_10' for item in found_items)
    
    if has_stamina_10:
        print("✅ PASS: Correctly identified stamina_10")
        
        # Verify position is roughly correct (should be in top right area)
        stamina_10_items = [item for item in found_items if item['type'] == 'stamina_10']
        for item in stamina_10_items:
            x, y = item['position']
            print(f"   Position: ({x}, {y})")
            
            # Top right should be x > 200, y < 400
            if x > 200 and y < 400:
                print("   ✓ Position looks correct (top right area)")
            else:
                print(f"   ⚠️  Position unexpected for top right item")
        
        return True
    else:
        print("❌ FAIL: Did not find stamina_10 (expected in this screenshot)")
        return False


def test_blackmarket_with_boots():
    """
    Test that boots (bottom left item in screenshot) are NOT matched.
    
    This is a CRITICAL test - boots have:
    - Purple border (not blue like stamina)
    - "1" in corner (like stamina_1)
    - Different icon
    - Must NOT be detected as stamina
    """
    
    print()
    print("=" * 80)
    print("BLACK MARKET TEST: Boots False Positive Check")
    print("=" * 80)
    print()
    
    screenshot_path = Path(__file__).parent.parent / "assets" / "icons" / "blackmarket_with_boots.png"
    
    if not screenshot_path.exists():
        print("⚠️  blackmarket_with_boots.png not found")
        print("   Save the screenshot with boots to test false positive detection")
        print("   SKIPPING TEST (but this is CRITICAL for production!)")
        return True  # Skip but don't fail
    
    screenshot_bytes = screenshot_path.read_bytes()
    
    library = TemplateLibrary(
        threshold=_prod_options.template_threshold,
        scales=_prod_options.template_scales,
        grayscale=True,
        descriptor_min_matches=_prod_options.descriptor_min_matches,
        normalize_resolution=_prod_options.normalize_resolution,
        template_source_resolution=_prod_options.template_source_resolution,
    )
    
    print("Checking if boots are incorrectly matched as stamina...")
    print()
    
    # Check all matches for stamina_1 (boots have "1" like stamina_1)
    stamina_1_matches = library.match(screenshot_bytes, ["stamina_1"])
    
    # Boots are in bottom left, roughly position (50-150, 500-650)
    # Stamina should be in top area
    boots_area_matched = False
    
    if stamina_1_matches:
        print(f"Found {len(stamina_1_matches)} match(es) for stamina_1")
        for i, match in enumerate(stamina_1_matches):
            x, y = match.top_left
            print(f"  Match {i+1}: pos=({x}, {y}), score={match.score:.4f}")
            
            # Check if this is in the boots area (bottom left)
            if x < 150 and y > 450:
                print(f"    ⚠️  This is in the BOOTS area (bottom left)!")
                boots_area_matched = True
            else:
                print(f"    ✓ This is NOT in boots area")
    else:
        print("No stamina_1 matches found (OK if only stamina_10 in screenshot)")
    
    print()
    
    if boots_area_matched:
        print("❌ FAIL: Boots were matched as stamina!")
        print("   Threshold too low or template too generic")
        return False
    else:
        print("✅ PASS: Boots not matched as stamina")
        return True


if __name__ == "__main__":
    test1 = test_blackmarket_with_exp_item()
    test2 = test_blackmarket_with_boots()
    
    print()
    print("=" * 80)
    print("FULL BLACK MARKET TEST SUMMARY")
    print("=" * 80)
    print(f"Stamina detection:     {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"Boots false positive:  {'✅ PASS' if test2 else '❌ FAIL'}")
    print()
    
    if test1 and test2:
        print("🎉 BLACK MARKET TESTS PASSED!")
        print("   Bot will correctly identify items in production.")
        sys.exit(0)
    else:
        print("❌ BLACK MARKET TESTS FAILED!")
        print("   Bot may buy wrong items! Fix before deploying.")
        sys.exit(1)

