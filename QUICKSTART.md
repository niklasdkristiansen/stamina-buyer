# Quick Start

**Stamina Buyer** automates purchasing stamina from the Black Market in
Evony: The King's Return. No ADB, no debug bridges, no config files.

---

## 1. Prerequisites

- Any Android emulator running Evony (BlueStacks, LDPlayer, NoxPlayer, MEmu, MuMu, …)
- Emulator window must be **visible** — not minimized, not fully covered by another window

That's it.

## 2. Install

Download the prebuilt binary for your OS:

- **Windows:** `staminabuyer.exe` — [Releases](https://github.com/niklasdkristiansen/stamina-buyer/releases)
- **macOS:** `staminabuyer` — [Releases](https://github.com/niklasdkristiansen/stamina-buyer/releases)
  - First run: right-click → Open (bypasses Gatekeeper), or `chmod +x staminabuyer`

Prefer Python? `pip install -e .` from the repo (requires Python ≥ 3.11).

## 3. Run it

**Double-click the executable.** The GUI opens automatically.

| In the window | What to do |
| --- | --- |
| **Detect** | Click it. The tool finds your emulator window by title. |
| **Stamina amount** | Type how much stamina you want to buy (e.g. `500`). |
| **Add** | Adds that target to the queue. Repeat for more emulators if you want. |
| **Start** | Go. Live log shows every purchase as it happens. |
| **Stop / X** | Cancels gracefully at the next safe checkpoint. |

> ⚠️ Keep the emulator window visible for the whole run. If you
> alt-tab over it or minimize it, the tool can't read pixels and
> won't be able to click.

## 4. That's it

The tool:

1. Captures the emulator window at native resolution.
2. Calibrates the UI's scale from the refresh button, so it handles any window size or DPI.
3. Finds the best-scoring available stamina card, skipping already-purchased (greyed-out) ones.
4. Taps the gem-price button, then the confirmation dialog.
5. Refreshes the Black Market as needed and repeats until the requested stamina is hit.

---

## Customising the item catalog

The default catalog lives in [`assets/items.yaml`](assets/items.yaml) and
is bundled into the binary. Override it by editing that file (if you're
running from source) or, with the CLI, via `--items-file`:

```yaml
# my_items.yaml
items:
  - template: stamina_10   # PNG in assets/icons/ (without extension)
    amount: 500            # stamina credited per purchase
  - template: stamina_1
    amount: 50
```

Items are tried in listed order (top = highest priority).

## Troubleshooting

### The "Detect" button doesn't find my emulator

- Make sure the emulator window is open and on top of other windows.
- Restart the emulator. Some emulators take a few seconds to register
  their window title with the OS.
- On macOS, the first run may prompt for **Accessibility / Screen
  Recording** permissions — grant both, then restart the app.

### It says it bought something but nothing happened in-game

- The gem-price button may have been mis-targeted. Reduce the emulator
  window size slightly and retry — really small or really stretched
  windows can push the price button off its expected spot.
- Check that the Black Market screen is actually showing cards (not an
  overlay dialog, chat popup, ad, etc.).

### Clicks land in the wrong place (macOS / Retina)

DPI scaling is auto-measured on the first screenshot, so the very first
click after launching may be learning the scale. If subsequent clicks are
still off, close the app, make sure the emulator isn't mid-animation,
and relaunch.

### Purchases feel too fast / rate-limited

If you want more breathing room between clicks, use a config file with
the CLI (see below) — the GUI uses sensible defaults.

---

## Advanced: CLI

The CLI is here for scripting, automation, dry runs, and CI. The GUI is
the recommended path for everyday use.

### Find your emulator window title

```bash
staminabuyer list-windows
```

### Dry-run (no clicks)

```bash
staminabuyer run --target "BlueStacks App Player:100" --dry-run
```

### Real run

```bash
staminabuyer run --target "BlueStacks App Player:100"
```

### Multiple targets

```bash
staminabuyer run \
  --target "BlueStacks:500" \
  --target "LDPlayer:300"
```

### Config file

```yaml
# config.yaml
targets:
  - name: "BlueStacks App Player"
    stamina: 500
purchase_delay_seconds: 2.0   # base delay between purchase attempts
jitter_seconds: 0.5           # random +/- added to the delay
```

```bash
staminabuyer run --config config.yaml
```

CLI `--target` flags are additive with file targets.

### Custom item catalog

```bash
staminabuyer run --target "BlueStacks:1000" --items-file my_items.yaml
```

### Everything else

```bash
staminabuyer --help
staminabuyer run --help
```

---

## Disclaimer

This tool is for personal use. Use at your own risk. Automating games may
violate the game's terms of service.
