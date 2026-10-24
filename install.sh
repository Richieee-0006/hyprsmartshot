#!/usr/bin/env bash
# HyprSmartShot Installer
# Sets up Python virtual environment, dependencies, and symlinks

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

echo "==> Setting up HyprSmartShot in $DIR..."

# 1. Ensure Python venv and dependencies
mkdir -p "$DIR/vision"
if [ ! -d "$DIR/.venv" ]; then
    echo "==> Creating Python virtual environment..."
    python3 -m venv "$DIR/.venv"
fi

echo "==> Installing Python dependencies (OpenCV, NumPy)..."
"$DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$DIR/.venv/bin/pip" install opencv-python-headless numpy >/dev/null

# 2. Make runner executable
chmod +x "$DIR/bin/hyprsmartshot"
chmod +x "$DIR/vision/detect_ui.py"

# 3. Create symlink in ~/.local/bin
mkdir -p "$BIN_DIR"
ln -sf "$DIR/bin/hyprsmartshot" "$BIN_DIR/hyprsmartshot"

echo ""
echo "✨ HyprSmartShot installed successfully!"
echo "   Binary linked to: $BIN_DIR/hyprsmartshot"
echo ""
echo "To bind in Hyprland, add to ~/.config/hypr/hyprland.conf:"
echo '  bind = , Print, exec, hyprsmartshot universal'
echo '  bind = SHIFT, Print, exec, hyprsmartshot full'
echo '  bind = CTRL, Print, exec, hyprsmartshot window'
echo ""
