#!/usr/bin/env python3
"""
Launcher script for Stamina Buyer.

When run without arguments, launches the GUI.
With arguments, runs the CLI.

This provides the best user experience:
- Double-click the exe → Opens GUI
- Run from terminal with args → CLI mode
"""

import sys
import os

# Ensure the src directory is in the path
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    bundle_dir = sys._MEIPASS
else:
    # Running as script
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(bundle_dir, 'src')
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

if __name__ == "__main__":
    # If no arguments (or just the script name), launch GUI
    if len(sys.argv) == 1:
        try:
            from staminabuyer.gui import launch_gui
            launch_gui()
        except Exception as e:
            print(f"Error launching GUI: {e}")
            print("Falling back to CLI mode. Use --help for usage.")
            from staminabuyer.cli import app
            app()
    else:
        # Has arguments, run CLI
        from staminabuyer.cli import app
        app()

