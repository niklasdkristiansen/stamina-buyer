# ADB vs Screen Capture Mode

Stamina Buyer supports two methods for interacting with emulators:

## 🔵 Method 1: ADB Mode (Default, Currently Implemented)

Uses Android Debug Bridge to capture screenshots and send tap commands.

### ✅ Advantages:
- **More reliable** - Direct device communication
- **Works when minimized** - Emulator can run in background
- **Precise coordinates** - No window borders to account for
- **Multi-instance friendly** - Each emulator has unique device ID
- **Standard approach** - Used by most Android automation tools

### ❌ Disadvantages:
- **Requires ADB installation** - Users must download and configure
- **Requires ADB enabled** - Must enable in emulator settings
- **Port configuration** - May need to connect manually
- **Learning curve** - Users need to understand `adb devices`

### 📦 Installation:
```bash
# Windows
Download: https://developer.android.com/studio/releases/platform-tools
Add to PATH

# macOS
brew install android-platform-tools

# Linux
sudo apt-get install android-tools-adb
```

### 🎮 Usage:
```bash
# Find emulator
adb devices
# Output: emulator-5554   device

# Run tool
staminabuyer run --target "emulator-5554:100"
```

---

## 🖥️ Method 2: Screen Capture Mode (Alternative, Less Setup)

Captures the emulator window directly and simulates mouse clicks.

### ✅ Advantages:
- **No ADB required** - Nothing to install or configure
- **Easier setup** - Just find window title
- **Universal** - Works with any emulator (even with ADB disabled)
- **Simpler for users** - More intuitive

### ❌ Disadvantages:
- **Window must be visible** - Can't minimize or cover window
- **Window borders** - Need to account for title bar/borders
- **Window can move** - Less stable if user moves window
- **Platform-specific** - Different code for Windows/Mac/Linux
- **Multi-monitor issues** - Can be problematic with multiple screens

### 📦 Installation:
```bash
pip install -e .[screencapture]
```

### 🎮 Usage:
```bash
# Find emulator windows
staminabuyer list-windows

# Output:
# Found emulator windows:
#   - BlueStacks App Player
#   - LDPlayer
#   - NoxPlayer

# Run tool
staminabuyer run --target "BlueStacks:100" --mode screen
```

---

## 📊 Comparison Table

| Feature | ADB Mode | Screen Capture Mode |
|---------|----------|---------------------|
| **User Setup** | ⚠️ Medium (install ADB) | ✅ Easy (no install) |
| **Configuration** | ⚠️ Enable ADB, find port | ✅ Just window title |
| **Reliability** | ✅ High | ⚠️ Medium |
| **Background Running** | ✅ Yes | ❌ No (must be visible) |
| **Multi-Instance** | ✅ Easy | ⚠️ Moderate |
| **Cross-Platform** | ✅ Same commands | ⚠️ Platform differences |
| **Window Moved** | ✅ No effect | ⚠️ Needs re-detection |
| **Performance** | ✅ Fast | ✅ Fast |

---

## 💡 Recommendation

### **For Personal Use (You):**
→ **Use ADB Mode** - It's more reliable for long automation sessions

### **For Distribution (Other Users):**
→ **Offer Both Options:**
- Default to **Screen Capture Mode** (easier setup)
- Advanced users can use **ADB Mode** (more reliable)

---

## 🔧 Implementation Status

### ✅ Currently Implemented:
- ADB Mode (full implementation in `emulator/adb.py`)
- Template matching and vision system
- Pipeline orchestration

### 🚧 To Add Screen Capture Mode:
- [x] Screen capture client (`emulator/screen_capture.py`)
- [ ] CLI flag to choose mode: `--mode adb` or `--mode screen`
- [ ] Update pipeline to use either ADBClient or ScreenCaptureClient
- [ ] Add window detection helper commands
- [ ] Update documentation

---

## 🎯 Quick Start Examples

### Using ADB Mode:
```bash
# Setup (one-time)
brew install android-platform-tools  # or download on Windows

# Enable ADB in emulator settings
# BlueStacks: Settings → Advanced → Enable ADB

# Connect
adb connect 127.0.0.1:5555

# Run
staminabuyer run --target "127.0.0.1:5555:100"
```

### Using Screen Capture Mode:
```bash
# Setup (one-time)
pip install -e .[screencapture]

# Find window
staminabuyer list-windows
# Or just know it's "BlueStacks"

# Run (window must be visible!)
staminabuyer run --target "BlueStacks:100" --mode screen
```

---

## 🤔 Which Should You Use?

**Choose ADB Mode if:**
- ✅ You're comfortable with command-line tools
- ✅ You want to run emulator in background
- ✅ You're running multiple instances
- ✅ You want maximum reliability

**Choose Screen Capture Mode if:**
- ✅ You want the simplest setup
- ✅ You don't want to install ADB
- ✅ Your emulator has ADB disabled
- ✅ You only run one instance at a time
- ✅ You can keep the window visible

---

## 🔄 Hybrid Approach

You could also **support both** and let users choose:

```bash
# Automatic detection
staminabuyer run --target "auto:100"
# Tries ADB first, falls back to screen capture

# Explicit mode
staminabuyer run --target "BlueStacks:100" --mode screen
staminabuyer run --target "127.0.0.1:5555:100" --mode adb
```

This gives the best of both worlds:
- Easy setup for casual users (screen mode)
- Reliable automation for power users (ADB mode)

