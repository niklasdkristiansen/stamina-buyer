"""High-level orchestration for stamina purchase runs."""

from __future__ import annotations

import enum
import random
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from .config import EmulatorTarget
from .emulator.screen_capture import ScreenCaptureClient
from .vision.matcher import MatchResult, TemplateLibrary


class PurchaseState(enum.Enum):
    """States the purchase loop can be in.

    Transitions (on success):
        FOCUS_WINDOW → FIND_ITEM → TAP_ITEM → WAIT_FOR_CONFIRM
                   → CONFIRM → RECORD_PURCHASE → FIND_ITEM (next round)
                                             → DONE (target reached)

    CONFIRM can also transition back to FIND_ITEM (no dialog, item was
    already bought). FIND_ITEM can transition directly to DONE when the
    target is already satisfied before the first purchase. Any state can
    raise ``CancelledError``, ending the loop.
    """

    FOCUS_WINDOW = "focus_window"
    FIND_ITEM = "find_item"
    TAP_ITEM = "tap_item"
    WAIT_FOR_CONFIRM = "wait_for_confirm"
    CONFIRM = "confirm"
    RECORD_PURCHASE = "record_purchase"
    DONE = "done"


@dataclass
class PurchaseContext:
    """Mutable state threaded through the purchase state machine."""

    target: EmulatorTarget
    purchased: int = 0
    purchase_count: int = 0
    pending_item: "StaminaItem | None" = None
    pending_match: MatchResult | None = None

    @property
    def remaining(self) -> int:
        return max(0, self.target.stamina - self.purchased)

    @property
    def is_satisfied(self) -> bool:
        return self.purchased >= self.target.stamina


@dataclass(slots=True)
class StaminaItem:
    """A stamina item available in the Black Market.

    ``template_name`` must reference a PNG in the assets/icons folder (without
    extension). ``stamina_amount`` is how much stamina is credited toward the
    target when this item is successfully purchased.

    Bought/greyed-out items are skipped via ROI saturation — no per-state
    template required.
    """

    template_name: str
    stamina_amount: int


#: Default catalog, prioritized by efficiency. Callers can override by
#: providing a YAML file via :func:`load_stamina_items` or the CLI's
#: ``--items-file`` option. The runtime catalog lives on
#: :attr:`PipelineRunner._items`, not at module scope, so per-run overrides
#: never leak across runners.
DEFAULT_STAMINA_ITEMS: tuple[StaminaItem, ...] = (
    StaminaItem("stamina_10", 500),  # 10 packs × 50 = 500 stamina
    StaminaItem("stamina_1", 50),    # 1 pack × 50 = 50 stamina
)


