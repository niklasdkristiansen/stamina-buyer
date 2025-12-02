# Stamina Buyer

Pipeline that automates stamina purchases from the Black Market inside Evony: The King's Return
emulators. The tool captures emulator windows directly, analyzes them using OpenCV template 
matching, and simulates clicks to buy stamina. **No ADB installation required!**

## Features
- ✨ **Zero setup** - No ADB installation or configuration required
- 🎨 **Modern GUI** - Beautiful interface, no command-line knowledge needed (just double-click!)
- 🎯 **Simple** - Just provide the emulator window title
- 🖥️ **Universal** - Works with BlueStacks, LDPlayer, NoxPlayer, MEmu, and any Android emulator
- 🔍 **Smart detection** - Uses computer vision (OpenCV) to find stamina cards automatically
- 🎯 **Resolution independent** - Works across different emulator resolutions (0.5x-2.0x scaling)
- 🚀 **Multi-instance** - Buy stamina on multiple emulators in one run
- 🧪 **Dry-run mode** - Test detection before making actual purchases
- 📊 **Live logging** - See exactly what the tool is doing in real-time
- 💻 **CLI available** - Advanced users can use command-line for automation/scripting

## Project Layout
```
staminabuyer/
  cli.py                    # Typer entrypoint
  config.py                 # Input parsing & validation
  emulator/screen_capture.py # Window capture and mouse automation
  pipeline.py               # Orchestration logic
  vision/matcher.py         # Template matching with OpenCV
assets/icons/               # Template icons for detection
tests/                      # Pytest suite
```

## Installation

### Option 1: Pre-built Executable (Easiest) ⭐

Download for your platform from [Releases](https://github.com/yourusername/stamina-buyer/releases):
- **Windows:** `staminabuyer.exe`
- **macOS/Linux:** `staminabuyer` (make executable: `chmod +x staminabuyer`)

**Just double-click to open the GUI!** No Python installation required!

Or run from terminal:
- `staminabuyer gui` - Open GUI
- `staminabuyer run --target "Window:100"` - CLI mode

### Option 2: Install with pip

```bash
pip install stamina-buyer
```

### Option 3: Install from Source (For Developers)

```bash
git clone https://github.com/yourusername/stamina-buyer.git
cd stamina-buyer
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .[dev]
```

## Usage

### 🎨 GUI Mode (Recommended)

**The easiest way to use Stamina Buyer:**

```bash
staminabuyer gui
```

Or simply double-click the exe (if using pre-built executable).

The GUI provides:
- 🔍 **Auto-detect** emulator windows with one click
- ➕ **Easy configuration** - add multiple targets visually
- 🧪 **Test mode** - dry-run before purchasing
- 📊 **Live logs** - see exactly what's happening
- 🎯 **Simple workflow** - no command-line knowledge needed

### 💻 Command-Line Mode (Advanced)

**Step 1: Find your emulator window title**
```bash
staminabuyer list-windows
```

Output:
```
Found emulator windows:
  • BlueStacks App Player
  • LDPlayer
```

**Step 2: Buy stamina (dry-run first to test)**
```bash
# Test detection without clicking
staminabuyer run --target "BlueStacks:100" --dry-run

# Actually buy stamina
staminabuyer run --target "BlueStacks:500"
```

**Multiple emulators:**
```bash
staminabuyer run --target "BlueStacks:500" --target "LDPlayer:300"
```

Each `--target` string is `<window_title>:<stamina_to_buy>`.

**Note:** The emulator window must be visible (not minimized) during operation.

### Configuration Files

For repeated use, create a `config.yaml`:
```yaml
targets:
  - name: "BlueStacks App Player"
    stamina: 500
  - name: "LDPlayer"
    stamina: 300
purchase_delay_seconds: 1.5
jitter_seconds: 0.3
```

Then run:
```bash
staminabuyer run --config config.yaml
```

## Requirements

**System:**
- Windows, macOS, or Linux
- Python 3.11+ (or use pre-built executable - no Python needed!)

**Emulator:**
- Any Android emulator (BlueStacks, LDPlayer, NoxPlayer, MEmu, MuMu, etc.)
- Emulator window must be **visible** (not minimized) during operation
- Evony: The King's Return installed and logged in
- Navigate to Black Market screen before running

**That's it!** No ADB, no special configuration needed.

## How It Works

1. **Finds your emulator window** by title (e.g., "BlueStacks")
2. **Captures screenshot** directly from the window
3. **Detects stamina card** using template matching (OpenCV)
4. **Clicks the gem button** at the bottom of the detected card
5. **Confirms purchase** by detecting and clicking the confirmation dialog
6. **Repeats** until the requested amount is purchased

All detection is resolution-independent thanks to multi-scale template matching (0.5x-2.0x).

## Development
- `pytest` for unit tests.
- `ruff` for linting/format.
- Keep docstrings/comments concise and focused on non-obvious behavior.

## Building Standalone Executables

To create executables for distribution (no Python required by end users):

```bash
# Install build dependencies
pip install -e .[build]

# Build using PyInstaller
pyinstaller staminabuyer.spec

# Or use the build script
python build_executable.py
```

Output will be in `dist/staminabuyer` (or `dist/staminabuyer.exe` on Windows).

See [DISTRIBUTION.md](DISTRIBUTION.md) for detailed packaging and distribution options.
