"""Tests for ScreenCaptureClient's caching and error handling."""

from __future__ import annotations

import pytest

from staminabuyer.emulator import screen_capture as sc


@pytest.fixture
def stub_window(monkeypatch):
    """Provide a stable WindowInfo regardless of platform."""
    info = sc.WindowInfo(title="Test", x=10, y=20, width=300, height=400, handle=1)

    def _fake_find(self: sc.ScreenCaptureClient) -> sc.WindowInfo:
        fake_find.calls += 1
        return info

    fake_find = _fake_find
    fake_find.calls = 0  # type: ignore[attr-defined]
    monkeypatch.setattr(sc.ScreenCaptureClient, "find_window", fake_find)
    return info, fake_find


@pytest.fixture
def _require_capture():
    if not sc.HAS_SCREEN_CAPTURE:
        pytest.skip(f"screen capture deps not importable: {sc.SCREEN_CAPTURE_IMPORT_ERROR}")


class TestWindowInfoCaching:
    def test_reuses_cached_info_within_ttl(self, _require_capture, stub_window):
        _, fake_find = stub_window
        client = sc.ScreenCaptureClient("test", window_info_ttl_seconds=10.0)

        client._get_window_info()
        client._get_window_info()
        client._get_window_info()

        assert fake_find.calls == 1, "TTL-cached lookups should not re-query"

    def test_ttl_zero_refreshes_every_call(self, _require_capture, stub_window):
        _, fake_find = stub_window
        client = sc.ScreenCaptureClient("test", window_info_ttl_seconds=0.0)

        client._get_window_info()
        client._get_window_info()

        assert fake_find.calls == 2, "TTL=0 should re-query on every call"

    def test_refresh_window_info_forces_requery(self, _require_capture, stub_window):
        _, fake_find = stub_window
        client = sc.ScreenCaptureClient("test", window_info_ttl_seconds=10.0)

        client._get_window_info()
        assert fake_find.calls == 1

        client.refresh_window_info()
        assert fake_find.calls == 2, "explicit refresh must bypass TTL cache"


class TestImportErrorSurfacing:
    def test_construct_without_deps_surfaces_real_error(self, monkeypatch):
        monkeypatch.setattr(sc, "HAS_SCREEN_CAPTURE", False)
        monkeypatch.setattr(sc, "SCREEN_CAPTURE_IMPORT_ERROR", "missing dependency: pyautogui")

        with pytest.raises(RuntimeError, match="missing dependency: pyautogui"):
            sc.ScreenCaptureClient("test")


class _FakeScreenshot:
    """Minimal stand-in for an mss screenshot object."""

    def __init__(self, width: int, height: int):
        self.size = (width, height)
        self.rgb = b"\x00" * (width * height * 3)


class TestRetinaDpiClickCorrection:
    """Verify tap coordinates are converted from capture pixels to logical points."""

    def _patch_mss(self, client: sc.ScreenCaptureClient, monkeypatch, retina: bool):
        """Replace the client's mss object so screenshot.size reflects a chosen DPI ratio."""
        ratio = 2 if retina else 1

        class _FakeMss:
            def grab(self, monitor):
                return _FakeScreenshot(monitor["width"] * ratio, monitor["height"] * ratio)

        client._mss = _FakeMss()
        monkeypatch.setattr(sc.mss.tools, "to_png", lambda rgb, size: b"fake-png")

    def test_retina_capture_scales_tap_by_half(self, _require_capture, stub_window, monkeypatch):
        clicks: list[tuple[float, float]] = []
        monkeypatch.setattr(sc.pyautogui, "click", lambda x, y, duration=0.1: clicks.append((x, y)))

        client = sc.ScreenCaptureClient("test", window_info_ttl_seconds=10.0)
        self._patch_mss(client, monkeypatch, retina=True)

        client.screencap()  # populate DPI scale
        # Match coordinate (200, 300) in capture-pixel space of a Retina screen
        # should correspond to logical (100, 150) within the window.
        client.tap(200, 300)

        # Window origin is (10, 20) per the stub_window fixture.
        assert clicks == [(10 + 100.0, 20 + 150.0)]
        assert client.capture_dpi_scale == (2.0, 2.0)

    def test_non_retina_capture_is_identity(self, _require_capture, stub_window, monkeypatch):
        clicks: list[tuple[float, float]] = []
        monkeypatch.setattr(sc.pyautogui, "click", lambda x, y, duration=0.1: clicks.append((x, y)))

        client = sc.ScreenCaptureClient("test", window_info_ttl_seconds=10.0)
        self._patch_mss(client, monkeypatch, retina=False)

        client.screencap()
        client.tap(50, 60)

        assert clicks == [(10 + 50, 20 + 60)]
        assert client.capture_dpi_scale == (1.0, 1.0)

    def test_tap_before_screencap_uses_identity(self, _require_capture, stub_window, monkeypatch):
        """Tapping before any capture should still hit the right place on non-Retina."""
        clicks: list[tuple[float, float]] = []
        monkeypatch.setattr(sc.pyautogui, "click", lambda x, y, duration=0.1: clicks.append((x, y)))

        client = sc.ScreenCaptureClient("test", window_info_ttl_seconds=10.0)
        client.tap(50, 60)

        assert clicks == [(10 + 50, 20 + 60)]