def _default_items_file() -> Path:
    """Return the path to the bundled items.yaml, whether running from source or PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "items.yaml"
    # pipeline.py lives at src/staminabuyer/pipeline.py
    return Path(__file__).resolve().parent.parent.parent / "assets" / "items.yaml"


def load_stamina_items(path: Path | None = None) -> list[StaminaItem]:
    """Load the stamina item catalog from YAML.

    Falls back to :data:`DEFAULT_STAMINA_ITEMS` if the file does not exist,
    so the pipeline still works when the bundled YAML is stripped from a
    minimal build.

    The expected schema is::

        items:
          - template: stamina_10
            amount: 500
          - template: stamina_1
            amount: 50
    """
    resolved = path or _default_items_file()
    if not resolved.exists():
        return list(DEFAULT_STAMINA_ITEMS)

    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"{resolved} must contain a non-empty 'items:' list.")

    catalog: list[StaminaItem] = []
    for idx, entry in enumerate(raw_items):
        if not isinstance(entry, dict):
            raise ValueError(f"{resolved}: items[{idx}] must be a mapping, got {type(entry).__name__}")
        try:
            template_name = entry["template"]
            amount = int(entry["amount"])
        except KeyError as exc:
            raise ValueError(f"{resolved}: items[{idx}] missing required field {exc}") from exc
        if amount <= 0:
            raise ValueError(f"{resolved}: items[{idx}] 'amount' must be positive, got {amount}")
        catalog.append(StaminaItem(template_name=str(template_name), stamina_amount=amount))
    return catalog


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
    template_threshold: float = 0.70  # Lowered to catch refresh button variants (free vs paid)
    descriptor_min_matches: int = 10  # Standard feature matching (15 was too strict!)
    # Mean HSV saturation below this is treated as "already purchased" (the
    # Evony UI desaturates bought cards). Regular cards measure ~145, bought
    # ones ~35, so 80 leaves plenty of margin either way.
    bought_saturation_threshold: float = 80.0
    # Scale sweep used by anchor calibration. Wide by design — the anchor
    # (refresh button) can appear anywhere from a small to a large window,
    # and we need the sweep to find it. After calibration, the frame is
    # resized so the UI matches template scale, and item matches use a
    # tight band around 1.0 (see ``item_scale_tolerance``).
    #
    # The sweep covers 0.40x–2.20x. Beyond those bounds in either direction,
    # template matching becomes noise-dominated: tiny templates cross-match
    # arbitrary UI regions (false-positive anchors), and huge ones lose
    # detail through upsampling (no match at all). If the diagnostic log
    # reveals your window lands outside this band, the right fix is to
    # regenerate templates at your preferred size, not to widen the sweep.
    template_scales: tuple[float, ...] = tuple(
        round(0.40 + i * 0.05, 2) for i in range(37)  # 0.40 → 2.20 at 0.05 steps
    )
    reference_width: int | None = None  # Legacy aspect-preserving rescale; superseded by frame normalization.
    save_debug_screenshots: bool = False
    items_file: Path | None = None  # Optional path to items.yaml; None = bundled default.
    # Anchor-based scale calibration is the core of the resolution-agnostic
    # matching pipeline: each frame is checked for an anchor icon, the
    # frame is resized so the UI appears at canonical (template) scale, and
    # then templates match at scale ≈ 1.0 with a small tolerance for
    # calibration quantization.
    anchor_icons: tuple[str, ...] = ("refresh",)
    anchor_min_score: float = 0.6
    # Tolerance around 1.0 for matching items *after* the frame has been
    # normalized to canonical scale. Calibration snaps to the nearest
    # configured scale step (0.05 above), so 0.08 gives plenty of headroom
    # for residual error while still being tight enough to prevent the
    # cross-card false positives that bit v2.3.0.
    item_scale_tolerance: float = 0.08
    # How long to wait before retrying when the anchor can't be found.
    # Distinct from the button-match retry delay because "no anchor" usually
    # means the emulator is mid-animation or on a different screen entirely.
    wrong_screen_wait_seconds: float = 1.0


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
        items: Sequence[StaminaItem] | None = None,
    ) -> None:
        self.options = options
        self.console = console or Console()
        self._client_factory = client_factory or (lambda window_title: ScreenCaptureClient(window_title=window_title))
        self._progress_callback = progress_callback
        self._cancel_callback = cancel_callback
        # Items: explicit > options.items_file > bundled default.
        if items is not None:
            self._items: list[StaminaItem] = list(items)
        else:
            self._items = load_stamina_items(options.items_file)
        # Most-recently-calibrated UI scale, reused across item/button matches
        # within a single purchase attempt. ``None`` means not yet calibrated.
        self._calibrated_scale: float | None = None
        threshold = options.template_threshold
        self._templates = template_library or TemplateLibrary(
            options.template_dir,
            threshold=threshold,
            scales=options.template_scales,
            grayscale=True,
            descriptor_min_matches=options.descriptor_min_matches,
            console=self.console,
            reference_width=options.reference_width,
        )

    def _calibrate_from_frame(self, frame: bytes) -> float | None:
        """Detect the UI's current scale from ``frame`` using the configured anchor.

        Updates ``self._calibrated_scale`` in place (only when a confident
        anchor is found) and returns the new value. Returns ``None`` and
        leaves the previous scale intact when the anchor can't be located —
        meaning "probably not on the expected screen".

        On failure, logs the best-effort probe so users can tell whether the
        anchor was almost-matched (lower ``anchor_min_score``) vs. not
        present at all (wrong screen, window outside sweep range).
        """
        anchor_match = self._templates.calibrate_scale(
            frame,
            anchor_icons=self.options.anchor_icons,
            min_score=self.options.anchor_min_score,
        )
        if anchor_match is None:
            self._log_calibration_miss(frame)
            return None
        if self._calibrated_scale is None or abs(anchor_match.scale - self._calibrated_scale) > 0.01:
            self.console.log(
                f"[dim]Scale calibrated from anchor '{anchor_match.icon}': "
                f"scale={anchor_match.scale:.2f} score={anchor_match.score:.3f}[/dim]"
            )
        self._calibrated_scale = anchor_match.scale
        return anchor_match.scale

    def _log_calibration_miss(self, frame: bytes) -> None:
        """Re-run the anchor probe at zero threshold to surface diagnostics.

        Cheap (reuses the same scale sweep) and only runs on the miss path,
        so no impact on happy-path performance. Also saves a debug snapshot
        when ``save_debug_screenshots`` is enabled, since the failing frame
        is exactly what you need to diagnose a miscalibration offline.
        """
        probe = self._templates.match(
            frame, list(self.options.anchor_icons), threshold=0.0
        )
        if probe:
            best = probe[0]
            self.console.log(
                f"[yellow]Anchor miss: best candidate was '{best.icon}' @ "
                f"scale {best.scale:.2f}x score {best.score:.3f} (need "
                f"{self.options.anchor_min_score:.2f}). If score is close, "
                f"try lowering anchor_min_score; if far below, the UI is "
                f"probably not on the Black Market or outside the "
                f"{min(self.options.template_scales):.2f}x–"
                f"{max(self.options.template_scales):.2f}x sweep.[/yellow]"
            )
        else:
            self.console.log(
                "[yellow]Anchor miss: no candidate at any scale. Window "
                "may be far outside the supported size range.[/yellow]"
            )

        if self.options.save_debug_screenshots:
            self._save_debug_screenshot(frame, "calibration_miss")

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

    def _execute_purchase_loop(
        self, client: ScreenCaptureClient, target: EmulatorTarget
    ) -> int:
        """Drive the purchase state machine until the target is satisfied or cancelled."""
        ctx = PurchaseContext(target=target)
        state = PurchaseState.FOCUS_WINDOW

        handlers: dict[PurchaseState, Callable[[ScreenCaptureClient, PurchaseContext], PurchaseState]] = {
            PurchaseState.FOCUS_WINDOW: self._state_focus_window,
            PurchaseState.FIND_ITEM: self._state_find_item,
            PurchaseState.TAP_ITEM: self._state_tap_item,
            PurchaseState.WAIT_FOR_CONFIRM: self._state_wait_for_confirm,
            PurchaseState.CONFIRM: self._state_confirm,
            PurchaseState.RECORD_PURCHASE: self._state_record_purchase,
        }

        while state is not PurchaseState.DONE:
            self._check_cancelled()
            try:
                handler = handlers[state]
            except KeyError as exc:
                raise RuntimeError(f"No handler registered for state {state}") from exc
            state = handler(client, ctx)

        return ctx.purchased

    # --- State handlers --------------------------------------------------
    # Each returns the next PurchaseState. They may raise CancelledError
    # or RuntimeError; the loop above handles the former and propagates
    # the latter out to the caller.

    def _state_focus_window(
        self, client: ScreenCaptureClient, ctx: PurchaseContext
    ) -> PurchaseState:
        self.console.log("Bringing window to foreground...")
        client.focus_window()
        return PurchaseState.FIND_ITEM

    def _state_find_item(
        self, client: ScreenCaptureClient, ctx: PurchaseContext
    ) -> PurchaseState:
        if ctx.is_satisfied:
            return PurchaseState.DONE

        ctx.purchase_count += 1
        self.console.log(
            f"Purchase #{ctx.purchase_count} for '{ctx.target.name}' "
            f"(have {ctx.purchased}/{ctx.target.stamina} stamina, need {ctx.remaining} more)"
        )

        pack_match, stamina_item = self._find_stamina_with_refresh(client)
        ctx.pending_match = pack_match
        ctx.pending_item = stamina_item
        return PurchaseState.TAP_ITEM

    def _state_tap_item(
        self, client: ScreenCaptureClient, ctx: PurchaseContext
    ) -> PurchaseState:
        assert ctx.pending_match is not None, "TAP_ITEM requires a pending match"
        self._tap_gem_button(client, ctx.pending_match)
        return PurchaseState.WAIT_FOR_CONFIRM

    def _state_wait_for_confirm(
        self, client: ScreenCaptureClient, ctx: PurchaseContext
    ) -> PurchaseState:
        delay = self.options.post_click_delay_seconds
        self.console.log(f"[dim]Waiting {delay}s for confirm dialog...[/dim]")
        time.sleep(delay)
        return PurchaseState.CONFIRM

    def _state_confirm(
        self, client: ScreenCaptureClient, ctx: PurchaseContext
    ) -> PurchaseState:
        try:
            confirm_match = self._match_with_retry(client, self.options.confirm_icon_name)
        except RuntimeError:
            # No dialog appeared — the item was already owned, or the tap missed.
            # Fall back to the next find/refresh cycle after a short settle.
            self.console.log(
                "[yellow]⚠️ Confirm dialog not found — item may already be purchased. "
                "Continuing...[/yellow]"
            )
            time.sleep(self.options.post_purchase_delay_seconds)
            ctx.pending_match = None
            ctx.pending_item = None
            return PurchaseState.FIND_ITEM

        self._tap_center(client, confirm_match)
        return PurchaseState.RECORD_PURCHASE

    def _state_record_purchase(
        self, client: ScreenCaptureClient, ctx: PurchaseContext
    ) -> PurchaseState:
        assert ctx.pending_item is not None, "RECORD_PURCHASE requires a pending item"

        ctx.purchased += ctx.pending_item.stamina_amount
        self.console.log(
            f"✅ Purchased {ctx.pending_item.stamina_amount} stamina. "
            f"Total: {ctx.purchased}/{ctx.target.stamina}"
        )

        if self._progress_callback:
            self._progress_callback(ctx.target.name, ctx.purchased)

        ctx.pending_match = None
        ctx.pending_item = None

        if ctx.is_satisfied:
            return PurchaseState.DONE

        delay = self.options.post_purchase_delay_seconds
        self.console.log(f"[dim]Waiting {delay}s for purchase to complete...[/dim]")
        time.sleep(delay)
        return PurchaseState.FIND_ITEM

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

    def _find_stamina_with_refresh(
        self, client: ScreenCaptureClient
    ) -> tuple[MatchResult, StaminaItem]:
        """Find the best available (un-purchased) stamina item, refreshing if needed.

        Every frame is anchor-calibrated; the detected UI scale is used to
        normalize the frame so templates match at canonical (1.0) scale with
        a small tolerance for calibration quantization. This makes the
        pipeline genuinely resolution-agnostic: any window size within the
        anchor sweep (0.5×–2.0× of template scale) works equivalently.

        When calibration fails we back off and wait rather than refresh —
        tapping the refresh button on a screen that isn't the Black Market
        would land on whatever happens to be there.

        Raises:
            RuntimeError: No available stamina item after exhausting refreshes.
        """
        # Separate budgets for "couldn't see the UI at all" vs. "saw the UI
        # but no items were available". Counting calibration misses against
        # the refresh budget silently burns through attempts without ever
        # tapping refresh, and masks the real cause of failure.
        max_calibration_misses = max(1, self.options.max_refreshes)
        calibration_misses = 0
        refresh_attempt = 0

        while True:
            self._check_cancelled()

            frame = client.screencap()
            calibrated_scale = self._calibrate_from_frame(frame)

            if calibrated_scale is None:
                calibration_misses += 1
                if calibration_misses > max_calibration_misses:
                    if self.options.save_debug_screenshots:
                        self._save_debug_screenshot(frame, "calibration_miss_final")
                    raise RuntimeError(
                        f"UI scale could not be detected after "
                        f"{calibration_misses} attempts — anchor '"
                        f"{', '.join(self.options.anchor_icons)}' was never "
                        f"found. Check that the Black Market screen is "
                        f"visible and the window is between "
                        f"{min(self.options.template_scales):.2f}x and "
                        f"{max(self.options.template_scales):.2f}x of "
                        f"template scale. Enable save_debug_screenshots "
                        f"to capture the failing frame."
                    )
                self.console.log(
                    f"[yellow]⚠️ UI scale not detected "
                    f"({calibration_misses}/{max_calibration_misses}). "
                    f"Waiting before retrying...[/yellow]"
                )
                time.sleep(self.options.wrong_screen_wait_seconds)
                continue

            # We're on the right screen; reset the miss counter.
            calibration_misses = 0

            scores = self._score_items(frame, frame_scale=calibrated_scale)

            selection = self._select_available_item(frame, scores)
            if selection is not None:
                return selection

            if refresh_attempt >= self.options.max_refreshes:
                if self.options.save_debug_screenshots:
                    self._save_debug_screenshot(frame, "stamina")
                raise RuntimeError(
                    f"Failed to locate any stamina items after "
                    f"{self.options.max_refreshes} refresh attempts."
                )

            refresh_attempt += 1
            self.console.log(
                f"No stamina items found. Refreshing Black Market... "
                f"(refresh #{refresh_attempt})"
            )
            self._refresh_market(client)

    def _score_items(
        self, frame: bytes, frame_scale: float
    ) -> dict[str, tuple[float, MatchResult | None]]:
        """Return ``{template_name: (best_score, best_match)}`` for every item.

        Uses a low acceptance threshold so callers can see and log scores for
        items that narrowly missed, rather than silently getting empty lists.
        The frame is normalized to template (canonical) scale via
        ``frame_scale``, and matching is restricted to a tight band around
        1.0 — so each item does 1-3 correlations instead of the full sweep,
        and cross-card false positives from extreme-scale variants cannot
        occur by construction.
        """
        scores: dict[str, tuple[float, MatchResult | None]] = {}
        for item in self._items:
            matches = self._templates.match(
                frame,
                [item.template_name],
                threshold=0.3,
                frame_scale=frame_scale,
                scale_hint=1.0,
                scale_tolerance=self.options.item_scale_tolerance,
            )
            best = matches[0] if matches else None
            scores[item.template_name] = (best.score if best else 0.0, best)

        self.console.log(
            "[dim]Template scores: "
            + ", ".join(f"{k}={v[0]:.3f}" for k, v in scores.items())
            + "[/dim]"
        )
        return scores

    def _select_available_item(
        self,
        frame: bytes,
        scores: dict[str, tuple[float, MatchResult | None]],
    ) -> tuple[MatchResult, StaminaItem] | None:
        """Pick the highest-scoring item that clears the threshold AND is not greyed out.

        Returns ``None`` when every item is either below threshold or
        desaturated (i.e., already purchased).
        """
        sorted_items = sorted(
            self._items,
            key=lambda it: scores[it.template_name][0],
            reverse=True,
        )

        for item in sorted_items:
            score, match = scores[item.template_name]
            if match is None or score < self.options.template_threshold:
                continue

            saturation = self._templates.mean_saturation(frame, match)
            if saturation < self.options.bought_saturation_threshold:
                self.console.log(
                    f"[yellow]Skipping '{item.template_name}' — already purchased "
                    f"(saturation {saturation:.1f} < {self.options.bought_saturation_threshold:.1f})[/yellow]"
                )
                continue

            self.console.log(
                f"Found '{item.template_name}' ({item.stamina_amount} stamina) "
                f"score={score:.3f} saturation={saturation:.1f}"
            )
            return match, item

        return None

    def _refresh_market(self, client: ScreenCaptureClient) -> None:
        """Tap the refresh button if we can find it, otherwise log and move on.

        Never raises — a missing refresh button shouldn't halt the whole run;
        the outer loop will just try another frame.
        """
        try:
            refresh_match = self._match_with_retry(client, self.options.refresh_button_icon)
        except RuntimeError:
            self.console.log("[yellow]Refresh button not found, continuing...[/yellow]")
            return

        self._tap_center(client, refresh_match)
        refresh_delay = 1.0
        self.console.log(f"[dim]Waiting {refresh_delay}s for refresh...[/dim]")
        time.sleep(refresh_delay)

    def _match_with_retry(self, client: ScreenCaptureClient, icon_name: str) -> MatchResult:
        """Locate ``icon_name`` on the current screen, retrying on failure.

        Each attempt re-captures the frame, re-calibrates the UI scale, and
        runs a tight scale match in the normalized frame. A failed
        calibration is treated as a soft failure (wait and retry); an
        exhausted retry budget raises.
        """
        if not self._templates.has_template(icon_name):
            raise RuntimeError(f"Template '{icon_name}' is not available in assets/icons.")

        for attempt in range(1, self.options.max_retries + 1):
            frame = client.screencap()

            calibrated_scale = self._calibrate_from_frame(frame)
            if calibrated_scale is None:
                self.console.log(
                    f"[yellow]Attempt {attempt}/{self.options.max_retries}: "
                    f"UI scale not detected while looking for '{icon_name}'. "
                    f"Retrying after delay.[/yellow]"
                )
                self._sleep_with_jitter()
                continue

            matches = self._templates.match(
                frame,
                [icon_name],
                frame_scale=calibrated_scale,
                scale_hint=1.0,
                scale_tolerance=self.options.item_scale_tolerance,
            )
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
            from datetime import datetime

            import cv2
            import numpy as np

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
