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
    help="Automate Evony Black Market stamina purchases across emulators (no ADB required)."
)
console = Console()


def _build_runner(
    config: ResolvedConfiguration,
    dry_run: bool,
    max_retries: int,
    reference_width: int | None = None,
) -> PipelineRunner:
    # Convert 0 to None (disabled)
    ref_width = reference_width if reference_width and reference_width > 0 else None
    
    options = PipelineOptions(
        dry_run=dry_run,
        max_retries=max_retries,
        purchase_delay_seconds=config.purchase_delay_seconds,
        jitter_seconds=config.jitter_seconds,
        reference_width=ref_width,
    )
    
    if ref_width:
        console.print(f"[cyan]Using reference width: {ref_width}px (screenshots will be normalized)[/cyan]")
    
    return PipelineRunner(options=options, console=console)


@app.callback()
def main_callback() -> None:
    """Display version banner when invoking CLI."""

    console.print(Panel.fit(f"Stamina Buyer v{get_version()}"))


@app.command()
def gui() -> None:
    """Launch the graphical user interface (recommended for most users)."""
    try:
        from .gui import launch_gui

        launch_gui()
    except ImportError as exc:
        console.print("[red]GUI dependencies not installed.[/red]")
        console.print("Install with: pip install customtkinter")
        raise typer.Exit(code=1) from exc


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
        console.print("Install with: pip install -e .[screencapture]")
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
        480,
        "--reference-width",
        "-w",
        help="Normalize screenshots to this width for reliable matching (default: 480, use 0 to disable).",
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
        resolved = resolve_configuration(target, config)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    runner = _build_runner(resolved, dry_run=dry_run, max_retries=max_retries, reference_width=reference_width)
    results = runner.run(resolved.targets)

    failures = [r for r in results if not r.successful]
    if failures:
        raise typer.Exit(code=1)

    typer.echo("Completed stamina purchases for all targets.")
