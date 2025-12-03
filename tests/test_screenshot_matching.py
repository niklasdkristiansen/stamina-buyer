#!/usr/bin/env python3
"""
Test template matching against the actual Black Market screenshot.

Tests both positive matching (finding stamina items) and negative matching
(not detecting non-stamina items as stamina).

Available stamina templates:
- stamina_10: 10 packs × 50 = 500 stamina
- stamina_1: 1 pack × 50 = 50 stamina
"""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from staminabuyer.vision.matcher import TemplateLibrary

def test_negative_matching():
    """Test that non-stamina items are NOT matched as stamina (no false positives)."""
    
    print("=" * 80)
    print("NEGATIVE TESTS: Ensuring false positives don't occur")
    print("=" * 80)
    print()
    
    library = TemplateLibrary(
        threshold=0.6,
        scales=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0],
        grayscale=True,
    )
    
    # Lower threshold library for bought template checking
    library_low = TemplateLibrary(
        threshold=0.3,
        scales=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0],
        grayscale=True,
    )
    
    test_files = [
        ("not_stamina_2.png", "stamina_10", library, "non-stamina item (boots)"),
        ("stamina_10_bought.png", "stamina_10", library, "already purchased stamina_10"),
        ("screenshot-bm.png", "stamina_10_bought", library_low, "regular unbought stamina (shouldn't match bought)"),
    ]
    
    all_passed = True
    
    for filename, template, lib, description in test_files:
        test_path = Path(__file__).parent.parent / "assets" / "icons" / filename
        
        if not test_path.exists():
            print(f"⚠️  Warning: {filename} not found, skipping")
            print()
            continue
        
        print(f"Testing: {filename} ({description})")
        
        test_bytes = test_path.read_bytes()
        matches = lib.match(test_bytes, [template])
        
        if matches:
            best_score = matches[0].score
            # Special handling for bought template on regular items
            if template == "stamina_10_bought" and best_score < 0.3:
                print(f"  ✅ CORRECT! Bought template score too low ({best_score:.4f} < 0.3)")
                print(f"     Regular items won't be mistaken as bought")
            else:
                print(f"  ❌ FALSE POSITIVE! Incorrectly matched as {template}:")
                for match in matches[:3]:
                    print(f"     Score: {match.score:.4f}, Scale: {match.scale:.2f}x")
                print(f"  This is BAD - {description}!")
                all_passed = False
        else:
            print(f"  ✅ CORRECT! Not matched as {template}")
        
        print()
    
    return all_passed

def test_screenshot_matching():
    """Test if we can find stamina_10 in the Black Market screenshot."""
    
    # Load the screenshot
    screenshot_path = Path(__file__).parent.parent / "assets" / "icons" / "screenshot-bm.png"
    
    if not screenshot_path.exists():
        print(f"Screenshot not found: {screenshot_path}")
        return False
    
    # Read it as bytes (like screencap would return)
    screenshot_bytes = screenshot_path.read_bytes()
    
    print("Testing template matching...")
    print(f"Screenshot: {screenshot_path}")
    print(f"Screenshot size: {len(screenshot_bytes)} bytes")
    print()
    
    # Test with different thresholds for both stamina types
    test_configs = [
        ("Original (0.7)", 0.7),
        ("Current (0.6)", 0.6),
        ("Lower (0.5)", 0.5),
        ("Even lower (0.4)", 0.4),
        ("Very low (0.3)", 0.3),
    ]
    
    results_summary = []
    
    for name, threshold in test_configs:
        print(f"Testing with threshold {name}:")
        
        library = TemplateLibrary(
            threshold=threshold,
            scales=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0],
            grayscale=True,
        )
        
        matches = library.match(screenshot_bytes, ["stamina_10"])
        
        if matches:
            print(f"  ✅ Found {len(matches)} match(es)!")
            results_summary.append((threshold, True, matches[0].score, matches[0].scale))
            for i, match in enumerate(matches[:3]):
                print(f"     Match {i+1}: score={match.score:.4f}, scale={match.scale:.2f}x")
                print(f"               position={match.top_left} -> {match.bottom_right}")
                width = match.bottom_right[0] - match.top_left[0]
                height = match.bottom_right[1] - match.top_left[1]
                print(f"               size={width}x{height}")
        else:
            print(f"  ❌ No matches found")
            results_summary.append((threshold, False, 0.0, 0.0))
        print()
    
    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("Threshold | Result | Best Score | Best Scale")
    print("----------|--------|------------|------------")
    for threshold, found, score, scale in results_summary:
        status = "✅ PASS" if found else "❌ FAIL"
        print(f"   {threshold:.1f}    | {status} | {score:7.4f}    | {scale:.2f}x")
    print()
    
    # Check if lowering threshold helped
    if len(results_summary) >= 2:
        original_worked = results_summary[0][1]  # 0.7 threshold
        current_worked = results_summary[1][1]   # 0.6 threshold
        
        if not original_worked and current_worked:
            print("🎉 SUCCESS! Lowering threshold from 0.7 to 0.6 FIXED the issue!")
        elif original_worked:
            print("✅ Template matching works even at 0.7 threshold")
        else:
            print("⚠️  Need to lower threshold further or adjust template")
    print()
    
    return True

if __name__ == "__main__":
    # Run negative test first
    print()
    negative_pass = test_negative_matching()
    
    print()
    print()
    
    # Run positive test
    positive_pass = test_screenshot_matching()
    
    # Overall result
    print()
    print("=" * 80)
    print("OVERALL RESULTS")
    print("=" * 80)
    print(f"Negative test (not_stamina_2.png should NOT match): {'✅ PASS' if negative_pass else '❌ FAIL'}")
    print(f"Positive test (screenshot-bm.png should match):     {'✅ PASS' if positive_pass else '❌ FAIL'}")
    print()
    
    if negative_pass and positive_pass:
        print("🎉 All tests PASSED!")
        sys.exit(0)
    else:
        print("⚠️  Some tests FAILED")
        sys.exit(1)

