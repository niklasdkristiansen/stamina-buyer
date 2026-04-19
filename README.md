# Stamina Buyer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Release](https://img.shields.io/github/v/release/niklasdkristiansen/stamina-buyer)](https://github.com/niklasdkristiansen/stamina-buyer/releases)

Automate stamina purchases from the Black Market in Evony: The King's Return.

**Point-and-click app.** No ADB, no debug bridges, no config files —
download it, double-click, and watch it buy stamina.

## Features

- 🖱️ **Double-click to run** — no terminal, no Python, no setup
- 🎨 **Friendly GUI** — auto-detects your emulator, shows live progress
- 🖥️ **Works with any emulator** — BlueStacks, LDPlayer, NoxPlayer, MEmu, MuMu, …
- 📐 **Resolution-agnostic** — anchor-based UI scale calibration + Retina/DPI click correction, so arbitrary window sizes and 2× displays work out of the box
- 🧠 **Never re-buys** — greyed-out cards are detected automatically and skipped
- 🔁 **Auto-refresh** — refreshes the Black Market until the requested stamina is reached
- 🚀 **Multi-instance** — queue up several emulators in one run

## Download

Grab the latest build for your platform:

👉 **[Releases](https://github.com/niklasdkristiansen/stamina-buyer/releases)**

- **Windows:** `staminabuyer.exe`
- **macOS:** `staminabuyer` (right-click → Open the first time, or `chmod +x staminabuyer`)

## Use it (30 seconds)

1. **Open your emulator** and navigate to the Black Market screen in Evony.
2. **Double-click `staminabuyer`** (or `staminabuyer.exe` on Windows).
3. **Click "Detect"** — it finds the emulator window automatically.
4. **Enter a stamina amount** and click **Add**.
5. **Click "Start"** and watch the log.

> ⚠️ Keep the emulator window visible (not minimized or hidden behind
> another window) while it runs — the tool reads pixels off the actual
> window.

## Tested setup

Primary test bed is **BlueStacks on macOS** (Retina display, window widths
anywhere from ~340px to ~1920px). The matcher auto-calibrates scale from
the refresh button, so other emulators, window sizes, and DPIs should work
without manual tuning.

## Customising the item catalog

The stamina items to buy live in [`assets/items.yaml`](assets/items.yaml):

```yaml
items:
  - template: stamina_10   # PNG in assets/icons/ (without extension)
    amount: 500            # stamina credited per purchase
  - template: stamina_1
    amount: 50
```

Items at the top are tried first. Add a new entry by dropping a reference
PNG into `assets/icons/` and listing its `template` name here.

## Power-user mode (CLI)

There's also a command-line interface for scripting, dry-runs, and CI —
see [QUICKSTART.md](QUICKSTART.md#advanced-cli) if you want it. The GUI is
the recommended path for everyone else.

## Contributing

- [QUICKSTART.md](QUICKSTART.md) — user guide (GUI + CLI)
- [DISTRIBUTION.md](DISTRIBUTION.md) — packaging & release mechanics
- `pytest -q` — 84 tests, ~24s on a laptop

## License

MIT — free to use, modify, and distribute with attribution. See [LICENSE](LICENSE).
