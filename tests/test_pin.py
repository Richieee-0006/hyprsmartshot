#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot Native Wayland Pin Window (bin/hyprsmartshot-pin).
Verifies:
- CLI argument verification, --help and --version flags
- Standalone execution permissions and shebang
- Headless PySide6 window initialization and QPixmap loading (QT_QPA_PLATFORM=offscreen)
- Zero temp-file accumulation (immediate disk deletion after memory load)
- Zoom scaling preservation and bounds [0.2, 6.0]
- Keyboard shortcuts (Esc, q, +, -, 0, Ctrl+C)
- Mouse interactions (wheel zoom, double-click reset, right/middle click close)
- In-memory clipboard copy operations
"""

import os
import sys
import tempfile
import subprocess
import unittest
from importlib.machinery import SourceFileLoader
import importlib.util

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PIN_BIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot-pin")
RUNNER_BIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot")

try:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import Qt, QPoint, QPointF
    from PySide6.QtGui import QPixmap, QColor, QKeyEvent, QMouseEvent, QWheelEvent, QKeySequence
    from PySide6.QtWidgets import QApplication, QWidget
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


class TestPinCLI(unittest.TestCase):
    """Test CLI arguments, flags, and executable metadata for bin/hyprsmartshot-pin."""

    def test_pin_script_exists_and_executable(self):
        self.assertTrue(os.path.isfile(PIN_BIN), f"Missing {PIN_BIN}")
        self.assertTrue(os.access(PIN_BIN, os.X_OK), f"{PIN_BIN} must be executable (chmod +x)")
        with open(PIN_BIN, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        self.assertTrue(first_line.startswith("#!/usr/bin/env python3"), f"Invalid shebang: {first_line}")

    def test_help_flag_long(self):
        proc = subprocess.run([PIN_BIN, "--help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage:", proc.stdout)
        self.assertIn("hyprsmartshot-pin", proc.stdout)

    def test_help_flag_short(self):
        proc = subprocess.run([PIN_BIN, "-h"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage:", proc.stdout)

    def test_version_flag_long(self):
        proc = subprocess.run([PIN_BIN, "--version"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hyprsmartshot-pin v0.0.1", proc.stdout)

    def test_version_flag_short(self):
        proc = subprocess.run([PIN_BIN, "-v"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hyprsmartshot-pin v0.0.1", proc.stdout)

    def test_missing_argument_error(self):
        proc = subprocess.run([PIN_BIN], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Usage: hyprsmartshot-pin", proc.stderr)

    def test_nonexistent_image_error(self):
        proc = subprocess.run([PIN_BIN, "/tmp/nonexistent_pin_image_99999.png"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Image not found:", proc.stderr)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for PinWindow unit tests")
class TestPinWindowUnit(unittest.TestCase):
    """Unit tests for PinWindow GUI logic, lifecycle, and memory management."""

    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication(["hyprsmartshot-pin"])

    def _create_test_image(self, width=120, height=80, color=QColor(0, 180, 255)):
        tmp = tempfile.NamedTemporaryFile(prefix="hyprsmartshot_pin_test_", suffix=".png", delete=False)
        tmp.close()
        pix = QPixmap(width, height)
        pix.fill(color)
        pix.save(tmp.name, "PNG")
        return tmp.name

    def _load_pin_module(self):
        loader = SourceFileLoader("hyprsmartshot_pin", PIN_BIN)
        spec = importlib.util.spec_from_file_location("hyprsmartshot_pin", PIN_BIN, loader=loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def test_window_initialization_and_pixmap_loaded(self):
        mod = self._load_pin_module()
        img_path = self._create_test_image(140, 90)

        try:
            win = mod.PinWindow(img_path, x=50, y=60, w=140, h=90, should_delete=False)
            self.assertFalse(win.orig_pixmap.isNull(), "QPixmap must not be null")
            self.assertEqual(win.orig_pixmap.width(), 140)
            self.assertEqual(win.orig_pixmap.height(), 90)
            self.assertEqual(win.width(), 140)
            self.assertEqual(win.height(), 90)

            # Wayland frameless, stay-on-top, and window type flags
            flags = win.windowFlags()
            self.assertTrue(flags & Qt.WindowType.FramelessWindowHint, "Must be frameless")
            self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint, "Must stay on top")
            self.assertEqual(win.objectName(), "hyprsmartshot-pin")
            win.close()
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_temporary_file_deleted_from_disk_after_loading(self):
        mod = self._load_pin_module()
        # Create temp crop file matching HyprSmartShot temp prefix
        tmp_crop = tempfile.NamedTemporaryFile(prefix="hyprsmartshot_pin_", suffix=".png", delete=False)
        tmp_crop.close()
        pix = QPixmap(100, 60)
        pix.fill(QColor(255, 100, 50))
        pix.save(tmp_crop.name, "PNG")

        self.assertTrue(os.path.isfile(tmp_crop.name), "Temp file must exist before loading")

        win = mod.PinWindow(tmp_crop.name)
        try:
            # Memory contents are valid
            self.assertFalse(win.orig_pixmap.isNull())
            self.assertTrue(hasattr(win, "image_bytes") and len(win.image_bytes) > 0,
                            "Window must preserve raw image bytes in memory")

            # Temporary file must be unlinked from disk
            self.assertFalse(os.path.exists(tmp_crop.name),
                             f"Temporary crop {tmp_crop.name} must be deleted from disk immediately after loading")
        finally:
            win.close()
            if os.path.exists(tmp_crop.name):
                os.remove(tmp_crop.name)

    def test_keep_flag_preserves_file(self):
        mod = self._load_pin_module()
        tmp_crop = tempfile.NamedTemporaryFile(prefix="hyprsmartshot_pin_keep_", suffix=".png", delete=False)
        tmp_crop.close()
        pix = QPixmap(80, 50)
        pix.fill(QColor(50, 200, 100))
        pix.save(tmp_crop.name, "PNG")

        win = mod.PinWindow(tmp_crop.name, should_delete=False)
        try:
            self.assertTrue(os.path.exists(tmp_crop.name), "should_delete=False must preserve the file")
        finally:
            win.close()
            if os.path.exists(tmp_crop.name):
                os.remove(tmp_crop.name)

    def test_zoom_scaling_and_boundaries(self):
        mod = self._load_pin_module()
        img_path = self._create_test_image(100, 100)
        try:
            win = mod.PinWindow(img_path, should_delete=False)
            self.assertEqual(win.scale_factor, 1.0)

            # Test scale bounds
            self.assertEqual(win.min_scale, 0.2)
            self.assertEqual(win.max_scale, 6.0)

            # Zoom in keyboard shortcut '+'
            event_plus = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier, "+")
            win.keyPressEvent(event_plus)
            self.assertGreater(win.scale_factor, 1.0)

            # Reset zoom '0'
            event_zero = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier, "0")
            win.keyPressEvent(event_zero)
            self.assertEqual(win.scale_factor, 1.0)

            # Zoom out keyboard shortcut '-'
            event_minus = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Minus, Qt.KeyboardModifier.NoModifier, "-")
            win.keyPressEvent(event_minus)
            self.assertLess(win.scale_factor, 1.0)

            # Test min_scale enforcement
            win.set_zoom(0.01)
            self.assertAlmostEqual(win.scale_factor, 0.2)

            # Test max_scale enforcement
            win.set_zoom(10.0)
            self.assertAlmostEqual(win.scale_factor, 6.0)

            win.close()
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_wheel_zoom(self):
        mod = self._load_pin_module()
        img_path = self._create_test_image(100, 100)
        try:
            win = mod.PinWindow(img_path, should_delete=False)
            initial_scale = win.scale_factor

            # Wheel zoom in (positive delta)
            wheel_in = QWheelEvent(
                QPointF(50, 50),
                QPointF(50, 50),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False
            )
            win.wheelEvent(wheel_in)
            self.assertGreater(win.scale_factor, initial_scale)

            # Wheel zoom out (negative delta)
            wheel_out = QWheelEvent(
                QPointF(50, 50),
                QPointF(50, 50),
                QPoint(0, 0),
                QPoint(0, -240),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False
            )
            win.wheelEvent(wheel_out)
            self.assertLess(win.scale_factor, 1.15)

            win.close()
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_mouse_double_click_reset_zoom(self):
        mod = self._load_pin_module()
        img_path = self._create_test_image(100, 100)
        try:
            win = mod.PinWindow(img_path, should_delete=False)
            win.set_zoom(2.5)
            self.assertAlmostEqual(win.scale_factor, 2.5)

            # Double click reset
            dbl_click = QMouseEvent(
                QMouseEvent.Type.MouseButtonDblClick,
                QPointF(50, 50),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier
            )
            win.mouseDoubleClickEvent(dbl_click)
            self.assertAlmostEqual(win.scale_factor, 1.0)
            win.close()
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_keyboard_close_shortcuts(self):
        mod = self._load_pin_module()
        img_path = self._create_test_image(100, 100)
        try:
            # Esc key
            win_esc = mod.PinWindow(img_path, should_delete=False)
            win_esc.show()
            event_esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            win_esc.keyPressEvent(event_esc)
            self.assertFalse(win_esc.isVisible())
            win_esc.close()

            # Q key
            win_q = mod.PinWindow(img_path, should_delete=False)
            win_q.show()
            event_q = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.NoModifier, "q")
            win_q.keyPressEvent(event_q)
            self.assertFalse(win_q.isVisible())
            win_q.close()
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_mouse_close_shortcuts(self):
        mod = self._load_pin_module()
        img_path = self._create_test_image(100, 100)
        try:
            # Right-click close
            win_r = mod.PinWindow(img_path, should_delete=False)
            win_r.show()
            m_right = QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(10, 10),
                Qt.MouseButton.RightButton,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier
            )
            win_r.mousePressEvent(m_right)
            self.assertFalse(win_r.isVisible())
            win_r.close()

            # Middle-click close
            win_m = mod.PinWindow(img_path, should_delete=False)
            win_m.show()
            m_mid = QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(10, 10),
                Qt.MouseButton.MiddleButton,
                Qt.MouseButton.MiddleButton,
                Qt.KeyboardModifier.NoModifier
            )
            win_m.mousePressEvent(m_mid)
            self.assertFalse(win_m.isVisible())
            win_m.close()
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_in_memory_clipboard_copy(self):
        mod = self._load_pin_module()
        img_path = self._create_test_image(64, 64)
        try:
            win = mod.PinWindow(img_path, should_delete=False)
            # Ensure copy_to_clipboard executes without errors even if disk file is removed
            if os.path.exists(img_path):
                os.remove(img_path)
            win.copy_to_clipboard()
            # Verify clipboard received pixmap
            cb = QApplication.clipboard()
            self.assertFalse(cb.pixmap().isNull(), "Clipboard must contain valid pixmap after copy_to_clipboard()")
            win.close()
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)


if __name__ == "__main__":
    unittest.main()
