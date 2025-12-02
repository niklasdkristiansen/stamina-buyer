#!/usr/bin/env python3
"""
Debug script to test window detection on Windows and macOS.
Run this on any machine to see what windows are being detected.
"""

import sys

print("=" * 80)
print("Window Detection Debug Script")
print("=" * 80)
print()

# Check platform
print(f"Platform: {sys.platform}")
print()

# Try to import platform-specific libraries
if sys.platform == 'win32':
    try:
        import win32gui
        print("✓ win32gui imported successfully")
        HAS_WIN32 = True
    except ImportError as e:
        print(f"✗ Failed to import win32gui: {e}")
        print("  Install with: pip install pywin32")
        sys.exit(1)
    HAS_QUARTZ = False
elif sys.platform == 'darwin':
    try:
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        print("✓ Quartz imported successfully")
        HAS_QUARTZ = True
    except ImportError as e:
        print(f"✗ Failed to import Quartz: {e}")
        print("  Install with: pip install pyobjc-framework-Quartz")
        sys.exit(1)
    HAS_WIN32 = False
else:
    print(f"✗ Unsupported platform: {sys.platform}")
    print("  This script only supports Windows and macOS")
    sys.exit(1)

print()
print("=" * 80)
print("Enumerating All Windows")
print("=" * 80)
print()

windows = []
stats = {
    "total": 0,
    "visible": 0,
    "with_title": 0,
}

print("Starting enumeration...")
print()

try:
    if HAS_WIN32:
        def callback(hwnd, extra):
            try:
                stats["total"] += 1
                
                is_visible = win32gui.IsWindowVisible(hwnd)
                title = win32gui.GetWindowText(hwnd)
                
                print(f"Window {stats['total']}:")
                print(f"  Handle: {hwnd}")
                print(f"  Visible: {is_visible}")
                print(f"  Title: '{title}'")
                
                if is_visible:
                    stats["visible"] += 1
                    if title and title.strip():
                        stats["with_title"] += 1
                        windows.append(title)
                        print(f"  ✓ Added to list")
                
                print()
                
            except Exception as e:
                print(f"  Error: {e}")
                print()
            
            return True  # Continue enumeration
        
        win32gui.EnumWindows(callback, None)
        
    elif HAS_QUARTZ:
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID
        )
        
        seen_apps = set()
        
        for i, window in enumerate(window_list, 1):
            try:
                stats["total"] += 1
                
                title = window.get('kCGWindowName', '')
                owner = window.get('kCGWindowOwnerName', '')
                layer = window.get('kCGWindowLayer', 0)
                window_id = window.get('kCGWindowNumber', 0)
                bounds = window.get('kCGWindowBounds', {})
                width = bounds.get('Width', 0)
                height = bounds.get('Height', 0)
                
                print(f"Window {i}:")
                print(f"  ID: {window_id}")
                print(f"  Owner: '{owner}'")
                print(f"  Title: '{title}'")
                print(f"  Layer: {layer}")
                print(f"  Size: {width}x{height}")
                
                if layer == 0 and width > 100 and height > 100:
                    stats["visible"] += 1
                    if title and title.strip():
                        stats["with_title"] += 1
                        window_display = f"{title} ({owner})"
                        windows.append(window_display)
                        print(f"  ✓ Added to list as: '{window_display}'")
                    elif owner and owner not in seen_apps:
                        stats["with_title"] += 1
                        windows.append(owner)
                        seen_apps.add(owner)
                        print(f"  ✓ Added to list as: '{owner}' (app name only)")
                    else:
                        print(f"  ⊘ Skipped (no title, app already added)")
                else:
                    print(f"  ⊘ Skipped (layer={layer}, size={width}x{height})")
                
                print()
                
            except Exception as e:
                print(f"  Error: {e}")
                print()
    
    print("=" * 80)
    print("Enumeration Complete")
    print("=" * 80)
    print()
    print(f"Total windows checked: {stats['total']}")
    print(f"Visible windows: {stats['visible']}")
    print(f"Windows with titles: {stats['with_title']}")
    print()
    print("=" * 80)
    print(f"Windows List ({len(windows)} windows)")
    print("=" * 80)
    print()
    
    for i, window in enumerate(windows, 1):
        print(f"{i:3d}. {window}")
    
    print()
    print("=" * 80)
    print("Looking for Emulator Keywords")
    print("=" * 80)
    print()
    
    emulator_keywords = [
        "bluestacks", "blue stacks", "bstk",
        "ldplayer", "noxplayer", "nox",
        "memu", "mumu", "android", "emulator", "evony"
    ]
    
    emulator_windows = []
    for window in windows:
        window_lower = window.lower()
        matched_keywords = [kw for kw in emulator_keywords if kw in window_lower]
        if matched_keywords:
            emulator_windows.append(window)
            print(f"✓ {window}")
            print(f"  Matched keywords: {', '.join(matched_keywords)}")
            print()
    
    if not emulator_windows:
        print("No emulator windows found!")
        print()
        print("Hint: Look through the windows list above for your emulator window")
        print("      and let me know what the exact title is.")
    
except Exception as e:
    print(f"Error during enumeration: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 80)
print("Done")
print("=" * 80)

