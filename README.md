<div align="center">

<img src="assets/icons/readme_icon.png" alt="Logo" width="300"/>

# NTE Auto-Fishing

[English](README.md) | [简体中文](docs/README_zh.md) | [日本語](docs/README_ja.md)

**A visual, configurable auto-fishing assistant built for responsive game control.**

Built with Python, OpenCV, MSS, PyDirectInput, and DearPyGui.

---

[![GitHub License](https://img.shields.io/github/license/Chizukuo/NTE-auto-fish)](https://github.com/Chizukuo/NTE-auto-fish/blob/main/LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/Chizukuo/NTE-auto-fish)](https://github.com/Chizukuo/NTE-auto-fish/releases)
[![GitHub Downloads](https://img.shields.io/github/downloads/Chizukuo/NTE-auto-fish/total)](https://github.com/Chizukuo/NTE-auto-fish/releases)
[![Build Status](https://github.com/Chizukuo/NTE-auto-fish/actions/workflows/build.yml/badge.svg)](https://github.com/Chizukuo/NTE-auto-fish/actions)
[![GitHub Stars](https://img.shields.io/github/stars/Chizukuo/NTE-auto-fish)](https://github.com/Chizukuo/NTE-auto-fish/stargazers)

</div>

## Highlights

- **Live control center**: Track bot state, fish count, session time, FPS, PID output, ROI data, and vision health in one GUI.
- **Safer controls**: The GUI starts paused, handles stop commands urgently, and releases held keys during pause, stop, recalibration, and shutdown.
- **Runtime tuning**: PID, HSV thresholds, timing, input keys, hotkeys, calibration, and debug options can be adjusted from the Settings tab. ([Settings Guide](docs/SETTINGS_GUIDE.md))
- **Resolution adaptation**: Ratio-based ROI calibration with resolution-proportional fallback supports 1080p, 2K, 4K, and custom display sizes automatically.
- **Fast capture and input**: `mss` captures screen regions efficiently, while `PyDirectInput` sends game-friendly input events.
- **Portable builds**: GitHub Actions produces a single-file Windows EXE for GUI and a lightweight source package for CLI.

## Project Structure

| Path | Description |
| :--- | :--- |
| `start_gui.py` | Recommended GUI entry point. |
| `main.py` | Headless entry point and core bot loop. |
| `config.py` | Runtime configuration for PID, HSV, keys, timing, and calibration. |
| `gui/` | DearPyGui control center, panels, and thread-safe bridge. |
| `modules/` | Capture, input, vision, and fishing logic modules. |
| `templates/` | Ratio data for automatic ROI calibration. |
| `tools/ratio_annotator.py` | Utility for creating ratio-based ROI JSON from screenshots. |

## Getting Started

### Option 1: Prebuilt Executable (GUI)

1. Download the latest `NTE-Auto-Fish-v*.*.*-Windows-x64.exe` from [Releases](https://github.com/Chizukuo/NTE-auto-fish/releases).
2. Run it as Administrator so simulated input can reach the game.

### Option 2: CLI Package

1. Download `NTE-Auto-Fish-v*.*.*-CLI.zip` from [Releases](https://github.com/Chizukuo/NTE-auto-fish/releases) and extract it.
2. Install dependencies once with `python -m pip install -r requirements.txt`.
3. For more options, run `python main.py --help` in a terminal. Available commands: `start`, `calibrate`, `config show/set`, `reset`.

### Option 3: Run From Source

```bash
git clone https://github.com/Chizukuo/NTE-auto-fish.git
cd NTE-auto-fish
pip install -r requirements.txt
```

Launch the GUI:

```bash
python start_gui.py
```

Launch headless mode:

```bash
python main.py
```

### Build a Windows EXE from Linux

PyInstaller is not a cross-compiler, and this application uses Windows-only input APIs. The Linux helper therefore
starts the repository's Windows GitHub Actions runner and downloads its artifact. Install and authenticate the
[GitHub CLI](https://cli.github.com/) first, and push the branch and icon file before building.

```bash
./scripts/build-from-linux.sh \
  --app-name "Fishing Tools" \
  --icon random
```

The artifact is downloaded to `dist/remote/`. Branding is configurable: `--app-name` changes the EXE,
window, and sidebar name, while `--icon` changes the EXE and window icon. Built-in choices are `classic`, `bobber`,
`target-fish`, and `fisher-cat`; `random` (the default) picks one per build. Select a named icon for reproducible
builds, or provide a custom `.ico` path.
On Windows, run the same build directly with `python scripts/build_windows.py --app-name "Fishing Tools" --icon random`. App names are ASCII-only
to avoid native Windows title-bar encoding problems. Every build receives a random 12-character build ID in its
filename and window title to prevent artifact collisions. Pass `--build-id my-id` when a stable ID is preferred.
Branded builds also namespace their settings, log, debug CSV, and session directory with the app name and build ID,
so multiple builds can run from the same directory without overwriting each other's runtime data. Unbranded source
runs retain the legacy filenames.

### Build locally in Windows Sandbox

For a fully local build without GitHub Actions, enable Windows Sandbox and run this from Windows PowerShell:

```powershell
# Run once as Administrator, then restart Windows if prompted.
Enable-WindowsOptionalFeature -Online -FeatureName "Containers-DisposableClientVM" -All

# Run from the repository on subsequent builds.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_with_windows_sandbox.ps1 -AppName "Fishing Tools" -Icon random
```

From WSL, the equivalent local command is:

```bash
./scripts/build-with-windows-sandbox.sh -AppName "Fishing Tools" -Icon random
```

The script stages a temporary read-only copy of the source, starts Windows Sandbox, installs Python and the build
dependencies inside it, and copies only the resulting EXE to `dist\sandbox`. Python installers and pip downloads are
cached under the current user's local application data to make later builds faster. The temporary Sandbox and staged
source are discarded after each build. A custom output directory, stable build ID, or named built-in icon can be set
with `-OutputDirectory`, `-BuildId`, and `-Icon`. Build details and failures are retained in `sandbox-build.log`.

## Notes

- Run from an elevated terminal on Windows.
- Borderless window or windowed fullscreen usually gives the most reliable capture behavior.
- Hotkeys are configurable in the GUI and re-register after editing.
- Debug logging writes extra tracking data to `fishing_data.csv`; branded builds add their build namespace to the filename.

## Known Issues

- **Dawn/dusk lighting**: During in-game sunrise and sunset, the warm yellow ambient lighting significantly interferes with HSV-based cursor detection, causing tracking failures and drastically reduced fishing success rates. This is an inherent limitation of the current color-based detection approach. If you encounter this, consider adjusting the cursor HSV thresholds in Settings to compensate for the shifted lighting conditions.

---

<div align="center">
Built for practical, low-friction automation.
</div>
