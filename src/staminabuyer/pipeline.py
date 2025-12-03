"""High-level orchestration for stamina purchase runs."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import EmulatorTarget
from .emulator.screen_capture import ScreenCaptureClient
from .vision.matcher import MatchResult, TemplateLibrary


@dataclass(slots=True)
class PipelineOptions:
    dry_run: bool = False
    max_retries: int = 3
    purchase_delay_seconds: float = 1.0
    jitter_seconds: float = 0.2
    post_purchase_delay_seconds: float = 3.0  # Wait after successful purchase for UI to update
    post_click_delay_seconds: float = 0.5  # Wait after clicking item for confirm dialog to appear
    refresh_button_icon: str = "refresh"
    max_refreshes: int = 100  # Maximum times to refresh the Black Market (can take 50-100+ tries)
    template_dir: Path | None = None
    stamina_pack_icon: str = "stamina_10"
    confirm_icon_name: str = "to_confirm"
    pack_size: int = 500  # stamina_10 = 10 packs × 50 stamina = 500 total
    gem_button_vertical_ratio: float = 0.9
    template_threshold: float = 0.6  # Lowered from 0.7 for better detection
    descriptor_min_matches: int = 10
    template_scales: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0)
    save_debug_screenshots: bool = False  # Save screenshots when matching fails


@dataclass(slots=True)
class PipelineResult:
    name: str
    requested: int
    purchased: int
    errors: list[str] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        return self.purchased >= self.requested and not self.errors


class PipelineRunner:
    """Runs the purchase pipeline sequentially for each emulator."""

    def __init__(
        self,
        options: PipelineOptions,
        console: Console | None = None,
        client_factory: Callable[[str], ScreenCaptureClient] | None = None,
        template_library: TemplateLibrary | None = None,
    ) -> None:
        self.options = options
        self.console = console or Console()
        self._client_factory = client_factory or (lambda window_title: ScreenCaptureClient(window_title=window_title))
        threshold = options.template_threshold
        self._templates = template_library or TemplateLibrary(
            options.template_dir,
            threshold=threshold,
            scales=options.template_scales,
            grayscale=True,
            descriptor_min_matches=options.descriptor_min_matches,
            console=self.console,  # Pass console for verbose logging
        )

    def run(self, targets: Sequence[EmulatorTarget]) -> list[PipelineResult]:
        results: list[PipelineResult] = []
        for target in targets:
            result = self._process_target(target)
            results.append(result)

        self._render_summary(results)
        return results

    def _process_target(self, target: EmulatorTarget) -> PipelineResult:
        self.console.rule(f"Processing {target.name}")

        if self.options.dry_run:
            self.console.log(
                f"[dry-run] Would buy {target.stamina} stamina from window '{target.name}'."
            )
            return PipelineResult(name=target.name, requested=target.stamina, purchased=target.stamina)

        client = self._client_factory(target.name)
        purchased = 0
        errors: list[str] = []

        try:
            purchased = self._execute_purchase_loop(client, target)
        except Exception as exc:  # pragma: no cover - runtime defensive path
            errors.append(str(exc))

        return PipelineResult(name=target.name, requested=target.stamina, purchased=purchased, errors=errors)

    def _execute_purchase_loop(self, client: ScreenCaptureClient, target: EmulatorTarget) -> int:
        # Focus the window first to ensure it's visible and on top
        self.console.log("Bringing window to foreground...")
        client.focus_window()
        """Buy stamina packs by matching templates and tapping confirm dialogs."""

        pack_size = self.options.pack_size
        if pack_size <= 0:
            raise ValueError("PipelineOptions.pack_size must be greater than zero.")

        packs_needed = ceil(target.stamina / pack_size)
        purchased = 0
        
        # Warn if we'll buy more than requested
        if packs_needed * pack_size > target.stamina:
            actual_amount = packs_needed * pack_size
            self.console.log(
                f"[yellow]Note: Will buy {actual_amount} stamina ({packs_needed} items × {pack_size}) "
                f"to meet request of {target.stamina}[/yellow]"
            )

        for attempt in range(1, packs_needed + 1):
            self.console.log(
                f"Buying item {attempt}/{packs_needed} for '{target.name}' ({pack_size} stamina per item)."
            )
            
            # Try to find stamina, refresh if needed
            pack_match = self._find_stamina_with_refresh(client)
            
            # Click the stamina item
            self._tap_gem_button(client, pack_match)
            
            # Wait for confirm dialog to appear
            delay = self.options.post_click_delay_seconds
            self.console.log(f"[dim]Waiting {delay}s for confirm dialog...[/dim]")
            time.sleep(delay)

            # Find and click confirm button
            confirm_match = self._match_with_retry(client, self.options.confirm_icon_name)
            self._tap_center(client, confirm_match)

            purchased += pack_size
            
            # Wait for purchase to complete and UI to update
            if attempt < packs_needed:  # Don't wait after the last purchase
                delay = self.options.post_purchase_delay_seconds
                self.console.log(f"[dim]Waiting {delay}s for purchase to complete...[/dim]")
                time.sleep(delay)

        return purchased

    def _render_summary(self, results: Sequence[PipelineResult]) -> None:
        table = Table(title="Stamina Buyer Run Summary")
        table.add_column("Emulator")
        table.add_column("Requested", justify="right")
        table.add_column("Purchased", justify="right")
        table.add_column("Errors")

        for result in results:
            table.add_row(
                result.name,
                str(result.requested),
                str(result.purchased),
                " | ".join(result.errors) if result.errors else "",
            )

        self.console.print(table)

    def _sleep_with_jitter(self) -> None:
        base = self.options.purchase_delay_seconds
        jitter = self.options.jitter_seconds
        if base <= 0 and jitter <= 0:
            return
        delta = random.uniform(-jitter, jitter)
        delay = max(0.0, base + delta)
        if delay > 0:
            time.sleep(delay)

    def _find_stamina_with_refresh(self, client: ScreenCaptureClient) -> MatchResult:
        """
        Try to find stamina item. If not found, refresh the Black Market and retry.
        
        Returns:
            MatchResult for the stamina item
            
        Raises:
            RuntimeError: If stamina cannot be found after refreshing
        """
        icon_name = self.options.stamina_pack_icon
        
        for refresh_attempt in range(self.options.max_refreshes + 1):
            # Try to find stamina (first attempt or after refresh)
            frame = client.screencap()
            matches = self._templates.match(frame, [icon_name])
            
            if matches:
                match = matches[0]
                self.console.log(
                    f"Found '{icon_name}' with score {match.score:.3f} "
                    f"at {match.top_left}->{match.bottom_right}."
                )
                return match
            
            # No stamina found
            if refresh_attempt < self.options.max_refreshes:
                # Try to refresh
                self.console.log(
                    f"No '{icon_name}' found. Refreshing Black Market... (refresh #{refresh_attempt + 1})"
                )
                
                try:
                    refresh_match = self._match_with_retry(client, self.options.refresh_button_icon)
                    self._tap_center(client, refresh_match)
                    
                    # Wait for refresh to complete
                    refresh_delay = 2.0
                    self.console.log(f"[dim]Waiting {refresh_delay}s for refresh to complete...[/dim]")
                    time.sleep(refresh_delay)
                except RuntimeError:
                    self.console.log("[yellow]Refresh button not found, continuing...[/yellow]")
            else:
                # Out of refresh attempts
                if self.options.save_debug_screenshots:
                    self._save_debug_screenshot(frame, icon_name)
                raise RuntimeError(
                    f"Failed to locate '{icon_name}' after {self.options.max_refreshes} refresh attempts."
                )
        
        raise RuntimeError(f"Failed to locate '{icon_name}'")
    
    def _match_with_retry(self, client: ScreenCaptureClient, icon_name: str) -> MatchResult:
        if not self._templates.has_template(icon_name):
            raise RuntimeError(f"Template '{icon_name}' is not available in assets/icons.")

        for attempt in range(1, self.options.max_retries + 1):
            frame = client.screencap()
            matches = self._templates.match(frame, [icon_name])
            if matches:
                match = matches[0]
                self.console.log(
                    f"Matched '{icon_name}' with score {match.score:.3f} "
                    f"at {match.top_left}->{match.bottom_right}."
                )
                return match

            self.console.log(
                f"Attempt {attempt}/{self.options.max_retries}: "
                f"no match for '{icon_name}', retrying after delay."
            )
            
            # Save debug screenshot if enabled and this is the last attempt
            if self.options.save_debug_screenshots and attempt == self.options.max_retries:
                self._save_debug_screenshot(frame, icon_name)
            
            self._sleep_with_jitter()

        raise RuntimeError(f"Failed to locate '{icon_name}' after {self.options.max_retries} retries.")

    def _tap_center(self, client: ScreenCaptureClient, match: MatchResult) -> None:
        self._tap_within_match(client, match, vertical_ratio=0.5)

    def _tap_gem_button(self, client: ScreenCaptureClient, match: MatchResult) -> None:
        ratio = self.options.gem_button_vertical_ratio
        ratio = min(max(ratio, 0.0), 1.0)
        self._tap_within_match(client, match, vertical_ratio=ratio)

    def _tap_within_match(self, client: ScreenCaptureClient, match: MatchResult, vertical_ratio: float) -> None:
        width = match.bottom_right[0] - match.top_left[0]
        height = match.bottom_right[1] - match.top_left[1]
        tap_x = match.top_left[0] + width // 2
        tap_y = match.top_left[1] + int(height * vertical_ratio)
        tap_y = min(match.bottom_right[1] - 1, max(match.top_left[1], tap_y))
        self.console.log(f"Tapping coordinates ({tap_x}, {tap_y}).")
        client.tap(tap_x, tap_y)
    
    def _save_debug_screenshot(self, frame: bytes, icon_name: str) -> None:
        """Save a debug screenshot when template matching fails."""
        try:
            import cv2
            import numpy as np
            from datetime import datetime
            
            # Decode the frame
            array = np.frombuffer(frame, dtype=np.uint8)
            image = cv2.imdecode(array, cv2.IMREAD_COLOR)
            
            if image is not None:
                # Create debug directory if it doesn't exist
                debug_dir = Path.cwd() / "debug_screenshots"
                debug_dir.mkdir(exist_ok=True)
                
                # Save with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = debug_dir / f"failed_{icon_name}_{timestamp}.png"
                cv2.imwrite(str(filename), image)
                
                self.console.log(f"[dim]Debug screenshot saved: {filename}[/dim]")
        except Exception as e:
            self.console.log(f"[dim]Could not save debug screenshot: {e}[/dim]")
