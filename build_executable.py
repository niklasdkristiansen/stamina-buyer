#!/usr/bin/env python3
"""
Build script to create standalone executables using PyInstaller.

Usage:
    python build_executable.py

This will create a standalone executable in the 'dist' folder that includes:
- Python runtime
- All dependencies (OpenCV, NumPy, etc.)
- Template icons
- Everything needed to run without installing Python
"""

import subprocess
import sys
from pathlib import Path

def build_executable():
    """Build the standalone executable using PyInstaller."""
    
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    project_root = Path(__file__).parent
    
    # PyInstaller command
    # Using --onefile creates a single executable (slower startup but easier distribution)
    # Using --onedir creates a folder with executable + libraries (faster startup)
    
    cmd = [
        "pyinstaller",
        "--name=staminabuyer",
        "--onefile",  # Single executable file
        "--console",  # Keep console window (for logging)
        "--add-data=assets/icons:assets/icons",  # Include template icons
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=typer",
        "--hidden-import=rich",
        "--hidden-import=pydantic",
        "--hidden-import=yaml",
        "--collect-all=cv2",  # Collect all OpenCV files
        "--collect-all=numpy",
        "--noconfirm",  # Overwrite without asking
        "src/staminabuyer/cli.py",  # Entry point
    ]
    
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

