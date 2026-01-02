"""
Pytest configuration for headless test environments.

Sets up mock environment variables needed by GUI libraries like pyautogui
that require DISPLAY on Linux.
"""

import os
import sys

# Set a dummy DISPLAY if not present (for headless CI/testing)
if sys.platform.startswith('linux') and 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'

