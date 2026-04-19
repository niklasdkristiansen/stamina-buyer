# Distribution Guide

This guide explains how to package Stamina Buyer for distribution to users who don't have Python installed.

## 📦 Distribution Options

### Option 1: PyInstaller (Recommended for Desktop)

Creates standalone executables for Windows, macOS, and Linux.

**Pros:**
- No Python installation required by end users
- Single executable or folder-based distribution
- Works on Windows, macOS, Linux

**Cons:**
- Larger file size (~50-100MB due to bundled dependencies)
- Slower first startup (single-file mode)
- Platform-specific builds (build on each OS)

#### Quick Build

```bash
# Install build dependencies
pip install pyinstaller

# Build using the spec file (recommended)
pyinstaller staminabuyer.spec

# OR use the build script
python build_executable.py
```

**Output:** `dist/staminabuyer` (or `dist/staminabuyer.exe` on Windows)

#### Platform-Specific Notes

**Windows:**
```bash
# Build on Windows to create .exe
pyinstaller staminabuyer.spec

# Output: dist/staminabuyer.exe (~80MB)
```

**macOS:**
```bash
# Build on macOS to create macOS binary
pyinstaller staminabuyer.spec

# Output: dist/staminabuyer (~70MB)

# Optional: Code sign for distribution
codesign --force --sign "Developer ID" dist/staminabuyer
```

**Linux:**
```bash
# Build on Linux to create Linux binary
pyinstaller staminabuyer.spec

# Output: dist/staminabuyer (~75MB)
```

#### Testing the Executable

```bash
# Test dry-run
./dist/staminabuyer run --target "test:10" --dry-run

# Test version
./dist/staminabuyer --version
```

---

### Option 2: Docker Container

Creates a containerized version that works anywhere Docker runs.

**Pros:**
- Platform-independent
- Consistent environment
- Easy updates

**Cons:**
- Requires Docker installation
- Can't reach the host's display server to read the emulator window — useful for CI only
- Larger download size

#### Dockerfile

Create `Dockerfile`:

> ⚠️ Docker is **not** a supported runtime for real use. Stamina Buyer
> needs direct access to the host's display server to read the emulator
> window and synthesise clicks, which is awkward to expose into a
> container. The snippet below is only useful for headless CI checks
> (e.g. running `pytest` or `staminabuyer --help`).

```dockerfile
FROM python:3.12-slim

# OpenCV runtime libs
RUN apt-get update && \
    apt-get install -y libgl1-mesa-glx libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .[dev]

ENTRYPOINT ["staminabuyer"]
CMD ["--help"]
```

#### Build and Use (CI only)

```bash
docker build -t staminabuyer:latest .
docker run --rm staminabuyer --help
```

---

### Option 3: Python Wheel Distribution

Distributes as a Python package (users need Python installed).

**Pros:**
- Smallest file size (~50KB)
- Easy to update via pip
- Cross-platform

**Cons:**
- Users must have Python 3.11+ installed
- Users must install dependencies

#### Build Wheel

```bash
# Install build tools
pip install build

# Build wheel
python -m build

# Output: dist/stamina_buyer-0.1.0-py3-none-any.whl
```

#### User Installation

```bash
# Install from wheel
pip install stamina_buyer-0.1.0-py3-none-any.whl

# Or directly from source
pip install .
```

---

### Option 4: GitHub Releases with Pre-built Binaries

Best for open-source distribution.

**Setup:**
1. Use GitHub Actions to auto-build on push
2. Create releases with binaries for each platform
3. Users download for their OS

#### GitHub Actions Workflow

Create `.github/workflows/build.yml`:

```yaml
name: Build Executables

on:
  push:
    tags:
      - 'v*'

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pyinstaller
      - name: Build
        run: pyinstaller staminabuyer.spec
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: staminabuyer-windows
          path: dist/staminabuyer.exe

  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pyinstaller
      - name: Build
        run: pyinstaller staminabuyer.spec
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: staminabuyer-macos
          path: dist/staminabuyer

  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pyinstaller
      - name: Build
        run: pyinstaller staminabuyer.spec
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: staminabuyer-linux
          path: dist/staminabuyer
```

---

## 🚀 Recommended Distribution Strategy

### For Public Release:
1. **Use PyInstaller** to create binaries for each platform
2. **Host on GitHub Releases** with auto-building via Actions
3. **Provide checksums** for verification
4. **Include quick-start guide** in release notes

### For Private/Internal Use:
1. **Build locally** with PyInstaller
2. **Share via file server** or internal distribution system
3. **Point users at [QUICKSTART.md](QUICKSTART.md)** for `list-windows` + `run` usage

---

## 📋 Distribution Checklist

Before distributing, ensure:

- ✅ All tests pass (`pytest tests/`)
- ✅ Templates (`assets/icons/*.png`) and `assets/items.yaml` are included in the bundle
- ✅ Executable runs without Python installed
- ✅ Platform-specific instructions provided
- ✅ Version number is correct
- ✅ README and QUICKSTART reflect the current CLI
- ✅ License file included

---

## 🔧 Troubleshooting Builds

### "Module not found" errors
Add missing modules to `hiddenimports` in `staminabuyer.spec`

### Large executable size
- Use `--onedir` instead of `--onefile` (faster, smaller)
- Enable UPX compression
- Exclude unused packages in spec file

### OpenCV/NumPy issues
- Ensure `collect_all` includes both packages
- May need to install `opencv-python-headless` instead

### macOS "app is damaged" error
Code sign the executable:
```bash
codesign --force --deep --sign - dist/staminabuyer
```

### Linux missing libraries
Install required system libraries:
```bash
sudo apt-get install libgl1-mesa-glx libglib2.0-0
```

---

## 📝 Release Notes Template

```markdown
## Stamina Buyer v0.1.0

### Download

- **Windows:** [staminabuyer-windows.exe](link) (80MB)
- **macOS:** [staminabuyer-macos](link) (70MB)
- **Linux:** [staminabuyer-linux](link) (75MB)

### Requirements

- Android emulator running Evony, window visible (not minimized)

### Quick Start

1. Download the executable for your platform
2. Make executable (macOS/Linux): `chmod +x staminabuyer`
3. Find the emulator window: `./staminabuyer list-windows`
4. Run: `./staminabuyer run --target "YourEmulator:100"`

### Checksums

- Windows: `sha256sum here`
- macOS: `sha256sum here`
- Linux: `sha256sum here`
```

---

## 🎯 File Size Comparison

| Method | Size | Startup Time | User Setup |
|--------|------|--------------|------------|
| PyInstaller (onefile) | ~80MB | Slow (2-3s) | None |
| PyInstaller (onedir) | ~120MB | Fast (<1s) | Unzip folder |
| Docker | ~200MB | Medium | Install Docker |
| Wheel | ~50KB | Fast | Install Python + deps |

**Recommendation:** Use PyInstaller `--onefile` for easiest distribution, or `--onedir` for better performance.

