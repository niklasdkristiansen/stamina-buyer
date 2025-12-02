# GUI User Guide

**Stamina Buyer** now has a modern, user-friendly graphical interface! 🎨

## 🚀 Launching the GUI

### Method 1: Double-Click (Easiest)
If you have the pre-built executable:
- **Windows:** Double-click `staminabuyer.exe`
- **macOS/Linux:** Double-click `staminabuyer` (or `./staminabuyer` from terminal)

The GUI will open automatically!

### Method 2: Command Line
```bash
staminabuyer gui
```

Or:
```bash
staminabuyer-gui
```

## 📖 How to Use the GUI

### Step 1: Detect Emulator Windows 🔍

1. Make sure your emulator(s) are running and visible
2. Click **"🔍 Detect Windows"** button
3. The dropdown will show all detected emulator windows
4. Select the emulator you want to use

**Example Output:**
```
✅ Found 2 emulator window(s)
   • BlueStacks App Player
   • LDPlayer
```

### Step 2: Add Targets ➕

1. Select an emulator window from the dropdown
2. Enter the stamina amount (e.g., `100`, `500`)
3. Click **"➕ Add Target"**
4. Repeat for multiple emulators if needed

**Target List Shows:**
```
1. BlueStacks App Player → 500 stamina
2. LDPlayer → 300 stamina
```

You can add the same emulator multiple times with different amounts.

### Step 3: Test First (Recommended) 🧪

Click **"🧪 Test (Dry Run)"** to:
- Test window detection
- Test template matching
- Verify coordinates
- See what will happen **without actually clicking**

Watch the Activity Log to see if detection works properly.

### Step 4: Buy Stamina 🚀

1. Click **"🚀 Buy Stamina"** button
2. Type `yes` in the confirmation dialog
3. Watch the Activity Log for progress
4. Keep the emulator windows visible during operation

**Important:** Do not minimize emulator windows while the tool is running!

## 🎯 GUI Features

### 📋 Activity Log
Real-time log showing:
- Window detection results
- Match scores and coordinates
- Tap locations
- Progress through purchases
- Errors and warnings

### 📊 Progress Bar
Shows overall progress during operation.

### 🗑️ Clear Buttons
- **Clear All** - Remove all targets
- **Clear Log** - Clear the activity log

### ⚠️ Safety Features
- **Confirmation dialog** before purchasing
- **Dry-run mode** for testing
- **Disabled controls** during operation (prevents double-clicks)
- **Error handling** with clear messages

## 💡 Tips

### Multiple Instances
You can add multiple targets for parallel operation:
```
1. BlueStacks → 500 stamina
2. LDPlayer → 300 stamina
3. NoxPlayer → 200 stamina
```

The tool will process them sequentially.

### Window Detection Issues?
If "Detect Windows" doesn't find your emulator:
1. Make sure emulator is running
2. Make sure emulator window is not minimized
3. Try closing and reopening the emulator
4. Check that the emulator window has a title (visible in title bar)

### Before Running
Make sure:
- ✅ Emulator is at the Black Market screen
- ✅ Stamina cards are visible (not sold out - wait for refresh)
- ✅ Emulator window is fully visible (not off-screen)
- ✅ No other windows covering the emulator

### During Operation
- ✅ Keep emulator windows visible
- ✅ Don't minimize them
- ✅ Don't move them (can cause coordinate issues)
- ✅ Don't interact with the emulator manually

## 🐛 Troubleshooting

### "No emulators found"
**Solution:**
- Restart your emulator
- Make sure it's fully loaded
- Try using Command-Line mode: `staminabuyer list-windows`

### Detection works but clicks wrong location
**Solution:**
- Keep window in same position
- Avoid fullscreen mode (some OSes add borders)
- Try restarting both emulator and tool

### GUI doesn't start
**Solution:**
```bash
# Check if GUI dependencies are installed
pip install customtkinter pillow

# Or reinstall the tool
pip install --force-reinstall stamina-buyer
```

## 🎨 GUI Appearance

The GUI uses a **modern dark theme** optimized for:
- Gaming aesthetics
- Easy reading
- Clear button states
- Professional look

All elements are clearly labeled with emoji icons for quick identification.

## ⌨️ Keyboard Shortcuts

- **Ctrl+C** in terminal - Stop operation (if running from terminal)
- **Escape** - Close confirmation dialogs
- **Tab** - Navigate between controls

## 📝 Comparison: GUI vs Command-Line

| Feature | GUI | Command-Line |
|---------|-----|--------------|
| **Ease of Use** | ⭐⭐⭐⭐⭐ Very Easy | ⭐⭐⭐ Moderate |
| **Window Detection** | ✅ One-click | Manual command |
| **Configuration** | ✅ Visual | Type commands |
| **Log Viewing** | ✅ Built-in | Terminal output |
| **Testing** | ✅ One button | Add `--dry-run` |
| **Multi-Instance** | ✅ Visual list | Multiple `--target` |
| **Automation** | ❌ Interactive only | ✅ Can script |
| **Speed** | Same | Same |

## 🎯 Best Practices

1. **Always test first** - Use dry-run before real purchases
2. **Start small** - Test with 10-50 stamina before larger amounts
3. **Watch the log** - Monitor for errors or issues
4. **One at a time** - When learning, add one target at a time
5. **Keep visible** - Don't minimize emulator windows

## 🆘 Getting Help

If you encounter issues:
1. Check the Activity Log for error messages
2. Try dry-run mode to test detection
3. Use `staminabuyer list-windows` from command-line
4. Refer to QUICKSTART.md for detailed troubleshooting
5. Report issues with screenshots of the GUI and log output

---

**Enjoy the GUI! It's designed to make stamina buying as simple as clicking a few buttons.** 🎮✨

