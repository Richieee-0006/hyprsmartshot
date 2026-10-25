# Project: HyprSmartShot

## Architecture
HyprSmartShot is a high-performance Wayland/Hyprland screenshot utility with Computer Vision UI detection.
- **Frontend / Overlay**: Written in Quickshell (Qt6 QML with Wayland layer-shell protocol). Manages user selection, action pill, freeze screen dimming, and pixel magnifier.
- **Vision Subsystem**: Python 3 with OpenCV (`vision/detect_ui.py`). Performs UI element bounding box detection, column clustering, and browser content area analysis.
- **System Integration**:
  - `grim` for display captures.
  - `satty` for annotations.
  - `wl-clipboard` (`wl-copy`) for image and text clipboard operations.
  - `hyprctl` for Hyprland workspace and client geometry queries.
  - `imagemagick` (`magick` / `convert`) for fast subpixel cropping.
  - Native Wayland floating window (`bin/hyprsmartshot-pin` using PySide6) for Pin to Screen.
- **Packaging**: Arch Linux standard `PKGBUILD`, `PKGBUILD-git`, `.SRCINFO`, and desktop entry in `packaging/arch/`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Register Config Singleton | Declare `singleton Config 1.0 Config.qml` in `components/qmldir` | M1 | Survey (R1) |
| 2 | QML Action Error Handling | Wrap `doCopy`, `doSave`, `doAnnotate`, `doOcr` in defensive `try/catch/finally` ensuring `closeOverlay()` always runs | M1 | Survey (R1) |
| 3 | Shell Argument Quoting | Ensure strict POSIX single-quote escaping (`shellEscape`) across all shell commands | M1 | Survey (R1) |
| 4 | Active Workspace Window Isolation | Filter `clients.json` in `vision/detect_ui.py` with `SMARTSHOT_WORKSPACE_ID` to prevent phantom 50/50 split boxes from background workspaces | M1 | Survey (R2) |
| 5 | Web Page Body Viewport Detection | Detect browser page content area below URL/tab bars using horizontal gradient demarcation in `detect_ui.py` | M1 | Survey (R2) |
| 6 | Adjacent Column Clustering | Synthesize adjacent column/sidebar panels into composite container unions (`cluster_adjacent_columns`) in `detect_ui.py` | M1 | Survey (R2) |
| 7 | Vision Unit Test Coverage | Comprehensive unit tests in `vision/test_detect_ui.py` verifying workspace filtering, column clustering, and browser body detection | M1 | Survey (R2) |
| 8 | Native Wayland Pin Window Script | Standalone `bin/hyprsmartshot-pin` with PySide6 (`class = "hyprsmartshot-pin"`) supporting frameless floating display and in-memory pixmap | M2 | Survey (R3) |
| 9 | Compositor Dragging & Resizing | Support `startSystemMove()` on left-click and native Hyprland Super+LMB / Super+RMB window manipulation | M2 | Survey (R3) |
| 10 | Pin Window Zoom & Shortcuts | Mouse scroll wheel zoom, `Ctrl+C` copy pixmap, `Esc`/`q` close, right/middle click close | M2 | Survey (R3) |
| 11 | QML Pin Button & Key Integration | Add `󰐃 Pin` button in `ActionPill.qml`, shortcut `P` in `shell.qml` and `SmartSelector.qml`, forward to `doPin` | M2 | Survey (R3) |
| 12 | Pin Localization & Config | Add `"pin"` translation key in `en.json`, `cs.json`, `tests/test_i18n.py`, and desktop/installer rules | M2 | Survey (R3) |
| 13 | Arch Release PKGBUILD | Create `packaging/arch/PKGBUILD` for tagged release packages with 11 core dependencies | M3 | Survey (R4) |
| 14 | Arch VCS PKGBUILD-git | Create `packaging/arch/PKGBUILD-git` with `pkgver()` tracking git describe | M3 | Survey (R4) |
| 15 | AUR .SRCINFO Generation | Automated generation of valid `.SRCINFO` templates via `makepkg --printsrcinfo` | M3 | Survey (R4) |
| 16 | XDG Desktop Entry | Create `packaging/arch/hyprsmartshot.desktop` validated with `desktop-file-validate` | M3 | Survey (R4) |
| 17 | Packaging CI Validation | Add PKGBUILD syntax and desktop file validation steps to `.github/workflows/ci.yml` | M3 | Survey (R4) |
| 18 | Subpixel Crop Endpoint Transform | Formulate `cx1 = round(x*s)`, `cx2 = round((x+w)*s)`, `cw = cx2 - cx1` in `shell.qml` eliminating 1px drift | M4 | Survey (R5) |
| 19 | Boundary Clamping & Crop Guard | Strict boundary clamping `[0, W_phys]` and `[0, H_phys]` preventing out-of-bounds crops or black borders | M4 | Survey (R5) |
| 20 | Multi-Monitor Coordinate Normalization | Offset client window coordinates by `(SMARTSHOT_MONITOR_X, SMARTSHOT_MONITOR_Y)` and scale in `detect_ui.py` | M4 | Survey (R5) |
| 21 | Fallback Grim Scale Parameter | Add `-s "$scale"` to fallback `grim -g` command avoiding highest-monitor scale pollution | M4 | Survey (R5) |
| 22 | CI Branch Pattern Fix | Update branch trigger pattern in `.github/workflows/ci.yml` to include `"feat/**"` | M4 | Survey (R6) |
| 23 | Full E2E & Remote CI Verification | Verify 100% test suite passing, all blocks committed to clean branches, merged to `main`, and pushed to remote | M5 | Survey (R6) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Urgent Fixes: Action Hanging & Browser Body | R1, R2: Register Config singleton in `qmldir`, wrap actions in `try/catch/finally`, implement `SMARTSHOT_WORKSPACE_ID` client filtering in `detect_ui.py`, verify column clustering and browser body detection, tests passing on branch `fix/action-hanging-and-browser-body` | none | DONE |
| M2 | Pin to Screen: Native Wayland Window | R3: `bin/hyprsmartshot-pin` with PySide6 XDG Toplevel, `startSystemMove()`, zoom, shortcuts, `ActionPill.qml` pin button, `shell.qml` shortcut `P`, i18n keys, installer updates on branch `feat/pin-to-screen` | M1 | IN_PROGRESS |
| M3 | AUR Packaging | R4: `packaging/arch/PKGBUILD`, `PKGBUILD-git`, `.SRCINFO`, `hyprsmartshot.desktop`, namcap/desktop-file-validate, packaging CI step on branch `feat/aur-packaging` | M2 | PLANNED |
| M4 | Wayland Multi-Monitor & Fractional Scaling | R5: Endpoint-difference transform (`cx2 - cx1`) in `shell.qml`, boundary clamping, `detect_ui.py` multi-monitor offset and coordinate normalization, grim `-s "$scale"`, CI branch trigger glob on branch `feat/wayland-scaling-and-monitors` | M3 | PLANNED |
| M5 | Final E2E Acceptance & Remote CI | R6: Full test suite execution across tests and vision, git merge to `origin/main`, CI matrix verification, Sentinel report | M4 | PLANNED |

