#!/usr/bin/env python3
"""
Build script to create standalone executables using PyInstaller.

Usage:
    python build_executable.py

Builds from ``staminabuyer.spec`` (the same spec CI uses), producing a single
executable in ``dist/`` that bundles the Python runtime, all dependencies,
the template icons, and the item catalog.
"""

import subprocess
import sys
from pathlib import Path


def build_executable():
    """Build the standalone executable using PyInstaller."""

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found. Install build deps with: pip install -e .[build]")
        sys.exit(1)

    project_root = Path(__file__).parent
    cmd = [sys.executable, "-m", "PyInstaller", "staminabuyer.spec", "--noconfirm"]

    print("Building standalone executable...")
    print(f"Command: {' '.join(cmd)}")
    print()

    try:
        subprocess.check_call(cmd, cwd=project_root)
        print("\n" + "="*80)
        print("✓ Build successful!")
        print("="*80)
        print(f"\nExecutable location: {project_root / 'dist' / 'staminabuyer'}")
        print("\nYou can now distribute this file to users who don't have Python installed.")
        print("\nUsage:")
        print("  • Double-click → Opens GUI (recommended for most users)")
        print("  • From terminal:")
        print("      staminabuyer gui                    # Open GUI")
        print("      staminabuyer run --target 'Win:100' # CLI mode")

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_executable()
