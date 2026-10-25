#!/usr/bin/env python3
"""
HyprSmartShot Native Wayland Pin Window (Backwards Compatibility Wrapper)
Delegates execution to bin/hyprsmartshot-pin.
"""

import sys
import os
from importlib.machinery import SourceFileLoader

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN_PIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot-pin")

if os.path.isfile(BIN_PIN):
    if "hyprsmartshot_pin" in sys.modules:
        mod = sys.modules["hyprsmartshot_pin"]
    else:
        loader = SourceFileLoader("hyprsmartshot_pin", BIN_PIN)
        mod = loader.load_module()

    # Expose symbols for backward compatibility
    PinWindow = getattr(mod, "PinWindow", None)
    run_pyside6_viewer = getattr(mod, "run_pyside6_viewer", None)
    fallback_viewer = getattr(mod, "fallback_viewer", None)
    is_temporary_path = getattr(mod, "is_temporary_path", None)

    if __name__ == "__main__":
        sys.exit(mod.main("pin_window.py"))
else:
    print(f"Error: Pin binary not found at {BIN_PIN}", file=sys.stderr)
    sys.exit(1)