## Interface Contracts

### QML Shell ↔ Action Handlers (`shell.qml`)
- `closeOverlay()` must be called in `finally` block of every action function (`doCopy`, `doSave`, `doAnnotate`, `doOcr`, `doPin`).
- `Config` access must use null-safe checking: `(typeof Config !== "undefined" && Config && Config.prop) ? Config.prop : fallback`.
- Shell commands executed through `Quickshell.execDetached` must pass arguments sanitized with `shellEscape(param)`.

### Environment ↔ CV Detector (`vision/detect_ui.py`)
- `SMARTSHOT_WORKSPACE_ID`: String or integer workspace ID. When present and non-empty, `detect_ui.py` retains client window `c` if `c.get("pinned") is True` or `str(c.get("workspace", {}).get("id")) == str(SMARTSHOT_WORKSPACE_ID)`.
- `SMARTSHOT_MONITOR_X`, `SMARTSHOT_MONITOR_Y`: Integer layout coordinates of target monitor. Subtracted from `c["at"]`.
- `SMARTSHOT_MONITOR_SCALE`: Float scaling factor. Multiplied by local client coordinates so bounding boxes in `boxes.json` match physical image pixels.

### CLI ↔ Pin Window (`bin/hyprsmartshot-pin`)
- Invocation: `hyprsmartshot-pin <path_to_cropped_image>`
- Window class: `hyprsmartshot-pin`
- Exit codes: 0 on normal close (Esc, q, click).

## Code Layout
- `bin/hyprsmartshot`: Main CLI launcher and Wayland snapshot orchestrator.
- `bin/hyprsmartshot-pin`: Standalone native Wayland floating/pinned image viewer.
- `components/`: Quickshell QML components (`qmldir`, `ActionPill.qml`, `Config.qml`, `ControlBar.qml`, `FreezeScreen.qml`, `I18n.qml`, `Magnifier.qml`, `SmartSelector.qml`, `Theme.qml`).
- `config/`: Default JSON and TOML configuration files.
- `localization/`: Translation files (`en.json`, `cs.json`).
- `packaging/arch/`: Arch Linux packaging specifications (`PKGBUILD`, `PKGBUILD-git`, `.SRCINFO`, `hyprsmartshot.desktop`).
- `shaders/`: GLSL shaders for overlay dimming.
- `tests/`: Python unit tests for CLI, config, i18n.
- `vision/`: OpenCV UI detection algorithms (`detect_ui.py`) and unit tests (`test_detect_ui.py`).
