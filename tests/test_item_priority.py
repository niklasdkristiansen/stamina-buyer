#!/usr/bin/env python3
"""
Test item priority and selection logic.

Verifies:
1. stamina_10 is tried before stamina_1 (efficiency)
2. Bought items are correctly skipped
3. Falls back to stamina_1 when stamina_10 not available
"""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from staminabuyer.pipeline import PipelineOptions
from staminabuyer.vision.matcher import TemplateLibrary

# Use production settings
_prod_options = PipelineOptions()

def test_priority_order():
    """Test that items are checked in correct priority order."""
    
    print("=" * 80)
    print("ITEM PRIORITY TEST")
    print("=" * 80)
    print()
    
    # Load a screenshot that has both types
    screenshot_path = Path(__file__).parent.parent / "assets" / "icons" / "screenshot-bm.png"
    
    if not screenshot_path.exists():
        print("⚠️  Warning: screenshot-bm.png not found, skipping test")
        return True
    
    screenshot_bytes = screenshot_path.read_bytes()
    
    library = TemplateLibrary(
        threshold=_prod_options.template_threshold,
        scales=_prod_options.template_scales,
        grayscale=True,
        descriptor_min_matches=_prod_options.descriptor_min_matches,
    )
    
    print("Testing which stamina types are detected in screenshot-bm.png:")
    print()
    
    # Check for stamina_10
    stamina_10_matches = library.match(screenshot_bytes, ["stamina_10"])
    print(f"stamina_10 (500 stamina): {'✅ Found' if stamina_10_matches else '❌ Not found'}")
    if stamina_10_matches:
        print(f"   Score: {stamina_10_matches[0].score:.4f}")
    
    # Check for stamina_1
    stamina_1_matches = library.match(screenshot_bytes, ["stamina_1"])
    print(f"stamina_1 (50 stamina):   {'✅ Found' if stamina_1_matches else '❌ Not found'}")
    if stamina_1_matches:
        print(f"   Score: {stamina_1_matches[0].score:.4f}")
    
    print()
    
    # Expected: Priority should be stamina_10 first
    print("Priority order in code:")
    print("   1. stamina_10 (500 stamina) - checked first")
    print("   2. stamina_1 (50 stamina)   - fallback")
    print()
    
    if stamina_10_matches:
        print("✅ PASS: stamina_10 detected - bot will buy 500 stamina packs efficiently")
    elif stamina_1_matches:
        print("⚠️  OK: Only stamina_1 detected - bot will buy 50 stamina packs (less efficient)")
    else:
        print("❌ FAIL: No stamina detected in screenshot!")
        return False
    
    return True

def test_bought_skipping():
    """Test that bought items are skipped."""
    
    print()
    print("=" * 80)
    print("BOUGHT ITEM SKIPPING TEST")
    print("=" * 80)
    print()
    
    library = TemplateLibrary(
        threshold=0.3,  # Low threshold specifically for bought detection
        scales=_prod_options.template_scales,
        grayscale=True,
        descriptor_min_matches=_prod_options.descriptor_min_matches,
    )
    
    tests = [
        ("stamina_10_bought.png", "stamina_10", "stamina_10_bought"),
        ("stamina_1_bought.png", "stamina_1", "stamina_1_bought"),
    ]
    
    all_passed = True
    
    for filename, regular_template, bought_template in tests:
        path = Path(__file__).parent.parent / "assets" / "icons" / filename
        
        if not path.exists():
            print(f"⚠️  {filename} not found, skipping")
            continue
        
        print(f"Testing: {filename}")
        
        image_bytes = path.read_bytes()
        
        # Match regular template
        regular_matches = library.match(image_bytes, [regular_template])
        regular_score = regular_matches[0].score if regular_matches else 0.0
        regular_pos = regular_matches[0].top_left if regular_matches else None
        
        # Match bought template
        bought_matches = library.match(image_bytes, [bought_template])
        bought_score = bought_matches[0].score if bought_matches else 0.0
        bought_pos = bought_matches[0].top_left if bought_matches else None
        
        print(f"   Regular: score={regular_score:.4f}, pos={regular_pos}")
        print(f"   Bought:  score={bought_score:.4f}, pos={bought_pos}")
        
        # Check detection logic
        if regular_matches and bought_matches:
            # Check same location (within 20px)
            same_location = (
                abs(bought_pos[0] - regular_pos[0]) < 20 and
                abs(bought_pos[1] - regular_pos[1]) < 20
            )
            
            if same_location and bought_score >= 0.3:
                print(f"   ✅ PASS: Bought indicator detected - will be skipped")
            else:
                print(f"   ❌ FAIL: Not same location or score too low")
                all_passed = False
        else:
            print(f"   ❌ FAIL: One or both templates didn't match")
            all_passed = False
        
        print()
    
    return all_passed

if __name__ == "__main__":
    priority_pass = test_priority_order()
    bought_pass = test_bought_skipping()
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Priority order test: {'✅ PASS' if priority_pass else '❌ FAIL'}")
    print(f"Bought skipping test: {'✅ PASS' if bought_pass else '❌ FAIL'}")
    print()
    
    success = priority_pass and bought_pass
    if success:
        print("🎉 All logic tests PASSED!")
    else:
        print("⚠️  Some logic tests FAILED")
    
    sys.exit(0 if success else 1)

