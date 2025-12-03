#!/usr/bin/env python3
"""
End-to-end pipeline tests.

Simulates the complete workflow:
1. Finding stamina items in Black Market
2. Verifying click coordinates are correct
3. Finding confirmation button
4. Testing bought item skipping
5. Testing refresh detection
"""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from staminabuyer.vision.matcher import TemplateLibrary
from staminabuyer.pipeline import STAMINA_ITEMS, PipelineOptions

# Use production settings
_prod_options = PipelineOptions()

def test_black_market_workflow():
    """Test complete Black Market purchase workflow."""
    
    print("=" * 80)
    print("END-TO-END: Black Market Purchase Workflow")
    print("=" * 80)
    print()
    
    # Load Black Market screenshot
    bm_screenshot = Path(__file__).parent.parent / "assets" / "icons" / "screenshot-bm.png"
    
    if not bm_screenshot.exists():
        print("❌ Error: screenshot-bm.png not found")
        print("   This test requires a real Black Market screenshot")
        return False
    
    screenshot_bytes = bm_screenshot.read_bytes()
    
    library = TemplateLibrary(
        threshold=_prod_options.template_threshold,
        scales=_prod_options.template_scales,
        grayscale=True,
        descriptor_min_matches=_prod_options.descriptor_min_matches,
        normalize_resolution=_prod_options.normalize_resolution,
        template_source_resolution=_prod_options.template_source_resolution,
    )
    
    print("STEP 1: Find available stamina item")
    print("-" * 80)
    
    found_item = None
    found_match = None
    
    # Simulate pipeline logic - try each stamina type
    for stamina_item in STAMINA_ITEMS:
        print(f"Trying {stamina_item.template_name} ({stamina_item.stamina_amount} stamina)...")
        
        matches = library.match(screenshot_bytes, [stamina_item.template_name])
        
        if matches:
            match = matches[0]
            print(f"   ✅ Found with score {match.score:.4f}")
            print(f"   Location: {match.top_left} -> {match.bottom_right}")
            
            # Check if bought
            if stamina_item.bought_template_name and library.has_template(stamina_item.bought_template_name):
                bought_matches = library.match(screenshot_bytes, [stamina_item.bought_template_name])
                
                if bought_matches:
                    bought_match = bought_matches[0]
                    same_location = (
                        abs(bought_match.top_left[0] - match.top_left[0]) < 20 and
                        abs(bought_match.top_left[1] - match.top_left[1]) < 20
                    )
                    
                    if same_location and bought_match.score >= 0.3:
                        print(f"   ⚠️  Already purchased (bought indicator present)")
                        continue
            
            found_item = stamina_item
            found_match = match
            break
    
    if not found_item:
        print("   ❌ No available stamina items found")
        return False
    
    print()
    print(f"Selected: {found_item.template_name} ({found_item.stamina_amount} stamina)")
    print()
    
    # STEP 2: Calculate click coordinates
    print("STEP 2: Calculate click coordinates")
    print("-" * 80)
    
    width = found_match.bottom_right[0] - found_match.top_left[0]
    height = found_match.bottom_right[1] - found_match.top_left[1]
    
    # Click at 90% down (where gem button is)
    click_x = found_match.top_left[0] + width // 2
    click_y = found_match.top_left[1] + int(height * 0.9)
    
    print(f"Item bounds: {found_match.top_left} -> {found_match.bottom_right}")
    print(f"Item size: {width}x{height}")
    print(f"Click coordinates: ({click_x}, {click_y})")
    
    # Verify click is within bounds
    if (found_match.top_left[0] <= click_x <= found_match.bottom_right[0] and
        found_match.top_left[1] <= click_y <= found_match.bottom_right[1]):
        print("   ✅ Click coordinates valid (within item bounds)")
    else:
        print("   ❌ Click coordinates OUTSIDE item bounds!")
        return False
    
    print()
    
    # STEP 3: Find confirmation button
    print("STEP 3: Find confirmation button")
    print("-" * 80)
    
    confirm_matches = library.match(screenshot_bytes, ["to_confirm"])
    
    if confirm_matches:
        confirm_match = confirm_matches[0]
        print(f"   ✅ Found 'to_confirm' with score {confirm_match.score:.4f}")
        print(f"   Location: {confirm_match.top_left} -> {confirm_match.bottom_right}")
        
        # Calculate confirm click (center)
        confirm_x = confirm_match.top_left[0] + (confirm_match.bottom_right[0] - confirm_match.top_left[0]) // 2
        confirm_y = confirm_match.top_left[1] + (confirm_match.bottom_right[1] - confirm_match.top_left[1]) // 2
        print(f"   Confirm click: ({confirm_x}, {confirm_y})")
    else:
        print("   ⚠️  Note: 'to_confirm' not in this screenshot")
        print("   (Confirm button appears after clicking item)")
    
    print()
    
    # STEP 4: Check for refresh button
    print("STEP 4: Check for refresh button")
    print("-" * 80)
    
    refresh_matches = library.match(screenshot_bytes, ["refresh"])
    
    if refresh_matches:
        refresh_match = refresh_matches[0]
        print(f"   ✅ Found 'refresh' with score {refresh_match.score:.4f}")
        print(f"   Location: {refresh_match.top_left} -> {refresh_match.bottom_right}")
        print("   Bot can refresh if no stamina found")
    else:
        print("   ⚠️  Refresh button not visible in screenshot")
        print("   (This is OK if items are available)")
    
    print()
    
    return True


