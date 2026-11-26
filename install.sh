#!/usr/bin/env bash
# HyprSmartShot v2 Installer
# Builds and installs the native C++23 standalone package (with daemon + on-demand settings),
# falling back cleanly to legacy script symlinks when C++ build dependencies are unavailable.

set -e

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SOURCE" ]; do
    SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="${BIN_DIR:-$PREFIX/bin}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
SYSTEMD_USER_DIR="$CONFIG_HOME/systemd/user"

has_native_toolchain() {
    command -v cmake >/dev/null 2>&1 &&
    command -v ninja >/dev/null 2>&1 &&
    command -v wayland-scanner >/dev/null 2>&1 &&
    pkg-config --exists wayland-client cairo pangocairo xkbcommon libpng libjpeg libcurl 2>/dev/null
}

NATIVE_BUILT=0
if [ "${HSS_LEGACY:-0}" != "1" ] && has_native_toolchain; then
    echo "==> Building HyprSmartShot (native C++23) in $DIR..."
    cmake -S "$DIR" -B "$DIR/build" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DENABLE_TESTS=OFF \
        -DBUILD_SETTINGS_GUI=ON >/dev/null
    cmake --build "$DIR/build" -j"$(nproc)" >/dev/null
    NATIVE_BUILT=1
fi

mkdir -p "$BIN_DIR"

if [ "$NATIVE_BUILT" = "1" ] && [ -x "$DIR/build/hyprsmartshot" ]; then
    # Install shared vision plugin & systemd unit under PREFIX
    LIB_DIR="$PREFIX/lib/hyprsmartshot"
    mkdir -p "$LIB_DIR"
    cp -f "$DIR/build/libhss_vision.so" "$LIB_DIR/libhss_vision.so"

    ln -sf "$DIR/build/hyprsmartshot" "$BIN_DIR/hyprsmartshot"
    ln -sf "$DIR/build/hyprsmartshot" "$BIN_DIR/hyprsmartshot-pin"
    if [ -x "$DIR/build/hyprsmartshot-settings" ]; then
        ln -sf "$DIR/build/hyprsmartshot-settings" "$BIN_DIR/hyprsmartshot-settings"
    fi

    if [ -f "$DIR/packaging/systemd/hyprsmartshot.service" ]; then
        mkdir -p "$SYSTEMD_USER_DIR"
        sed "s|/usr/bin/hyprsmartshot|$BIN_DIR/hyprsmartshot|g" \
            "$DIR/packaging/systemd/hyprsmartshot.service" \
            > "$SYSTEMD_USER_DIR/hyprsmartshot.service"
    fi
else
    # Fallback symlinks (e.g. minimal Python-only environment without C++ dev headers)
    chmod +x "$DIR/bin/hyprsmartshot" "$DIR/bin/hyprsmartshot-pin" 2>/dev/null || true
    ln -sf "$DIR/bin/hyprsmartshot" "$BIN_DIR/hyprsmartshot"
    ln -sf "$DIR/bin/hyprsmartshot-pin" "$BIN_DIR/hyprsmartshot-pin"
fi

# Satty configuration template
mkdir -p "$CONFIG_HOME/satty"
if [ ! -f "$CONFIG_HOME/satty/config.toml" ] && [ -f "$DIR/config/satty/config.toml" ]; then
    cp "$DIR/config/satty/config.toml" "$CONFIG_HOME/satty/config.toml"
fi

# HyprSmartShot configuration template
CONFIG_DIR="$CONFIG_HOME/hyprsmartshot"
mkdir -p "$CONFIG_DIR/localization"
if [ ! -f "$CONFIG_DIR/config.json" ] && [ -f "$DIR/config/hyprsmartshot/config.json" ]; then
    cp "$DIR/config/hyprsmartshot/config.json" "$CONFIG_DIR/config.json"
fi

echo ""
echo "HyprSmartShot installed successfully!"
echo "   Binary linked to: $BIN_DIR/hyprsmartshot"
echo "   Pin linked to:    $BIN_DIR/hyprsmartshot-pin"
if [ "$NATIVE_BUILT" = "1" ]; then
    echo "   Settings GUI:     $BIN_DIR/hyprsmartshot-settings"
    echo "   Vision plugin:    $PREFIX/lib/hyprsmartshot/libhss_vision.so"
    echo "   Optional daemon:  systemctl --user daemon-reload && systemctl --user enable --now hyprsmartshot.service"
fi
