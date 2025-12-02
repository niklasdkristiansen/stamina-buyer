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
except ImportError:
    HAS_WIN32 = False


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
        else:
            return self._find_window_mss()
    
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
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:  # Only include windows with titles
                    results.append(title)
        
        win32gui.EnumWindows(enum_callback, windows)
        return windows
    else:
        raise RuntimeError(
            "Window listing not available on this platform. "
            "Manually specify your emulator window title."
        )


def find_emulator_windows() -> list[str]:
    """
    Find likely emulator windows.
    
    Returns:
        List of window titles that are probably emulators
    """
    emulator_keywords = [
        "bluestacks",
        "ldplayer",
        "noxplayer",
        "memu",
        "mumu",
        "android",
        "emulator",
    ]
    
    all_windows = list_windows()
    
    emulator_windows = []
    for window in all_windows:
        window_lower = window.lower()
        if any(keyword in window_lower for keyword in emulator_keywords):
            emulator_windows.append(window)
    
    return emulator_windows

