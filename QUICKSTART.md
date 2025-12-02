# Quick Start Guide

**Stamina Buyer** automates purchasing stamina from the Black Market in Evony: The King's Return.

**✨ No ADB, no configuration - just run it!**

## ⚡ 3-Minute Setup

### 1. Prerequisites

**Required:**
- Android emulator (BlueStacks, LDPlayer, NoxPlayer, MEmu, MuMu, etc.)
- Evony: The King's Return running on emulator
- Emulator window must be **visible** (not minimized)

**That's it!** No ADB installation needed.

### 2. Download Stamina Buyer

Download the executable for your platform:
- **Windows:** [staminabuyer.exe](releases)
- **macOS/Linux:** [staminabuyer](releases) (then `chmod +x staminabuyer`)

Or install with pip:
```bash
pip install stamina-buyer
```

### 3. Find Your Emulator Window

```bash
./staminabuyer list-windows
```

This shows all emulator windows:
```
Found emulator windows:
  • BlueStacks App Player
  • LDPlayer
  • NoxPlayer
```

Note your emulator's window title!

### 4. Navigate to Black Market

In Evony:
1. Open your emulator
2. Navigate to **Black Market** screen
3. Make sure stamina cards are visible (if not, wait for refresh or use Instant Refresh)

### 5. Run Stamina Buyer

**Dry Run (Test First - Recommended):**
```bash
# Replace "BlueStacks" with your window title from step 3
./staminabuyer run --target "BlueStacks:10" --dry-run
```

This will test detection without actually clicking anything. You should see logs like:
```
✓ Matched 'stamina_10' with score 0.826
Tapping coordinates (150, 950)
```

**Real Purchase:**
```bash
# Buy 100 stamina (10 packs of 10)
./staminabuyer run --target "BlueStacks:100"
```

**Important:** Keep the emulator window visible during operation!

## 📝 Command Examples

```bash
# Buy from single emulator
./staminabuyer run --target "BlueStacks:500"

# Buy from multiple emulators
./staminabuyer run \
  --target "BlueStacks:500" \
  --target "LDPlayer:300"

# Test without clicking (dry run)
./staminabuyer run --target "BlueStacks:100" --dry-run

# More retries if detection is slow
./staminabuyer run --target "BlueStacks:100" --max-retries 5
```

## 🎯 Target Format

```
--target "<WindowTitle>:<StaminaAmount>"
```

- **WindowTitle:** Window title from `staminabuyer list-windows`
- **StaminaAmount:** Total stamina to buy (buys in packs of 10)

Examples:
- `"BlueStacks:100"` - Buy 100 stamina (10 packs)
- `"LDPlayer:500"` - Buy 500 stamina (50 packs)
- `"NoxPlayer:50"` - Buy 50 stamina (5 packs)

**Tip:** If window title has spaces, use quotes: `"BlueStacks App Player:100"`

## 🔧 Troubleshooting

### "Failed to locate 'stamina_10'"

**Cause:** Not at Black Market screen, or cards look different

**Fix:**
1. Make sure you're on the Black Market screen
2. Make sure stamina cards are visible (wait for refresh or use Instant Refresh)
3. Ensure emulator window is fully visible (not partially off-screen)
4. Try increasing retries: `--max-retries 5`

### "Could not find window with title..."

**Cause:** Window title doesn't match or emulator not visible

**Fix:**
1. Run `staminabuyer list-windows` to see exact window title
2. Copy the exact title (including spaces and special characters)
3. Use quotes around title: `--target "BlueStacks App Player:100"`
4. Make sure emulator window is not minimized

### Clicks in wrong location

**Cause:** Window moved or coordinates off

**Fix:**
1. Keep emulator window in same position during operation
2. Make sure window is not maximized (some OSes add borders)
3. Try running dry-run first to verify detection
4. Close and restart both emulator and tool

### Purchases too fast

**Cause:** Default delay might be too short for your game/network

**Fix:**
Create a config file `config.yaml`:
```yaml
targets:
  - name: "emulator-5554"
    stamina: 500
purchase_delay_seconds: 2.0  # Increase delay
jitter_seconds: 0.5
```

Then run:
```bash
./staminabuyer run --config config.yaml
```

## 📊 What It Does

1. **Captures** screenshot from emulator
2. **Detects** stamina card using computer vision
3. **Taps** gem purchase button (bottom of card)
4. **Detects** confirmation dialog
5. **Taps** confirm button
6. **Repeats** until requested amount purchased

## 🛡️ Safety Features

- **Dry-run mode** to test without tapping
- **Template matching** ensures correct elements are tapped
- **Retry logic** if detection fails temporarily
- **Logging** of all actions for debugging

## ⚙️ Advanced Options

```bash
# Use configuration file
./staminabuyer run --config myconfig.yaml

# Adjust retry attempts
./staminabuyer run --target "emu:100" --max-retries 5

# Multiple targets from config + CLI
./staminabuyer run --config base.yaml --target "emu2:100"
```

## 📞 Getting Help

If issues persist:
1. Check that ADB works: `adb devices`
2. Test with dry-run: `--dry-run`
3. Check logs for specific errors
4. Verify you're on Black Market screen
5. Try manually tapping to confirm UI is responsive

## ⚖️ Disclaimer

This tool is for personal use. Use at your own risk. Automating games may violate terms of service.

