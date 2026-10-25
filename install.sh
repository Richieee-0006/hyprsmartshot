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
if [ -f "$DIR/requirements.txt" ]; then
    "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt" >/dev/null
else
    "$DIR/.venv/bin/pip" install opencv-python-headless numpy >/dev/null
fi

# 2. Make runner executable
chmod +x "$DIR/bin/hyprsmartshot"
chmod +x "$DIR/vision/detect_ui.py"

# 3. Create symlink in ~/.local/bin
mkdir -p "$BIN_DIR"
ln -sf "$DIR/bin/hyprsmartshot" "$BIN_DIR/hyprsmartshot"

# 4. Satty configuration template
mkdir -p "$HOME/.config/satty"
if [ ! -f "$HOME/.config/satty/config.toml" ]; then
    echo "==> Installing default aesthetic Satty config..."
    cp "$DIR/config/satty/config.toml" "$HOME/.config/satty/config.toml"
fi

# 5. HyprSmartShot configuration template
CONFIG_DIR="$HOME/.config/hyprsmartshot"
mkdir -p "$CONFIG_DIR/localization"
if [ ! -f "$CONFIG_DIR/config.json" ] && [ ! -f "$CONFIG_DIR/config.toml" ]; then
    echo "==> Installing default HyprSmartShot config..."
    cp "$DIR/config/hyprsmartshot/config.json" "$CONFIG_DIR/config.json"
fi

echo ""
echo "✨ HyprSmartShot installed successfully!"
echo "   Binary linked to: $BIN_DIR/hyprsmartshot"
echo ""
echo "To bind in Hyprland Lua (e.g. ~/.config/hypr/modules/keybinds.lua):"
echo '  hl.bind("Print", hl.dsp.exec_cmd("hyprsmartshot universal"))'
echo '  hl.bind("SHIFT + Print", hl.dsp.exec_cmd("hyprsmartshot screen"))'
echo ""
