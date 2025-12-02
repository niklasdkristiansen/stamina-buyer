# Creating Releases with GitHub Actions

Your repo now has **automated builds**! When you push a version tag, GitHub Actions automatically:
- ✅ Builds executables for Windows, macOS, and Linux
- ✅ Creates a GitHub Release
- ✅ Uploads all executables
- ✅ Generates checksums
- ✅ Adds release notes

## 🚀 How to Create a Release

### Step 1: Make sure everything is committed and pushed

```bash
cd /Users/nkristiansen/personal/stamina-buyer

# Check status
git status

# Commit any changes
git add .
git commit -m "Prepare for v0.1.0 release"
git push origin main
```

### Step 2: Create and push a version tag

```bash
# Create an annotated tag
git tag -a v0.1.0 -m "Release v0.1.0: Initial release with GUI and ADB-free automation"

# Push the tag (this triggers the build!)
git push origin v0.1.0
```

### Step 3: Watch the magic happen! ✨

1. Go to your repo on GitHub
2. Click "Actions" tab
3. You'll see "Build and Release" workflow running
4. It will build for Windows, macOS, and Linux (takes ~10-15 minutes)
5. When done, go to "Releases" tab
6. Your release is automatically created with all executables!

## 📋 Release Checklist

Before creating a release:

- [ ] All tests pass locally: `pytest tests/`
- [ ] Version number updated if needed
- [ ] README.md is up to date
- [ ] CHANGELOG or release notes prepared
- [ ] Built and tested executable locally: `pyinstaller staminabuyer.spec`
- [ ] All changes committed and pushed
- [ ] Choose appropriate version number (semver):
  - `v0.1.0` - Initial release
  - `v0.2.0` - New features
  - `v0.1.1` - Bug fixes
  - `v1.0.0` - Stable release

## 🏷️ Version Tagging Convention

Use **semantic versioning**: `vMAJOR.MINOR.PATCH`

```bash
# Patch release (bug fixes)
git tag -a v0.1.1 -m "Fix: Window detection on macOS"

# Minor release (new features)
git tag -a v0.2.0 -m "Feature: Add batch processing mode"

# Major release (breaking changes)
git tag -a v1.0.0 -m "Release: Stable v1.0 with all features"
```

## 🔄 Release Workflow

```
Your Local Machine              GitHub Actions              GitHub Releases
     |                                |                            |
     |  git tag v0.1.0               |                            |
     |  git push origin v0.1.0       |                            |
     |------------------------------>|                            |
     |                               |                            |
     |                          [Triggered!]                      |
     |                               |                            |
     |                        Build Windows                       |
     |                        Build macOS                         |
     |                        Build Linux                         |
     |                        Generate Checksums                  |
     |                               |                            |
     |                               |  Create Release           |
     |                               |-------------------------->|
     |                               |                            |
     |                               |                    [Release Published]
     |                               |                            |
     |                               |                   Users can download!
```

## 📦 What Gets Built

For each release, GitHub Actions creates:

1. **staminabuyer-windows.exe** (~80MB)
   - Windows 10/11 compatible
   - Just double-click to run

2. **staminabuyer-macos** (~70MB)
   - macOS 11+ compatible
   - `chmod +x` then run

3. **staminabuyer-linux** (~75MB)
   - Ubuntu/Debian compatible
   - `chmod +x` then run

4. **checksums.txt**
   - SHA256 hashes for verification

## 🐛 If Build Fails

### Check the logs:
1. Go to "Actions" tab on GitHub
2. Click on the failed workflow
3. Click on the failed job
4. Read the error messages

### Common issues:

**Missing dependencies:**
```yaml
# Add to pyproject.toml [project.dependencies]
"missing-package>=1.0.0"
```

**Import errors:**
```python
# Add to staminabuyer.spec hiddenimports
hiddenimports = [
    'missing_module',
]
```

**Build timeout:**
- Builds usually take 10-15 minutes
- If longer, check for infinite loops or hanging processes

## 🔧 Customizing the Release

### Edit release notes:

After the release is created, you can:
1. Go to "Releases" tab
2. Click "Edit" on your release
3. Modify the description
4. Add screenshots, demo GIFs, etc.

### Pre-release:

For beta/alpha releases:
```bash
git tag -a v0.1.0-beta -m "Beta release for testing"
git push origin v0.1.0-beta
```

Then mark as "pre-release" on GitHub.

## 🎯 Example: Your First Release

```bash
# From your project directory
cd /Users/nkristiansen/personal/stamina-buyer

# Make sure everything is up to date
git pull origin main

# Create the tag
git tag -a v0.1.0 -m "Initial release: Stamina Buyer v0.1.0

Features:
- Modern GUI with CustomTkinter
- ADB-free emulator automation
- Computer vision template matching
- Multi-resolution support (0.5x-2.0x)
- Works with all Android emulators
- Dry-run testing mode
- Real-time logging"

# Push the tag (triggers build)
git push origin v0.1.0

# Wait ~10-15 minutes, then check:
# https://github.com/YOUR_USERNAME/stamina-buyer/releases
```

## 📊 Monitoring Builds

### GitHub UI:
- **Actions tab** - See all workflow runs
- **Green checkmark** ✅ - Build succeeded
- **Red X** ❌ - Build failed
- **Yellow dot** 🟡 - Build in progress

### Email notifications:
- GitHub sends emails on build failures
- Configure in Settings → Notifications

## 🚀 After Release

Users can now download by:
1. Going to your repo
2. Click "Releases" (right sidebar)
3. Download the executable for their platform

Update your README.md with:
```markdown
Download the latest release from:
[Releases](https://github.com/YOUR_USERNAME/stamina-buyer/releases/latest)
```

## 💡 Tips

- **Test locally first** - Always build and test with `pyinstaller staminabuyer.spec` before releasing
- **Version consistently** - Use semantic versioning
- **Tag messages** - Write descriptive tag messages, they become release notes
- **Beta releases** - Use `v0.1.0-beta` for testing
- **Hotfix releases** - Use `v0.1.1` for quick bug fixes

## 🎉 That's It!

Now every time you push a tag, GitHub Actions automatically builds and releases your app for all platforms! 🚀

