"""Direct screen capture and mouse automation.

Finds the emulator's native OS window by title, grabs its pixels via ``mss``,
and synthesises clicks with ``pyautogui``. This is the sole I/O backend —
there is no ADB path — so the user must keep the emulator window visible
(not minimized or occluded) during a run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger(__name__)

# Screen capture (cross-platform) — mss and pyautogui both touch the display
# backend at import time, so we isolate each failure mode with its real error
# and surface it to users instead of silently disabling the whole feature.
HAS_SCREEN_CAPTURE = False
SCREEN_CAPTURE_IMPORT_ERROR: str | None = None
try:
    import mss
    import mss.tools
    import pyautogui

    HAS_SCREEN_CAPTURE = True
except ImportError as _exc:
    SCREEN_CAPTURE_IMPORT_ERROR = f"missing dependency: {_exc}"
    _logger.warning("Screen capture unavailable (%s)", SCREEN_CAPTURE_IMPORT_ERROR)
except Exception as _exc:  # noqa: BLE001 - intentional: backends raise platform-specific errors
    # Real cases seen in practice:
    #   KeyError("DISPLAY")                 -> Linux without X11
    #   Xlib.error.DisplayConnectionError   -> X11 can't connect
    SCREEN_CAPTURE_IMPORT_ERROR = f"backend init failed ({type(_exc).__name__}): {_exc}"
    _logger.warning("Screen capture unavailable (%s)", SCREEN_CAPTURE_IMPORT_ERROR)

# Windows
HAS_WIN32 = False
WIN32_IMPORT_ERROR: str | None = None
try:
    from ctypes import windll  # noqa: F401 - used elsewhere in this module

    import win32con  # noqa: F401
    import win32gui
    import win32ui  # noqa: F401

    HAS_WIN32 = True
except ImportError as _exc:
    WIN32_IMPORT_ERROR = str(_exc)

# macOS
HAS_QUARTZ = False
QUARTZ_IMPORT_ERROR: str | None = None
try:
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListOptionOnScreenOnly,
    )

    HAS_QUARTZ = True
except ImportError as _exc:
    QUARTZ_IMPORT_ERROR = str(_exc)


@dataclass
class WindowInfo:
    """Information about an emulator window."""

    title: str
    x: int
    y: int
    width: int
    height: int
    handle: int | None = None


DEFAULT_WINDOW_INFO_TTL_SECONDS = 1.5


class ScreenCaptureClient:
    """
    Captures screenshots and simulates clicks by interacting with the OS window system.

    Locates the emulator by (partial) window title, grabs its bitmap via
    ``mss``, and dispatches clicks via ``pyautogui``. No ADB involved.

    Window metadata is cached for ``window_info_ttl_seconds`` so a tight
    purchase loop doesn't re-enumerate every OS window on every frame. Use
    :meth:`refresh_window_info` to force a refresh (e.g. if the user has moved
    or resized the emulator window).
    """

    def __init__(
        self,
        window_title: str,
        window_info_ttl_seconds: float = DEFAULT_WINDOW_INFO_TTL_SECONDS,
    ) -> None:
        """
        Initialize client for a specific emulator window.

        Args:
            window_title: Title or partial title of the emulator window
                (e.g., "BlueStacks", "LDPlayer", "NoxPlayer").
            window_info_ttl_seconds: How long window position/size is cached
                before we re-enumerate. Keeps per-frame cost low while still
                picking up drags/resizes within one or two purchase iterations.
        """
        if not HAS_SCREEN_CAPTURE:
            detail = f" ({SCREEN_CAPTURE_IMPORT_ERROR})" if SCREEN_CAPTURE_IMPORT_ERROR else ""
            raise RuntimeError(
                "Screen capture dependencies not available" + detail + ". "
                "Install with: pip install mss pyautogui pillow"
            )

        self.window_title = window_title
        self._window_info: WindowInfo | None = None
        self._window_info_fetched_at: float = 0.0
        self._window_info_ttl = max(0.0, window_info_ttl_seconds)
        self._mss = mss.mss()
        # DPI ratio between captured bitmap pixels (mss) and logical points
        # (pyautogui / window bounds). 2.0 on a Retina display, 1.0 on most
        # Windows setups. Populated lazily on first screencap().
        self._capture_dpi_scale: tuple[float, float] = (1.0, 1.0)

    def refresh_window_info(self) -> WindowInfo:
        """Force a re-query of the window position/size and return it."""
        self._window_info = self.find_window()
        self._window_info_fetched_at = time.monotonic()
        return self._window_info

    def _get_window_info(self) -> WindowInfo:
        """Return cached window info, refreshing if the TTL has expired."""
        now = time.monotonic()
        if (
            self._window_info is None
            or now - self._window_info_fetched_at > self._window_info_ttl
        ):
            self._window_info = self.find_window()
            self._window_info_fetched_at = now
        return self._window_info

    def focus_window(self) -> None:
        """
        Bring the window to the front and focus it.

        This ensures the window is visible and active before capturing/clicking.
        """
        self._get_window_info()

        if HAS_WIN32 and self._window_info.handle:
            # Windows: Use win32gui to bring window to foreground
            try:
                import win32con
                if win32gui.IsIconic(self._window_info.handle):
                    # If minimized, restore it
                    win32gui.ShowWindow(self._window_info.handle, win32con.SW_RESTORE)
                # Bring to foreground
                win32gui.SetForegroundWindow(self._window_info.handle)
                time.sleep(0.3)  # Give window time to come to front
            except Exception:
                # If this fails, not critical - continue anyway
                pass
        elif HAS_QUARTZ and self._window_info.handle:
            # macOS: Use AppleScript to activate the application
            try:
                import subprocess
                # Get the owner name from the window info (it's stored in title if it's just the app name)
                # or we need to query it again
                app_name = self._window_info.title.split('(')[-1].rstrip(')') if '(' in self._window_info.title else self._window_info.title
                script = f'tell application "{app_name}" to activate'
                subprocess.run(['osascript', '-e', script], check=False, capture_output=True)
                time.sleep(0.3)  # Give window time to come to front
            except Exception:
                # If this fails, not critical - continue anyway
                pass

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
        info = self._get_window_info()
        monitor = {
            "top": info.y,
            "left": info.x,
            "width": info.width,
            "height": info.height,
        }

        screenshot = self._mss.grab(monitor)

        # mss returns device pixels; the monitor dict is in logical points.
        # Remember the ratio so tap() can convert match coordinates (which are
        # in the captured bitmap's pixel space) back to logical points for
        # pyautogui.click().
        capture_w, capture_h = screenshot.size
        if info.width > 0 and info.height > 0:
            self._capture_dpi_scale = (
                capture_w / info.width,
                capture_h / info.height,
            )

        return mss.tools.to_png(screenshot.rgb, screenshot.size)

    def tap(self, x: int, y: int) -> None:
        """
        Simulate a tap at the given coordinates.

        ``x`` and ``y`` are expected to be in the captured screenshot's pixel
        space (which is what template matching returns). They are converted
        back to logical points using the DPI ratio measured during the most
        recent ``screencap()`` before being handed to pyautogui.

        Args:
            x: X coordinate relative to the captured emulator window
            y: Y coordinate relative to the captured emulator window
        """
        info = self._get_window_info()
        scale_x, scale_y = self._capture_dpi_scale

        logical_x = x / scale_x if scale_x else x
        logical_y = y / scale_y if scale_y else y

        screen_x = info.x + logical_x
        screen_y = info.y + logical_y

        pyautogui.click(screen_x, screen_y, duration=0.1)
        time.sleep(0.05)

    @property
    def capture_dpi_scale(self) -> tuple[float, float]:
        """DPI ratio (x, y) between captured bitmap pixels and logical points.

        1.0 means no scaling; 2.0 means the capture is at 2× the logical
        window size (typical for Retina on macOS). Only meaningful after at
        least one call to :meth:`screencap`.
        """
        return self._capture_dpi_scale

    def get_window_size(self) -> tuple[int, int]:
        """
        Get the emulator window size.

        Returns:
            (width, height) tuple
        """
        info = self._get_window_info()
        return (info.width, info.height)


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


def list_windows_debug() -> tuple[list[str], dict[str, Any]]:
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

            except Exception:
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

            except Exception:
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

