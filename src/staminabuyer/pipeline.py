"""High-level orchestration for stamina purchase runs."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import EmulatorTarget
from .emulator.screen_capture import ScreenCaptureClient
from .vision.matcher import MatchResult, TemplateLibrary


@dataclass
class StaminaItem:
    """Represents a stamina item available in the Black Market."""
    template_name: str
    stamina_amount: int
    bought_template_name: str | None = None  # Template for already-purchased version
    
    
# Available stamina items (prioritized by efficiency)
STAMINA_ITEMS = [
    StaminaItem("stamina_10", 500, "stamina_10_bought"),  # 10 packs × 50 = 500 stamina
    StaminaItem("stamina_1", 50, "stamina_1_bought"),    # 1 pack × 50 = 50 stamina
]


@dataclass(slots=True)
class PipelineOptions:
    dry_run: bool = False
    max_retries: int = 3
    purchase_delay_seconds: float = 1.0
    jitter_seconds: float = 0.2
    post_purchase_delay_seconds: float = 1.0  # Wait after successful purchase for UI to update
    post_click_delay_seconds: float = 1.0  # Wait after clicking item for confirm dialog to appear
    refresh_button_icon: str = "refresh"
    max_refreshes: int = 100  # Maximum times to refresh the Black Market (can take 50-100+ tries)
    template_dir: Path | None = None
    confirm_icon_name: str = "to_confirm"
    gem_button_vertical_ratio: float = 0.9
    template_threshold: float = 0.75  # Safe margin above 0.64 false positive; 0.02 scale steps ensure reliable matching
    descriptor_min_matches: int = 10  # Standard feature matching (15 was too strict!)
    # Templates are scale-sensitive; 0.02 step increments ensure we hit the exact scale needed
    # Range 0.4-2.0 covers emulator windows from ~200px to ~2000px width
    template_scales: tuple[float, ...] = tuple(round(0.4 + i * 0.02, 2) for i in range(81))  # 0.40 to 2.00 in 0.02 steps
    normalize_resolution: tuple[int, int] | None = None  # Let multi-scale handle resolution differences
    template_source_resolution: tuple[int, int] | None = None  # Not using dynamic scaling
    reference_width: int | None = None  # Normalize screenshots to this width (maintains aspect ratio, more robust)
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


class CancelledError(Exception):
    """Raised when the operation is cancelled by user."""
    pass


class PipelineRunner:
    """Runs the purchase pipeline sequentially for each emulator."""

    def __init__(
        self,
        options: PipelineOptions,
        console: Console | None = None,
        client_factory: Callable[[str], ScreenCaptureClient] | None = None,
        template_library: TemplateLibrary | None = None,
        progress_callback: Callable[[str, int], None] | None = None,  # (target_name, purchased_amount)
        cancel_callback: Callable[[], bool] | None = None,  # Returns True if cancelled
    ) -> None:
        self.options = options
        self.console = console or Console()
        self._client_factory = client_factory or (lambda window_title: ScreenCaptureClient(window_title=window_title))
        self._progress_callback = progress_callback
        self._cancel_callback = cancel_callback
        threshold = options.template_threshold
        self._templates = template_library or TemplateLibrary(
            options.template_dir,
            threshold=threshold,
            scales=options.template_scales,
            grayscale=True,
            descriptor_min_matches=options.descriptor_min_matches,
            console=self.console,  # Pass console for verbose logging
            normalize_resolution=options.normalize_resolution,
            template_source_resolution=options.template_source_resolution,
            reference_width=options.reference_width,
        )

    def _check_cancelled(self) -> None:
        """Check if operation was cancelled and raise if so."""
        if self._cancel_callback and self._cancel_callback():
            self.console.log("[yellow]Operation cancelled by user[/yellow]")
            raise CancelledError("Operation cancelled by user")

    def run(self, targets: Sequence[EmulatorTarget]) -> list[PipelineResult]:
        results: list[PipelineResult] = []
        for target in targets:
            self._check_cancelled()
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

        purchased = 0
        purchase_count = 0
        
        # Keep buying until we reach the target
        while purchased < target.stamina:
            self._check_cancelled()
            
            purchase_count += 1
            remaining = target.stamina - purchased
            
            self.console.log(
                f"Purchase #{purchase_count} for '{target.name}' "
                f"(have {purchased}/{target.stamina} stamina, need {remaining} more)"
            )
            
            # Try to find any available stamina item, refresh if needed
            pack_match, stamina_item = self._find_stamina_with_refresh(client)
            
            # Click the stamina item
            self._tap_gem_button(client, pack_match)
            
            # Wait for confirm dialog to appear
            delay = self.options.post_click_delay_seconds
            self.console.log(f"[dim]Waiting {delay}s for confirm dialog...[/dim]")
            time.sleep(delay)

            # Find and click confirm button - if not found, skip and try again
            try:
                confirm_match = self._match_with_retry(client, self.options.confirm_icon_name)
                self._tap_center(client, confirm_match)
            except RuntimeError:
                self.console.log(
                    "[yellow]⚠️ Confirm dialog not found - item may already be purchased. "
                    "Continuing...[/yellow]"
                )
                # Wait a moment then continue to find next item
                time.sleep(self.options.post_purchase_delay_seconds)
                continue

            # Update purchased amount
            purchased += stamina_item.stamina_amount
            self.console.log(
                f"✅ Purchased {stamina_item.stamina_amount} stamina. "
                f"Total: {purchased}/{target.stamina}"
            )
            
            # Notify progress callback
            if self._progress_callback:
                self._progress_callback(target.name, purchased)
            
            # Check if we're done
            if purchased >= target.stamina:
                break
            
            # Wait for purchase to complete and UI to update before next purchase
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

    def _find_stamina_with_refresh(self, client: ScreenCaptureClient) -> tuple[MatchResult, StaminaItem]:
        """
        Try to find any stamina item. If not found, refresh the Black Market and retry.
        
        Also checks for "bought" versions and skips them (they can't be purchased again).
        
        Returns:
            Tuple of (MatchResult, StaminaItem) for the found stamina
            
        Raises:
            RuntimeError: If stamina cannot be found after refreshing
        """
        for refresh_attempt in range(self.options.max_refreshes + 1):
            self._check_cancelled()
            
            # Try to find any stamina item (try in priority order)
            frame = client.screencap()
            
            for stamina_item in STAMINA_ITEMS:
                # Check for regular version
                regular_matches = self._templates.match(frame, [stamina_item.template_name])
                
                if regular_matches:
                    regular_match = regular_matches[0]
                    regular_score = regular_match.score
                    
                    # If this item has a "bought" version, check if it's been purchased
                    # by looking for the bought indicator in the SAME location
                    if stamina_item.bought_template_name:
                        bought_matches = self._templates.match(frame, [stamina_item.bought_template_name])
                        
                        if bought_matches:
                            bought_match = bought_matches[0]
                            bought_score = bought_match.score
                            
                            # Check if the bought version is at the same location (within tolerance)
                            same_location = (
                                abs(bought_match.top_left[0] - regular_match.top_left[0]) < 20 and
                                abs(bought_match.top_left[1] - regular_match.top_left[1]) < 20
                            )
                            
                            # If bought template matches above threshold at same location, it's bought
                            # The bought template specifically includes the "purchased" overlay,
                            # so a high match means that overlay is present
                            is_actually_bought = (
                                same_location and 
                                bought_score >= self.options.template_threshold
                            )
                            
                            if is_actually_bought:
                                self.console.log(
                                    f"[yellow]Skipping '{stamina_item.template_name}' at {regular_match.top_left} - "
                                    f"already purchased (bought score: {bought_score:.3f} >= {self.options.template_threshold})[/yellow]"
                                )
                                continue  # Try next stamina item type
                            else:
                                self.console.log(
                                    f"[dim]Bought check: bought={bought_score:.3f} < threshold={self.options.template_threshold:.3f} → not bought[/dim]"
                                )
                    
                    # This is a valid, unpurchased item
                    self.console.log(
                        f"Found '{stamina_item.template_name}' ({stamina_item.stamina_amount} stamina) "
                        f"with score {regular_score:.3f} at {regular_match.top_left}->{regular_match.bottom_right}."
                    )
                    return regular_match, stamina_item
            
            # No stamina found
            if refresh_attempt < self.options.max_refreshes:
                # Try to refresh
                self.console.log(
                    f"No stamina items found. Refreshing Black Market... (refresh #{refresh_attempt + 1})"
                )
                
                try:
                    refresh_match = self._match_with_retry(client, self.options.refresh_button_icon)
                    self._tap_center(client, refresh_match)
                    
                    # Wait for refresh to complete
                    refresh_delay = 1.0
                    self.console.log(f"[dim]Waiting {refresh_delay}s for refresh...[/dim]")
                    time.sleep(refresh_delay)
                except RuntimeError:
                    self.console.log("[yellow]Refresh button not found, continuing...[/yellow]")
            else:
                # Out of refresh attempts
                if self.options.save_debug_screenshots:
                    self._save_debug_screenshot(frame, "stamina")
                raise RuntimeError(
                    f"Failed to locate any stamina items after {self.options.max_refreshes} refresh attempts."
                )
        
        raise RuntimeError("Failed to locate any stamina items")
    
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