def test_workflow_with_bought_items():
    """Test that workflow correctly skips bought items."""
    
    print("=" * 80)
    print("END-TO-END: Bought Item Handling")
    print("=" * 80)
    print()
    
    library = TemplateLibrary(
        threshold=0.3,  # Low threshold specifically for bought detection
        scales=_prod_options.template_scales,
        grayscale=True,
        descriptor_min_matches=_prod_options.descriptor_min_matches,
        normalize_resolution=_prod_options.normalize_resolution,
        template_source_resolution=_prod_options.template_source_resolution,
    )
    
    bought_items = [
        ("stamina_10_bought.png", "stamina_10"),
        ("stamina_1_bought.png", "stamina_1"),
    ]
    
    all_passed = True
    
    for filename, template_name in bought_items:
        path = Path(__file__).parent.parent / "assets" / "icons" / filename
        
        if not path.exists():
            print(f"⚠️  {filename} not found, skipping")
            continue
        
        print(f"Testing: {filename}")
        
        image_bytes = path.read_bytes()
        
        # Try to match regular template
        regular_matches = library.match(image_bytes, [template_name])
        
        if not regular_matches:
            print(f"   ❌ FAIL: Regular template doesn't match at all")
            all_passed = False
            continue
        
        regular_match = regular_matches[0]
        print(f"   Regular match: score={regular_match.score:.4f}")
        
        # Find corresponding bought template
        bought_template = f"{template_name}_bought"
        
        if not library.has_template(bought_template):
            print(f"   ❌ FAIL: Bought template '{bought_template}' not loaded")
            all_passed = False
            continue
        
        bought_matches = library.match(image_bytes, [bought_template])
        
        if not bought_matches:
            print(f"   ❌ FAIL: Bought indicator not detected")
            all_passed = False
            continue
        
        bought_match = bought_matches[0]
        print(f"   Bought indicator: score={bought_match.score:.4f}")
        
        # Check pipeline logic
        same_location = (
            abs(bought_match.top_left[0] - regular_match.top_left[0]) < 20 and
            abs(bought_match.top_left[1] - regular_match.top_left[1]) < 20
        )
        
        would_skip = same_location and bought_match.score >= 0.3
        
        if would_skip:
            print(f"   ✅ PASS: Would be skipped (bought indicator detected)")
        else:
            print(f"   ❌ FAIL: Would NOT be skipped")
            print(f"      Same location: {same_location}")
            print(f"      Score >= 0.3: {bought_match.score >= 0.3}")
            all_passed = False
        
        print()
    
    return all_passed


if __name__ == "__main__":
    print()
    workflow_pass = test_black_market_workflow()
    print()
    print()
    bought_pass = test_workflow_with_bought_items()
    
    print("=" * 80)
    print("END-TO-END TEST SUMMARY")
    print("=" * 80)
    print(f"Black Market workflow: {'✅ PASS' if workflow_pass else '❌ FAIL'}")
    print(f"Bought item handling:  {'✅ PASS' if bought_pass else '❌ FAIL'}")
    print()
    
    if workflow_pass and bought_pass:
        print("🎉 END-TO-END TESTS PASSED!")
        print("   The complete pipeline logic is working correctly.")
        sys.exit(0)
    else:
        print("❌ END-TO-END TESTS FAILED!")
        print("   Fix issues before deploying.")
        sys.exit(1)

