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
    template_dir: Path | None = None
    stamina_pack_icon: str = "stamina_10"
    confirm_icon_name: str = "to_confirm"
    pack_size: int = 10
    gem_button_vertical_ratio: float = 0.9
    template_threshold: float = 0.7
    descriptor_min_matches: int = 10
    template_scales: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0)


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
        """Buy stamina packs by matching templates and tapping confirm dialogs."""

        pack_size = self.options.pack_size
        if pack_size <= 0:
            raise ValueError("PipelineOptions.pack_size must be greater than zero.")

        packs_needed = ceil(target.stamina / pack_size)
        purchased = 0

        for attempt in range(1, packs_needed + 1):
            self.console.log(
                f"Buying pack {attempt}/{packs_needed} for '{target.name}' (size={pack_size})."
            )
            pack_match = self._match_with_retry(client, self.options.stamina_pack_icon)
            self._tap_gem_button(client, pack_match)

            confirm_match = self._match_with_retry(client, self.options.confirm_icon_name)
            self._tap_center(client, confirm_match)

            purchased += pack_size
            self._sleep_with_jitter()

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
