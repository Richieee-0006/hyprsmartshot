# 📸 HyprSmartShot

[![Hyprland](https://img.shields.io/badge/Hyprland-Optimized-00a4a6?style=for-the-badge&logo=archlinux&logoColor=white)](https://hyprland.org)
[![Wayland](https://img.shields.io/badge/Wayland-Native-blue?style=for-the-badge&logo=wayland&logoColor=white)](https://wayland.freedesktop.org)
[![Quickshell](https://img.shields.io/badge/QuickShell-v0.3.2+-41cd52?style=for-the-badge&logo=qt&logoColor=white)](https://quickshell.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer_Vision-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

An **ultra-smart, aesthetic screenshot utility** for [Hyprland](https://hyprland.org) and Wayland compositors. 

HyprSmartShot combines a polished desktop overlay interface (inspired by modern Wayland shells, featuring smooth spring physics, fragment shaders, and pywal theming) with an ultra-fast **Computer Vision engine (OpenCV)** that automatically recognizes **in-game UI interfaces, inventories, slot grids, dialogue boxes, menus, and application windows**.

---

## ✨ Features

- 🎮 **Smart Game UI & Panel Detection**:
  - Automatically identifies rectangular and curved UI frames, game inventories, equipment grids, healthbars, toolbars, and dialogue windows.
  - Sub-60ms CV processing runs seamlessly in the background during the screen freeze animation.
- 🔄 **Hierarchical Zoom (Scroll Wheel)**:
  - Effortlessly cycle through nested UI levels:  
    *Individual Item Slot* $\leftrightarrow$ *Inventory Bag Grid* $\leftrightarrow$ *Full Character Menu* $\leftrightarrow$ *Entire Game Window*.
- 📐 **Universal Magnetic Snapping**:
  - Freehand region drag magnetically snaps corners and edges to high-contrast UI borders.
- 🪟 **Multi-Mode Control Bar**:
  - **Universal**: In-game UI + Hyprland windows + freehand selection.
  - **Window**: Direct Hyprland client snapping.
  - **Region**: Freehand rectangular cropping with edge guides.
  - **Screen**: Fullscreen snapshot.
- 🎨 **Modern Wayland UI**:
  - Hardware accelerated fragment shader for smooth rounded cutouts and backdrop dimming.
  - Dynamic color scheme integration with `pywal` (`~/.cache/wal/colors.json`).
  - Spring-damped physics on highlight boxes and pill selectors.
- 📋 **Integrated Action Palette**:
  - **Copy**: Instant clipboard capture (`wl-copy`).
  - **Save**: File export to `~/Pictures/Screenshots/`.
  - **OCR**: In-place text recognition (`tesseract`) to clipboard.
  - **Magnifier**: Real-time pixel loupe with RGB hex display.

---

## ⌨️ Controls & Keybindings

| Key / Gesture | Action |
| :--- | :--- |
| **Mouse Hover** | Automatically snaps to nearest in-game panel, slot, or window |
| **Scroll Wheel** | Drill down or expand hierarchy level (*Slot $\leftrightarrow$ Bag $\leftrightarrow$ Window*) |
| **Left Click** | Locks selection in **Confirmation Mode** |
| **Double Click / Enter** | Confirms & copies selection to clipboard and exits |
| **Ctrl + S** | Confirms & saves screenshot to `~/Pictures/Screenshots/` |
| **O** | Runs OCR on selection and copies recognized text |
| **Alt** | Toggles pixel-zoom magnifier loupe |
| **Right Click / Esc** | Unlocks selection / cancels and closes overlay |
| **1 / 2 / 3 / 4** | Switches modes (*Universal / Window / Region / Screen*) |

---

## 🚀 Installation

### 1. Requirements

Ensure the following tools are available on your system:
- `hyprland` (Wayland compositor)
- `quickshell` (v0.2+ / v0.3+)
- `grim` & `wl-clipboard`
- `python3` (with `venv` module)
- `tesseract` (optional, for OCR)

### 2. Clone & Setup

```bash
# Clone into your local directory
git clone https://github.com/Richieee-0006/hyprsmartshot.git ~/.local/share/hyprsmartshot

# Run installer
cd ~/.local/share/hyprsmartshot
./install.sh
```

### 3. Hyprland Configuration

Add these keybindings to your `~/.config/hypr/hyprland.conf`:

```ini
# HyprSmartShot Binds
bind = , Print, exec, hyprsmartshot universal
bind = SHIFT, Print, exec, hyprsmartshot full
bind = CTRL, Print, exec, hyprsmartshot window
```

---

## 🛠️ Project Structure

```
~/.local/share/hyprsmartshot/
├── bin/
│   └── hyprsmartshot        # Shell runner & freeze pipeline
├── components/
│   ├── ActionPill.qml       # Confirmation action palette
│   ├── ControlBar.qml       # Top floating mode switcher
│   ├── FreezeScreen.qml     # Wayland layer-shell overlay
│   ├── Magnifier.qml        # Pixel loupe & color inspection
│   ├── SmartSelector.qml    # Spring-animated selection canvas
│   └── Theme.qml            # Pywal colors & typography
├── shaders/
│   ├── dimming.frag         # Fragment shader source
│   └── dimming.frag.qsb     # Qt precompiled shader
├── vision/
│   └── detect_ui.py         # OpenCV hierarchical contour engine
├── install.sh               # One-click environment installer
├── shell.qml                # Quickshell entrypoint
└── README.md
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
