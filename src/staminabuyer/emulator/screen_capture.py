"""
Alternative to ADB: Direct screen capture and mouse automation.

This module allows capturing emulator windows directly and simulating clicks
without requiring ADB installation or configuration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

try:
    import mss
    import mss.tools
    import pyautogui
    
    HAS_SCREEN_CAPTURE = True
except ImportError:
    HAS_SCREEN_CAPTURE = False

try:
    # Windows-specific imports
    from ctypes import windll

    import win32con
    import win32gui
    import win32ui
    
    HAS_WIN32 = True
except ImportError as e:
    HAS_WIN32 = False
    WIN32_IMPORT_ERROR = str(e)

try:
    # macOS-specific imports
    import Quartz
    from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    
    HAS_QUARTZ = True
except ImportError as e:
    HAS_QUARTZ = False
    QUARTZ_IMPORT_ERROR = str(e)


@dataclass
class WindowInfo:
    """Information about an emulator window."""
    
    title: str
    x: int
    y: int
    width: int
    height: int
    handle: int | None = None


class ScreenCaptureClient:
    """
    Captures screenshots and simulates clicks by interacting with the OS window system.
    
    This is an alternative to ADBClient that doesn't require ADB installation.
    Works by finding the emulator window and capturing/clicking directly.
    """
    
    def __init__(self, window_title: str) -> None:
        """
        Initialize client for a specific emulator window.
        
        Args:
            window_title: Title or partial title of the emulator window
                         (e.g., "BlueStacks", "LDPlayer", "NoxPlayer")
        """
        if not HAS_SCREEN_CAPTURE:
            raise RuntimeError(
                "Screen capture dependencies not installed. "
                "Install with: pip install mss pyautogui pillow"
            )
        
        self.window_title = window_title
        self._window_info: WindowInfo | None = None
        self._mss = mss.mss()
    
    def find_window(self) -> WindowInfo:
        """
        Find the emulator window by title.
        
        Returns:
            WindowInfo with window position and size
            
        Raises:
            RuntimeError: If window cannot be found
        """
        # Try platform-specific methods first
        if HAS_WIN32:
            return self._find_window_win32()
        elif HAS_QUARTZ:
            return self._find_window_quartz()
        else:
            return self._find_window_mss()
    
    def _find_window_quartz(self) -> WindowInfo:
        """Find window using macOS Quartz API."""
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID
        )
        
        matching_windows = []
        search_term = self.window_title.lower()
        
        for window in window_list:
            title = window.get('kCGWindowName', '')
            owner = window.get('kCGWindowOwnerName', '')
            layer = window.get('kCGWindowLayer', 0)
            bounds = window.get('kCGWindowBounds', {})
            
            # Only consider normal windows (layer 0)
            if layer != 0:
                continue
            
            # Check if title or owner matches
            title_matches = search_term in title.lower() if title else False
            owner_matches = search_term in owner.lower() if owner else False
            
            if title_matches or owner_matches:
                matching_windows.append((window, title, owner, bounds))
        
        if not matching_windows:
            raise RuntimeError(
                f"Could not find window with title/app containing '{self.window_title}'. "
                f"Make sure the emulator window is open and visible."
            )
        
        # Use the first matching window
        window, title, owner, bounds = matching_windows[0]
        
        # Extract position and size from bounds
        x = int(bounds.get('X', 0))
        y = int(bounds.get('Y', 0))
        width = int(bounds.get('Width', 0))
        height = int(bounds.get('Height', 0))
        
        return WindowInfo(
            title=title or owner,
            x=x,
            y=y,
            width=width,
            height=height,
            handle=window.get('kCGWindowNumber'),
        )
    
    def _find_window_win32(self) -> WindowInfo:
        """Find window using Windows API (most accurate)."""
        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if self.window_title.lower() in title.lower():
                    rect = win32gui.GetWindowRect(hwnd)
                    results.append((hwnd, title, rect))
        
        windows = []
        win32gui.EnumWindows(enum_callback, windows)
        
        if not windows:
            raise RuntimeError(
                f"Could not find window with title containing '{self.window_title}'. "
                f"Make sure the emulator window is open and visible."
            )
        
        # Use the first matching window
        hwnd, title, rect = windows[0]
        x, y, x2, y2 = rect
        
        # Account for window borders and title bar
        # Windows 10/11 have invisible borders
        border = 8  # Typical invisible border size
        title_bar = 31  # Typical title bar height
        
        return WindowInfo(
            title=title,
            x=x + border,
            y=y + title_bar,
            width=x2 - x - (2 * border),
            height=y2 - y - title_bar - border,
            handle=hwnd,
        )
    
    def _find_window_mss(self) -> WindowInfo:
        """
        Find window using cross-platform method (less accurate).
        
        This requires the user to manually specify window position,
        or we can capture the entire screen and search for the emulator.
        """
        # For cross-platform, we'll need to use pyautogui to find windows
        # This is less reliable, so we'll prompt the user
        raise RuntimeError(
            "Window detection not available on this platform. "
            "Please install python-xlib (Linux) or pyobjc (macOS) for window detection, "
            "or provide window coordinates manually."
        )
    
    def screencap(self) -> bytes:
        """
        Capture screenshot of the emulator window.
        
        Returns:
            PNG image bytes
        """
        # Update window position (in case it moved)
        self._window_info = self.find_window()
        
        # Capture the window region
        monitor = {
            "top": self._window_info.y,
            "left": self._window_info.x,
            "width": self._window_info.width,
            "height": self._window_info.height,
        }
        
        screenshot = self._mss.grab(monitor)
        
        # Convert to PNG bytes
        return mss.tools.to_png(screenshot.rgb, screenshot.size)
    
    def tap(self, x: int, y: int) -> None:
        """
        Simulate a tap at the given coordinates.
        
        Args:
            x: X coordinate relative to emulator window (0 = left edge)
            y: Y coordinate relative to emulator window (0 = top edge)
        """
        if self._window_info is None:
            self._window_info = self.find_window()
        
        # Convert to screen coordinates
        screen_x = self._window_info.x + x
        screen_y = self._window_info.y + y
        
        # Move and click
        pyautogui.click(screen_x, screen_y, duration=0.1)
        
        # Small delay to let the click register
        time.sleep(0.05)
    
    def get_window_size(self) -> tuple[int, int]:
        """
        Get the emulator window size.
        
        Returns:
            (width, height) tuple
        """
        if self._window_info is None:
            self._window_info = self.find_window()
        
        return (self._window_info.width, self._window_info.height)


def list_windows() -> list[str]:
    """
    List all visible windows (useful for finding emulator window title).
    
    Returns:
        List of window titles
    """
    if HAS_WIN32:
        windows = []
        
        def enum_callback(hwnd, results):
            try:
                # Check if window is visible
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                
                # Get window title
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                
                # Filter out some system windows that are not useful
                # But be permissive - we want to see most windows
                if title.strip():
                    results.append(title)
                
            except Exception:
                # If there's any error with a specific window, just skip it
                pass
            
            return True  # Continue enumeration
        
        win32gui.EnumWindows(enum_callback, windows)
        return windows
    elif HAS_QUARTZ:
        # macOS implementation using Quartz
        windows = []
        seen_apps = set()  # Track apps we've already added
        
        # Get list of all on-screen windows
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID
        )
        
        for window in window_list:
            # Get window title (kCGWindowName)
            title = window.get('kCGWindowName', '')
            
            # Get window owner (application name)
            owner = window.get('kCGWindowOwnerName', '')
            
            # Get window layer (0 is normal windows)
            layer = window.get('kCGWindowLayer', 0)
            
            # Get window bounds to check if it's a real window
            bounds = window.get('kCGWindowBounds', {})
            width = bounds.get('Width', 0)
            height = bounds.get('Height', 0)
            
            # Only include normal windows (layer 0) that are reasonably sized
            if layer == 0 and owner and width > 100 and height > 100:
                # If window has a title, use it
                if title and title.strip():
                    window_display = f"{title} ({owner})"
                    windows.append(window_display)
                # Otherwise, use just the app name (but only once per app)
                elif owner not in seen_apps:
                    windows.append(owner)
                    seen_apps.add(owner)
        
        return windows
    else:
        import sys
        error_msg = (
            f"Window listing not available on this platform ({sys.platform}). "
        )
        if 'WIN32_IMPORT_ERROR' in globals():
            error_msg += f"\nWin32 import error: {WIN32_IMPORT_ERROR}"
            error_msg += "\nInstall pywin32: pip install pywin32"
        elif 'QUARTZ_IMPORT_ERROR' in globals():
            error_msg += f"\nQuartz import error: {QUARTZ_IMPORT_ERROR}"
            error_msg += "\nInstall pyobjc: pip install pyobjc-framework-Quartz"
        else:
            error_msg += "\nManually specify your emulator window title."
        raise RuntimeError(error_msg)


def list_windows_debug() -> tuple[list[str], dict[str, any]]:
    """
    Debug version that returns both windows and stats about enumeration.
    
    Returns:
        (list of window titles, debug stats dict)
    """
    windows = []
    stats = {
        "total_checked": 0,
        "visible": 0,
        "with_title": 0,
        "errors": 0,
    }
    
    if HAS_WIN32:
        def enum_callback(hwnd, results):
            try:
                stats["total_checked"] += 1
                
                # Check if window is visible
                is_visible = win32gui.IsWindowVisible(hwnd)
                if is_visible:
                    stats["visible"] += 1
                
                # Get window title
                title = win32gui.GetWindowText(hwnd)
                
                if is_visible and title and title.strip():
                    stats["with_title"] += 1
                    results.append(title)
                    
            except Exception as e:
                stats["errors"] += 1
            
            return True  # Continue enumeration
        
        win32gui.EnumWindows(enum_callback, windows)
        return windows, stats
        
    elif HAS_QUARTZ:
        # macOS implementation
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID
        )
        
        stats["total_checked"] = len(window_list)
        seen_apps = set()
        
        for window in window_list:
            try:
                title = window.get('kCGWindowName', '')
                owner = window.get('kCGWindowOwnerName', '')
                layer = window.get('kCGWindowLayer', 0)
                bounds = window.get('kCGWindowBounds', {})
                width = bounds.get('Width', 0)
                height = bounds.get('Height', 0)
                
                if layer == 0 and width > 100 and height > 100:
                    stats["visible"] += 1
                    
                    if title and title.strip():
                        stats["with_title"] += 1
                        window_display = f"{title} ({owner})"
                        windows.append(window_display)
                    elif owner and owner not in seen_apps:
                        stats["with_title"] += 1
                        windows.append(owner)
                        seen_apps.add(owner)
                        
            except Exception as e:
                stats["errors"] += 1
        
        return windows, stats
    else:
        return [], {"error": "No window detection library available"}


def find_emulator_windows() -> list[str]:
    """
    Find likely emulator windows.
    
    Returns:
        List of window titles that are probably emulators
    """
    emulator_keywords = [
        "bluestacks",
        "blue stacks",
        "bstk",  # BlueStacks abbreviation
        "ldplayer",
        "noxplayer",
        "nox",
        "memu",
        "mumu",
        "android",
        "emulator",
        "evony",  # Game-specific
    ]
    
    all_windows = list_windows()
    
    emulator_windows = []
    for window in all_windows:
        window_lower = window.lower()
        if any(keyword in window_lower for keyword in emulator_keywords):
            emulator_windows.append(window)
    
    return emulator_windows

