#!/usr/bin/env python3
"""Test template matching against the actual Black Market screenshot."""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from staminabuyer.vision.matcher import TemplateLibrary

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
    
    # Test with different thresholds
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
    success = test_screenshot_matching()
    sys.exit(0 if success else 1)

