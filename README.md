# HyprSmartShot

[![Target](https://img.shields.io/badge/target-Hyprland_Wayland-89b4fa?style=flat-square&logo=wayland&logoColor=white)](https://hyprland.org)
[![Toolkit](https://img.shields.io/badge/toolkit-QuickShell_Qt6-a6e3a1?style=flat-square)](https://quickshell.org)
[![Vision](https://img.shields.io/badge/vision-OpenCV-f9e2af?style=flat-square&logo=opencv&logoColor=black)](https://opencv.org)
[![Palette](https://img.shields.io/badge/palette-Catppuccin_&_Pywal-cba6f7?style=flat-square)](https://github.com/dylanaraps/pywal)
[![CI](https://github.com/Richieee-0006/hyprsmartshot/actions/workflows/ci.yml/badge.svg)](https://github.com/Richieee-0006/hyprsmartshot/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

An ultra-smart, responsive screenshot and annotation utility crafted for **Hyprland** on Wayland. HyprSmartShot harnesses high-performance Computer Vision (OpenCV) to detect in-game interface panels, inventory grids, individual item slots, dialogue windows, and floating desktop overlays in real time.

---

## Features

| Feature | Description |
| :--- | :--- |
| **Game UI & Inventory Detection** | Sub-60ms OpenCV contour engine automatically detects square slots, rectangular rows, entire inventory grids (e.g. Minecraft, WoW, Diablo, Terraria), dialogue boxes, buttons, and ornate RPG frames down to 10×10 pixels. |
| **Hierarchical Wheel Zoom** | Seamlessly navigate UI nesting using the mouse scroll wheel (`Scroll Up / Down`) — drill down to a single item slot or zoom out to the containing grid row, full bag container, or game window. |
| **Instant Freezed Framebuffer** | Leverages `grim` to capture and hold a freeze-frame before spawning the overlay, preventing window-snapping stutter, cursor flicker, or moving elements from desyncing during selection. |
| **Floating Overlay Prioritization** | Automatically resolves Hyprland window stacking order: floating overlay dialogs and pinned windows take precedence over background tiled windows. |
| **Magnetic Snapping** | Freehand dragging magnetically snaps selection borders to detected UI bounds, window frames, and screen edges. |
| **Confirmation Mode & Controls** | Left-click locks the candidate selection into place, spawning a sleek floating action bar directly beneath the cursor with 8 resize handles for precise adjustments. |
| **Instant Annotation (Satty)** | Fully integrated with **Satty v0.22+** running as a centered, floating dialog with Catppuccin theme styling and brush smoothing. |
| **Optical Character Recognition** | Fast one-key OCR powered by `tesseract` (English & Czech preconfigured) with recognized text instantly copied to the Wayland clipboard. |
| **Pixel Magnifier** | Press `Alt` to toggle an ultra-sharp 4× pixel magnifier with cursor coordinate readouts. |

---

## Capture Modes

| Mode | Command | Description |
| :--- | :--- | :--- |
| **Smart / Universal (Default)** | `hyprsmartshot universal` | All-in-one detection combining Computer Vision UI analysis, Hyprland window boundaries, and freehand magnetic selection. |
| **Full Screen** | `hyprsmartshot screen` | Instant capture of the entire focused monitor. |

---

## Controls & Shortcuts

| Input | Action |
| :--- | :--- |
| **Mouse Hover** | Highlight and smoothly snap to detected game slots, UI elements, or windows |
| **Mouse Drag** | Freehand region selection with magnetic boundary snapping |
| **Mouse Wheel (Scroll)** | Cycle semantic hierarchy (e.g. `Item Slot` $\leftrightarrow$ `Grid Row` $\leftrightarrow$ `Bag Container` $\leftrightarrow$ `Game Window`) |
| **Left Click** | **Confirmation Mode**: Locks selection and displays action bar under cursor |
| **Enter / Double Click** | Copy selection to clipboard (`wl-copy`) and close overlay |
| **Ctrl + S** | Save image to `~/Pictures/Screenshots/` and copy to clipboard |
| **O** | Run OCR on selected region and copy recognized text to clipboard |
| **Alt** | Toggle pixel-level inspection magnifier |
| **Esc / Right Click** | Unlock confirmed selection / Cancel and close overlay |
| **1 / 2** | Switch active mode on the fly (`Smart` / `Screen`) |

---

## Dependencies & License Compatibility

HyprSmartShot is licensed under the permissive **[MIT License](LICENSE)**. Below is the complete dependency matrix and license compatibility analysis:

| Component | Role | Project License | Compatibility with MIT |
| :--- | :--- | :--- | :--- |
| **[QuickShell](https://quickshell.org)** | Wayland QML shell host | **LGPL-3.0** | **Fully Compatible**: HyprSmartShot scripts and QML are independent client code executed by the standalone `quickshell` runtime without modifying the QuickShell library itself. |
| **[OpenCV (Python)](https://opencv.org)** | Computer Vision contour engine | **Apache-2.0** | **Fully Compatible**: Apache 2.0 is a permissive license that explicitly permits sublicensing and integration into MIT-licensed projects. |
| **[NumPy](https://numpy.org)** | Matrix & array calculations | **BSD-3-Clause** | **Fully Compatible**: BSD-3-Clause permits incorporation into MIT projects provided copyright notices are preserved. |
| **[grim](https://gitlab.freedesktop.org/emersion/grim)** | Screen capture utility | **MIT** | **Fully Compatible**: Identical license terms. |
| **[slurp](https://github.com/emersion/slurp)** | Screen region selector | **MIT** | **Fully Compatible**: Identical license terms. |
| **[Satty](https://github.com/gabm/Satty)** | Screenshot annotation editor | **MPL-2.0** | **Fully Compatible**: Satty is executed as an external standalone CLI tool via process isolation (`sh -c`). Weak copyleft (MPL) does not apply to calling scripts. |
| **[Tesseract](https://github.com/tesseract-ocr/tesseract)** | OCR engine | **Apache-2.0** | **Fully Compatible**: Permissive Apache 2.0 license. |
| **[wl-clipboard](https://github.com/bugaevc/wl-clipboard)** | Wayland clipboard manager | **GPL-3.0-or-later**| **Fully Compatible**: Invoked as an external command-line utility (`wl-copy`). Subprocess CLI invocation does not constitute a derivative work under GPL terms. |
| **[Pywal](https://github.com/dylanaraps/pywal)** | Dynamic color generation | **MIT** | **Fully Compatible**: Identical license terms. |
| **[JetBrainsMono Nerd Font](https://www.nerdfonts.com)** | UI typography | **OFL-1.1** | **Fully Compatible**: Open Font License permits bundling and display. |

> [!NOTE]
> **Legal Compliance Guarantee**: All external CLI tools (`grim`, `slurp`, `satty`, `wl-copy`, `tesseract`) are decoupled through standard Wayland inter-process communication and POSIX shells. No proprietary or copyleft restrictions are imposed on user installations or derivative workflows.

---

## Installation

### 1. Prerequisites (Arch Linux / CachyOS)

Install core packages via `pacman`:

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
    python
```

### 2. Clone & Run Automated Setup

Clone the repository to your user data directory and run the installer:

```bash
git clone git@github.com:Richieee-0006/hyprsmartshot.git ~/.local/share/hyprsmartshot
cd ~/.local/share/hyprsmartshot
chmod +x install.sh
./install.sh
```

The installer automatically:
1. Creates an isolated Python virtual environment (`.venv`) and installs `opencv-python-headless` and `numpy`.
2. Creates a symlink in `~/.local/bin/hyprsmartshot`.
3. Installs the recommended Catppuccin Satty configuration into `~/.config/satty/config.toml` (if not already customized).

---

## Configuration

### Localization & Internationalization (i18n)

HyprSmartShot features a generic, dynamic internationalization architecture. While **English (`en`)** (default) and **Czech (`cs`)** are bundled out of the box as reference translations, **any arbitrary language code `{lang}`** (e.g., `de`, `fr`, `es`, `pl`, `ja`, etc.) is dynamically supported without requiring code changes.

#### Configuration

Language preference is resolved in the following priority order:
1. Environment variable: `SMARTSHOT_LANG` (e.g., `SMARTSHOT_LANG=de hyprsmartshot universal`)
2. User JSON config: `~/.config/hyprsmartshot/config.json`
3. User TOML config: `~/.config/hyprsmartshot/config.toml`
4. Bundled fallback: `config/hyprsmartshot/config.json` (defaults to `"en"`)

Example `~/.config/hyprsmartshot/config.json`:
```json
{
  "language": "en"
}
```

Example `~/.config/hyprsmartshot/config.toml`:
```toml
language = "en"
```

#### How Users Can Add or Customize Languages

You can easily add your own language or override existing phrases locally without touching repository files:

1. **Create the user localization folder**:
   ```bash
   mkdir -p ~/.config/hyprsmartshot/localization
   ```

2. **Copy the English reference template**:
   ```bash
   cp ~/.local/share/hyprsmartshot/localization/en.json ~/.config/hyprsmartshot/localization/<lang>.json
   # Example for German:
   cp ~/.local/share/hyprsmartshot/localization/en.json ~/.config/hyprsmartshot/localization/de.json
   ```

3. **Translate the values** in your new `<lang>.json` file.

4. **Activate the language**:
   Set `"language": "<lang>"` in `~/.config/hyprsmartshot/config.json` (or `language = "<lang>"` in `config.toml`), or test immediately:
   ```bash
   SMARTSHOT_LANG=de hyprsmartshot universal
   ```

#### Graceful Key Fallback

HyprSmartShot guarantees seamless partial translation support:
- If any key is missing in your custom or community language file, the system automatically falls back to `en.json` (and internal compiled defaults).
- Regional language tags (e.g. `cs_CZ` or `de_AT`) automatically fall back to the corresponding base language (`cs`, `de`) before falling back to English.
- Buttons and notifications will never disappear, break, or display blank labels.

#### Contributing a New Language (Community PRs Welcome!)

Community translations are warmly encouraged! To submit a new language upstream:

1. Add your language file `localization/<lang>.json` directly to the `localization/` directory (use `localization/en.json` as a reference).
2. Validate formatting and key parity with existing tests:
   ```bash
   python3 tests/test_i18n.py
   ```
3. Open a Pull Request!


### Hyprland Lua Configuration

Hyprland natively uses Lua scripting. Add the keybindings and window rules to your configuration (e.g., `~/.config/hypr/hyprland.lua` or under `~/.config/hypr/modules/`):

#### Keybindings (`modules/keybinds.lua`)
```lua
-- HyprSmartShot Keybindings
hl.bind("Print", hl.dsp.exec_cmd("hyprsmartshot universal"))
hl.bind("SHIFT + Print", hl.dsp.exec_cmd("hyprsmartshot screen"))
```

#### Satty Floating Window Rule (`modules/rules.lua`)
To ensure the Satty annotation editor opens as an aesthetic centered floating modal with ambient dimming:
```lua
hl.window_rule({
    match = { class = "^(com\\.gabm\\.satty|satty)$" },
    float = true,
    center = true,
    pin = true,
    stay_focused = true,
    dim_around = true,
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
```
</details>

---

## License

This project is licensed under the [MIT License](LICENSE).
Copyright © 2026 Richieee.
