"""CLI entrypoint for the Stamina Buyer emulator pipeline."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from . import get_version
from .config import ResolvedConfiguration, resolve_configuration
from .pipeline import PipelineOptions, PipelineRunner

app = typer.Typer(
    help=(
        "Automate Evony Black Market stamina purchases.\n\n"
        "Running without a subcommand opens the GUI (recommended). "
        "Use `run`, `list-windows`, or `gui` for explicit control."
    ),
    # Make every subcommand optional so bare `staminabuyer` can launch the GUI
    # (the typical double-click / `staminabuyer.exe` experience).
    invoke_without_command=True,
)
console = Console()


def _build_runner(
    config: ResolvedConfiguration,
    dry_run: bool,
    max_retries: int,
    reference_width: int | None = None,
    items_file: Path | None = None,
) -> PipelineRunner:
    # Convert 0 to None (disabled)
    ref_width = reference_width if reference_width and reference_width > 0 else None

    options = PipelineOptions(
        dry_run=dry_run,
        max_retries=max_retries,
        reference_width=ref_width,
        items_file=items_file,
        **config.pipeline_overrides(),
    )

    if options.auto_settle:
        console.print(
            f"[cyan]Refresh wait: at least {options.refresh_wait_seconds:.1f}s, then until the "
            f"screen settles (max {options.settle_timeout_seconds:.1f}s)[/cyan]"
        )
    else:
        console.print(f"[cyan]Refresh wait: fixed {options.refresh_wait_seconds:.1f}s[/cyan]")

    if ref_width:
        console.print(f"[cyan]Using reference width: {ref_width}px (screenshots will be normalized)[/cyan]")
    if items_file:
        console.print(f"[cyan]Using item catalog: {items_file}[/cyan]")

    return PipelineRunner(options=options, console=console)


@app.callback()
def main_callback(ctx: typer.Context) -> None:
    """Display a version banner, and launch the GUI when no subcommand is given.

    Running ``staminabuyer`` with no arguments (or double-clicking the bundled
    executable) falls through to the GUI — that's the intended default UX.
    Pass an explicit subcommand (``run``, ``list-windows``, ``gui``) to use
    the CLI instead.
    """
    console.print(Panel.fit(f"Stamina Buyer v{get_version()}"))
    if ctx.invoked_subcommand is None:
        _launch_gui_or_exit()


def _launch_gui_or_exit() -> None:
    """Launch the GUI, or print an actionable error and exit."""
    try:
        from .gui import launch_gui
    except ImportError as exc:
        console.print(str(exc), style="red", markup=False)
        console.print("Reinstall with: pip install -e .  — or use the CLI: staminabuyer run --help")
        raise typer.Exit(code=1) from exc
    launch_gui()


@app.command()
def gui() -> None:
    """Launch the graphical user interface (default when no subcommand is given)."""
    _launch_gui_or_exit()


@app.command()
def list_windows() -> None:
    """List all visible emulator windows to help identify window titles."""
    try:
        from .emulator.screen_capture import (
            find_emulator_windows,
        )
        from .emulator.screen_capture import (
            list_windows as list_all_windows,
        )

        console.print("\n[bold cyan]Searching for emulator windows...[/bold cyan]\n")

        emulator_windows = find_emulator_windows()

        if emulator_windows:
            console.print("[bold green]Found emulator windows:[/bold green]")
            for window in emulator_windows:
                console.print(f"  • [yellow]{window}[/yellow]")

            console.print("\n[dim]Use these window titles with --target, e.g.:[/dim]")
            console.print(f"[dim]  staminabuyer run --target \"{emulator_windows[0]}:100\"[/dim]")
        else:
            console.print("[yellow]No emulator windows found automatically.[/yellow]")
            console.print("\n[bold]All visible windows:[/bold]")
            all_windows = list_all_windows()
            for window in all_windows[:20]:  # Show first 20
                console.print(f"  • {window}")

            if len(all_windows) > 20:
                console.print(f"\n[dim]...and {len(all_windows) - 20} more[/dim]")

            console.print("\n[dim]Look for your emulator window title above.[/dim]")

    except ImportError as exc:
        console.print("[red]Screen capture dependencies not installed.[/red]")
        console.print("Reinstall the package with: pip install -e .")
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def run(
    target: list[str] = typer.Option(
        [],
        "--target",
        "-t",
        help="Repeatable <window_title>:<stamina_to_buy> (e.g. 'BlueStacks:100')",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        file_okay=True,
        dir_okay=False,
        exists=False,
        help="Optional YAML/JSON config file containing targets and defaults.",
    ),
    dry_run: bool = typer.Option(
        False, help="Test detection without clicking (recommended first run)."
    ),
    max_retries: int = typer.Option(3, min=1, help="Maximum retries when detection fails."),
    reference_width: int | None = typer.Option(
        0,
        "--reference-width",
        "-w",
        help=(
            "Legacy: rescale captured frames to this logical width before matching. "
            "Anchor-based scale calibration (on by default) makes this unnecessary in "
            "most setups. Use 0 to disable, or a positive integer to force rescaling."
        ),
    ),
    items_file: Path | None = typer.Option(
        None,
        "--items-file",
        file_okay=True,
        dir_okay=False,
        exists=True,
        help="Custom stamina item catalog (YAML). Defaults to the bundled assets/items.yaml.",
    ),
    refresh_wait: float | None = typer.Option(
        None,
        "--refresh-wait",
        min=0.0,
        help=(
            "Seconds to wait after tapping refresh (default 1.0). With auto-settle this is "
            "the minimum wait; with --fixed-wait it is the exact wait."
        ),
    ),
    auto_settle: bool | None = typer.Option(
        None,
        "--auto-settle/--fixed-wait",
        help=(
            "After --refresh-wait, keep waiting until the screen stops changing "
            "(default), or treat --refresh-wait as a fixed delay."
        ),
    ),
    settle_timeout: float | None = typer.Option(
        None,
        "--settle-timeout",
        min=0.1,
        help="Maximum seconds to wait for the screen to settle (default 8.0).",
    ),
) -> None:
    """Buy stamina from Black Market by detecting the window and clicking automatically.
    
    First, find your emulator window title:
        staminabuyer list-windows
    
    Then run the tool:
        staminabuyer run --target "BlueStacks:100"
    
    The window must be visible (not minimized) during operation.
    """

    try:
        resolved = resolve_configuration(
            target,
            config,
            cli_overrides={
                "refresh_wait_seconds": refresh_wait,
                "auto_settle": auto_settle,
                "settle_timeout_seconds": settle_timeout,
            },
        )
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Config file not found: {exc}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    runner = _build_runner(
        resolved,
        dry_run=dry_run,
        max_retries=max_retries,
        reference_width=reference_width,
        items_file=items_file,
    )
    results = runner.run(resolved.targets)

    failures = [r for r in results if not r.successful]
    if failures:
        raise typer.Exit(code=1)

    typer.echo("Completed stamina purchases for all targets.")
