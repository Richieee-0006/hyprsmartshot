# HyprSmartShot

Screenshot and annotation utility for Hyprland on Wayland using OpenCV to detect game UI panels, inventory grids, item slots, dialogue boxes, and floating windows.

## Key Features
- **OpenCV UI & Inventory Detection:** Detects game inventory grids, individual item slots, dialogue frames, and desktop windows in under 60ms.
- **Hierarchical Scroll Zoom:** Steps through nested UI levels (slot -> row -> container -> window) with the mouse wheel.
- **Frozen Framebuffer & Pinning:** Captures via `grim` before showing the overlay and supports pinning selections as floating Wayland windows.
- **Annotation & OCR:** Integrates Satty v0.22+ for editing and Tesseract (`eng+ces`) for copying text straight to the Wayland clipboard.

## Tech Stack
- **UI & Shell:** Quickshell (Qt6 / QML), PySide6, Bash
- **Vision & OCR:** Python, OpenCV, NumPy, Tesseract
- **Wayland Tools:** `grim`, `slurp`, `satty`, `wl-clipboard`, Hyprland
