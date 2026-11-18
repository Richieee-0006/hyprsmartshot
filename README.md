# HyprSmartShot

[![Release](https://img.shields.io/github/v/release/Richieee-0006/hyprsmartshot?style=flat-square&color=fab387)](https://github.com/Richieee-0006/hyprsmartshot/releases)
[![Target](https://img.shields.io/badge/target-Hyprland_Wayland-89b4fa?style=flat-square&logo=wayland&logoColor=white)](https://hyprland.org)
[![Toolkit](https://img.shields.io/badge/toolkit-QuickShell_Qt6-a6e3a1?style=flat-square)](https://quickshell.org)
[![Vision](https://img.shields.io/badge/vision-OpenCV-f9e2af?style=flat-square&logo=opencv&logoColor=black)](https://opencv.org)
[![Palette](https://img.shields.io/badge/palette-Catppuccin_&_Pywal-cba6f7?style=flat-square)](https://github.com/dylanaraps/pywal)
[![CI](https://github.com/Richieee-0006/hyprsmartshot/actions/workflows/ci.yml/badge.svg)](https://github.com/Richieee-0006/hyprsmartshot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

Screenshot and annotation tool for Hyprland on Wayland. Uses OpenCV to detect game inventory grids, item slots, dialogue windows, and floating overlays.

## Features

| Feature | Description |
| :--- | :--- |
| **Game UI & Inventory Detection** | OpenCV contour engine (<60ms) detects square slots, rows, inventory grids (Minecraft, WoW, Diablo, Terraria), dialogue boxes, buttons, and RPG frames down to 10×10 px. |
| **Hierarchical Wheel Zoom** | Scroll Up/Down steps between nested UI elements: item slot, grid row, bag container, and game window. |
| **Frozen Framebuffer** | Captures the screen with `grim` before opening the overlay so moving elements stay still during selection. |
| **Floating Overlay Prioritization** | Respects Hyprland stacking order so floating dialogs and pinned windows take precedence over tiled windows behind them. |
| **Magnetic Snapping** | Freehand dragging snaps selection edges to detected UI bounds, window frames, and monitor edges. |
| **Confirmation Mode & Controls** | Left-click locks the selection and shows an action bar with 8 resize handles. |
| **Annotation (Satty)** | Opens the selection in Satty v0.22+ as a centered floating window with Catppuccin styling. |
| **OCR** | Runs `tesseract` (English & Czech preconfigured) on the selection and copies recognized text to the Wayland clipboard. |
| **Pixel Magnifier** | `Alt` toggles a 4× pixel magnifier with cursor coordinate readouts. |

## Capture Modes

| Mode | Command | Description |
| :--- | :--- | :--- |
| **Smart / Universal (Default)** | `hyprsmartshot universal` | Combines OpenCV UI detection, Hyprland window bounds, and freehand magnetic selection. |
| **Full Screen** | `hyprsmartshot screen` | Interactive overlay across the focused monitor. |
| **Fast Fullscreen** | `hyprsmartshot full` | Non-interactive capture of the focused monitor directly to disk and clipboard. |
| **Pin to Screen** | `hyprsmartshot pin <image> [x] [y] [w] [h]` | Displays an image in a floating, pinned Wayland window. |

## Controls & Shortcuts

| Input | Action |
| :--- | :--- |
| **Mouse Hover** | Highlight and snap to detected game slots, UI elements, or windows |
| **Mouse Drag** | Freehand region selection with magnetic snapping |
| **Mouse Wheel (Scroll)** | Cycle semantic hierarchy (`Item Slot` $\leftrightarrow$ `Grid Row` $\leftrightarrow$ `Bag Container` $\leftrightarrow$ `Game Window`) |
| **Left Click** | Lock selection and show action bar under cursor |
| **Enter / Double Click** | Copy selection to clipboard (`wl-copy`) and close overlay |
| **Ctrl + S** | Save image to `~/Pictures/Screenshots/` and copy to clipboard |
| **P** | Open selection in a floating, draggable, zoomable Wayland window |
| **A / E** | Open selection in Satty |
| **O** | Run OCR on selected region and copy text to clipboard |
| **Alt** | Toggle 4× pixel magnifier |
| **Esc / Right Click** | Unlock confirmed selection or cancel and close overlay |
| **1 / 2** | Switch active mode (`Smart` / `Screen`) |

## Dependencies & License Compatibility

HyprSmartShot is licensed under the [MIT License](LICENSE). External CLI tools (`grim`, `slurp`, `satty`, `wl-copy`, `tesseract`) run in separate subprocesses.

| Component | Role | License |
| :--- | :--- | :--- |
| **[QuickShell](https://quickshell.org)** | Wayland QML shell host | LGPL-3.0 |
| **[OpenCV (Python)](https://opencv.org)** | Computer Vision contour engine | Apache-2.0 |
| **[NumPy](https://numpy.org)** | Matrix & array calculations | BSD-3-Clause |
| **[PySide6 (Qt6)](https://wiki.qt.io/Qt_for_Python)** | Pin window viewer (falls back to `swayimg`, `imv`, `feh`) | LGPL-3.0 |
| **[grim](https://gitlab.freedesktop.org/emersion/grim)** | Screen capture | MIT |
| **[slurp](https://github.com/emersion/slurp)** | Region selector | MIT |
| **[Satty](https://github.com/gabm/Satty)** | Annotation editor | MPL-2.0 |
| **[Tesseract](https://github.com/tesseract-ocr/tesseract)** | OCR engine | Apache-2.0 |
| **[wl-clipboard](https://github.com/bugaevc/wl-clipboard)** | Wayland clipboard utility | GPL-3.0-or-later |
| **[Pywal](https://github.com/dylanaraps/pywal)** | Dynamic color generation | MIT |
| **[JetBrainsMono Nerd Font](https://www.nerdfonts.com)** | UI typography | OFL-1.1 |

## Installation

### 1. Prerequisites (Arch Linux / CachyOS)

```bash
sudo pacman -S --needed \
    quickshell-git \
    grim \
    slurp \
    satty \
    tesseract \
    tesseract-data-eng \
    tesseract-data-ces \
    wl-clipboard \
    libnotify \
    python \
    python-pyside6
```

### 2. Clone & Run Setup

```bash
git clone git@github.com:Richieee-0006/hyprsmartshot.git ~/.local/share/hyprsmartshot
cd ~/.local/share/hyprsmartshot
chmod +x install.sh
./install.sh
```

The installer:
1. Creates `.venv` and installs `opencv-python-headless` and `numpy`.
2. Symlinks `~/.local/bin/hyprsmartshot`.
3. Installs the Catppuccin Satty config into `~/.config/satty/config.toml` if none exists.

## Configuration

Configuration lives at `~/.config/hyprsmartshot/config.json`:

```json
{
  "language": "en",
  "ocrLanguages": "eng+ces",
  "postSaveHook": "oxipng -o 4 {path}",
  "postCopyHook": ""
}
```

| Key | Default | Description |
|---|---|---|
| `language` | `"en"` | Interface and notification language (`en`, `cs`, or custom code) |
| `ocrLanguages` | `"eng+ces"` | Tesseract OCR language string (e.g. `eng`, `eng+ces`, `deu+eng`) |
| `postSaveHook` | `""` | Shell command run after saving (`{path}` = saved file path) |
| `postCopyHook` | `""` | Shell command run after copying (`{path}` = temporary file path) |

Language preference resolves in order:
1. `SMARTSHOT_LANG` environment variable (e.g. `SMARTSHOT_LANG=de hyprsmartshot universal`)
2. `~/.config/hyprsmartshot/config.json`
3. `config/hyprsmartshot/config.json` (defaults to `"en"`)

### Localization (i18n)

English (`en`) and Czech (`cs`) are bundled. Any custom language code `{lang}` works without code changes; missing keys fall back from regional tag (e.g. `cs_CZ` -> `cs`) to `en.json`.

To add a local translation:

```bash
scripts/localization_template.py de --user
```

Edit `~/.config/hyprsmartshot/localization/de.json`, then set `"language": "de"` in `config.json` or pass `SMARTSHOT_LANG=de`.

To submit a translation upstream:

```bash
scripts/localization_template.py <lang>   # or --empty for blank values
scripts/localization_template.py --check <lang>
```

### Hyprland Lua Configuration

Add keybindings and window rules to `~/.config/hypr/hyprland.lua` or `~/.config/hypr/modules/`:

#### Keybindings (`modules/keybinds.lua`)
```lua
-- HyprSmartShot Keybindings
hl.bind("Print", hl.dsp.exec_cmd("hyprsmartshot universal"))
hl.bind("SHIFT + Print", hl.dsp.exec_cmd("hyprsmartshot screen"))
```

#### Satty & Pinned Window Rules (`modules/rules.lua`)
```lua
-- Satty Annotation Editor
hl.window_rule({
    match = { class = "^(com\\.gabm\\.satty|satty)$" },
    float = true,
    center = true,
    pin = true,
    stay_focused = true,
    dim_around = true,
})

-- HyprSmartShot Native Pinned Window (Always-on-top, draggable, zoomable)
hl.window_rule({
    match = { class = "^(hyprsmartshot-pin)$" },
    float = true,
    pin = true,
    keep_aspect_ratio = true,
})
```

<details>
<summary>Legacy <code>hyprland.conf</code> syntax (for older Hyprland versions)</summary>

```ini
# Keybindings
bind = , Print, exec, hyprsmartshot universal
bind = SHIFT, Print, exec, hyprsmartshot screen

# Window rules
windowrulev2 = float, class:^(com\.gabm\.satty|satty)$
windowrulev2 = center, class:^(com\.gabm\.satty|satty)$
windowrulev2 = pin, class:^(com\.gabm\.satty|satty)$
windowrulev2 = dimaround, class:^(com\.gabm\.satty|satty)$

# HyprSmartShot Pin Window
windowrulev2 = float, class:^(hyprsmartshot-pin)$
windowrulev2 = pin, class:^(hyprsmartshot-pin)$
windowrulev2 = keepaspectratio, class:^(hyprsmartshot-pin)$
```
</details>

## License

[MIT License](LICENSE) — Copyright © 2026 Richieee.
