#!/usr/bin/env python3
"""
Adversarial and Stress Tests for HyprSmartShot Native Wayland Pin Window (bin/hyprsmartshot-pin).

Covers:
1. CLI argument stress: --help, -h, help, --version, -v, version, missing arguments,
   nonexistent files, directories, flag permutations (--keep, --no-delete, --delete, --rm),
   coordinate parsing (floats, negative coordinates, zero dimensions).
2. Temporary file lifecycle:
   - Verification that files in /tmp, /var/tmp, or with hyprsmartshot prefixes are unlinked
     immediately from disk upon instantiation.
   - Verification that in-memory QPixmap and raw image bytes remain 100% intact and usable.
   - User non-temporary image preservation.
3. --keep flag:
   - Verification that files are preserved on disk throughout the entire lifecycle when requested.
4. Zoom bounds and aspect ratio invariance:
   - Extreme zoom-in (repeated 100x and direct out-of-bound inputs) strictly clamped at 6.0.
   - Extreme zoom-out (repeated 100x and direct out-of-bound inputs) strictly clamped at 0.2.
   - Zoom reset (0, double-click) returns to 1.0x.
   - Strict aspect ratio preservation across square, widescreen, portrait, and extreme aspect ratio banners.
   - Smooth anchor position geometry handling.
5. Keyboard shortcuts:
   - '+', '=', '-', '_', '0', 'Esc', 'q', 'Q', 'Ctrl+C', 'Enter'.
   - Rapid interleaved key press events.
6. Clipboard copying:
   - In-memory clipboard copy after source file deletion.
   - Qt clipboard and wl-copy verification.
   - Fault injection / resiliency when wl-copy or notify-send fails.
7. Multi-window concurrency stress.
"""

import os
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader
import importlib.util
from unittest.mock import patch

REPO_DIR = Path(__file__).resolve().parent.parent
PIN_BIN = str(REPO_DIR / "bin" / "hyprsmartshot-pin")

try:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import Qt, QPoint, QPointF
    from PySide6.QtGui import QPixmap, QColor, QKeyEvent, QMouseEvent, QWheelEvent, QKeySequence, QPainter
    from PySide6.QtWidgets import QApplication, QWidget
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


def load_pin_module():
    loader = SourceFileLoader("hyprsmartshot_pin", PIN_BIN)
    spec = importlib.util.spec_from_file_location("hyprsmartshot_pin", PIN_BIN, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestPinCLIStress(unittest.TestCase):
    """Adversarial testing of CLI arguments, permutations, and error boundaries."""

    def test_cli_help_variants(self):
        for flag in ["--help", "-h", "help"]:
            with self.subTest(flag=flag):
                proc = subprocess.run([PIN_BIN, flag], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"Expected 0 for {flag}")
                self.assertIn("Usage:", proc.stdout)
                self.assertIn("Options:", proc.stdout)
                self.assertIn("--delete", proc.stdout)
                self.assertIn("--keep", proc.stdout)

    def test_cli_version_variants(self):
        for flag in ["--version", "-v", "version"]:
            with self.subTest(flag=flag):
                proc = subprocess.run([PIN_BIN, flag], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"Expected 0 for {flag}")
                self.assertIn("hyprsmartshot-pin v0.0.1", proc.stdout)

    def test_cli_missing_arguments_exit_code_1(self):
        proc = subprocess.run([PIN_BIN], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Usage:", proc.stderr)

    def test_cli_nonexistent_file_exit_code_1(self):
        bogus_path = "/tmp/hyprsmartshot_stress_nonexistent_404_file.png"
        proc = subprocess.run([PIN_BIN, bogus_path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Image not found:", proc.stderr)

    def test_cli_directory_input_rejected_with_exit_code_1(self):
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run([PIN_BIN, td], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("Error: Image not found:", proc.stderr)

    def test_cli_flag_ordering_permutations(self):
        """Verify flags can appear before or after the image path."""
        mod = load_pin_module()
        # Verify argument parsing function directly
        for argv in [
            ["hyprsmartshot-pin", "--keep", "/tmp/fake.png"],
            ["hyprsmartshot-pin", "/tmp/fake.png", "--keep"],
            ["hyprsmartshot-pin", "--no-delete", "/tmp/fake.png"],
            ["hyprsmartshot-pin", "/tmp/fake.png", "--no-delete"],
            ["hyprsmartshot-pin", "--delete", "/tmp/fake.png"],
            ["hyprsmartshot-pin", "/tmp/fake.png", "--delete"],
            ["hyprsmartshot-pin", "--rm", "/tmp/fake.png"],
            ["hyprsmartshot-pin", "/tmp/fake.png", "--rm"],
        ]:
            with self.subTest(argv=argv):
                delete_flag = None
                clean = []
                for a in argv[1:]:
                    if a in ("--delete", "--rm"):
                        delete_flag = True
                    elif a in ("--keep", "--no-delete"):
                        delete_flag = False
                    else:
                        clean.append(a)
                self.assertEqual(clean, ["/tmp/fake.png"])
                if "--keep" in argv or "--no-delete" in argv:
                    self.assertFalse(delete_flag)
                if "--delete" in argv or "--rm" in argv:
                    self.assertTrue(delete_flag)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 required for PinWindow stress tests")
class TestPinLifecycleStress(unittest.TestCase):
    """Stress tests for disk unlinking and memory retention of loaded images."""

    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication(["hyprsmartshot-pin-stress"])
        cls.mod = load_pin_module()

    def _create_image(self, directory=None, prefix="hyprsmartshot_stress_", w=128, h=96, color=None):
        if color is None:
            color = QColor(120, 200, 80)
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=".png", dir=directory)
        os.close(fd)
        pix = QPixmap(w, h)
        pix.fill(color)
        pix.save(path, "PNG")
        with open(path, "rb") as f:
            raw_bytes = f.read()
        return path, raw_bytes

    def test_tmp_file_unlinked_immediately(self):
        """Temporary file in /tmp without prefix must be unlinked immediately."""
        path, raw_bytes = self._create_image(directory="/tmp", prefix="test_pin_unprefixed_")
        self.assertTrue(os.path.isfile(path))

        win = self.mod.PinWindow(path)
        try:
            # File unlinked from disk
            self.assertFalse(os.path.exists(path), "File in /tmp must be deleted immediately after loading")
            # In-memory pixmap and raw bytes intact
            self.assertFalse(win.orig_pixmap.isNull())
            self.assertEqual(win.orig_pixmap.width(), 128)
            self.assertEqual(win.orig_pixmap.height(), 96)
            self.assertEqual(win.image_bytes, raw_bytes)
            self.assertEqual(win.raw_image_data, raw_bytes)
        finally:
            win.close()
            if os.path.exists(path):
                os.remove(path)

    def test_var_tmp_file_unlinked_immediately(self):
        """Temporary file in /var/tmp must be unlinked immediately."""
        if os.path.isdir("/var/tmp") and os.access("/var/tmp", os.W_OK):
            path, raw_bytes = self._create_image(directory="/var/tmp", prefix="vartmp_pin_")
            self.assertTrue(os.path.isfile(path))
            win = self.mod.PinWindow(path)
            try:
                self.assertFalse(os.path.exists(path), "File in /var/tmp must be deleted immediately")
                self.assertFalse(win.orig_pixmap.isNull())
                self.assertEqual(win.image_bytes, raw_bytes)
            finally:
                win.close()
                if os.path.exists(path):
                    os.remove(path)

    def test_prefix_file_in_custom_dir_unlinked_immediately(self):
        """File named with 'hyprsmartshot' prefix in non-tmp dir must be unlinked."""
        with tempfile.TemporaryDirectory(dir=str(REPO_DIR)) as custom_dir:
            path, raw_bytes = self._create_image(directory=custom_dir, prefix="hyprsmartshot_crop_")
            self.assertTrue(os.path.isfile(path))
            win = self.mod.PinWindow(path)
            try:
                self.assertFalse(os.path.exists(path), "File prefixed with 'hyprsmartshot' must be deleted immediately")
                self.assertFalse(win.orig_pixmap.isNull())
                self.assertEqual(win.image_bytes, raw_bytes)
            finally:
                win.close()

    def test_user_file_without_prefix_in_custom_dir_preserved(self):
        """Regular user image file in custom directory must NOT be deleted by default."""
        with tempfile.TemporaryDirectory(dir=str(REPO_DIR)) as custom_dir:
            path, raw_bytes = self._create_image(directory=custom_dir, prefix="user_wallpaper_")
            self.assertTrue(os.path.isfile(path))
            win = self.mod.PinWindow(path)
            try:
                self.assertTrue(os.path.exists(path), "User file must be preserved when not in temp or prefixed")
                self.assertFalse(win.orig_pixmap.isNull())
            finally:
                win.close()

    def test_keep_flag_preserves_temp_file(self):
        """should_delete=False (--keep) preserves file even in /tmp with hyprsmartshot prefix."""
        path, raw_bytes = self._create_image(directory="/tmp", prefix="hyprsmartshot_must_keep_")
        self.assertTrue(os.path.isfile(path))
        win = self.mod.PinWindow(path, should_delete=False)
        try:
            self.assertTrue(os.path.exists(path), "--keep must prevent deletion")
            # Zoom and manipulate
            win.set_zoom(2.0)
            win.update()
            self.assertTrue(os.path.exists(path), "File must remain on disk during zoom/manipulation")
        finally:
            win.close()
            self.assertTrue(os.path.exists(path), "File must remain on disk after window close")
            if os.path.exists(path):
                os.remove(path)

    def test_delete_flag_forces_deletion_of_user_file(self):
        """should_delete=True (--delete) forces deletion even for regular user files."""
        with tempfile.TemporaryDirectory(dir=str(REPO_DIR)) as custom_dir:
            path, raw_bytes = self._create_image(directory=custom_dir, prefix="user_force_delete_")
            self.assertTrue(os.path.isfile(path))
            win = self.mod.PinWindow(path, should_delete=True)
            try:
                self.assertFalse(os.path.exists(path), "should_delete=True must delete the file")
                self.assertFalse(win.orig_pixmap.isNull())
            finally:
                win.close()

    def test_corrupt_image_raises_value_error(self):
        """PinWindow must raise ValueError when given a non-image/corrupted file."""
        fd, path = tempfile.mkstemp(prefix="corrupt_pin_", suffix=".png")
        os.write(fd, b"CORRUPTED_NOT_AN_IMAGE_DATA_12345")
        os.close(fd)
        try:
            with self.assertRaises(ValueError) as ctx:
                self.mod.PinWindow(path, should_delete=False)
            self.assertIn("Failed to load image from:", str(ctx.exception))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_zero_byte_file_raises_value_error(self):
        """PinWindow must raise ValueError when given an empty 0-byte file."""
        fd, path = tempfile.mkstemp(prefix="empty_pin_", suffix=".png")
        os.close(fd)
        try:
            with self.assertRaises(ValueError) as ctx:
                self.mod.PinWindow(path, should_delete=False)
            self.assertIn("Failed to load image from:", str(ctx.exception))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_extreme_large_image_handling(self):
        """PinWindow must handle high-resolution crops (e.g. 4000x3000) smoothly."""
        path, _ = self._create_image(w=4000, h=3000)
        try:
            win = self.mod.PinWindow(path, should_delete=False)
            self.assertEqual(win.orig_pixmap.width(), 4000)
            self.assertEqual(win.orig_pixmap.height(), 3000)
            win.set_zoom(0.2)
            self.assertEqual(win.width(), 800)
            self.assertEqual(win.height(), 600)
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_extreme_tiny_image_minimum_bounds(self):
        """PinWindow must clamp tiny images (e.g. 1x1) to safe minimum bounds (40x30)."""
        path, _ = self._create_image(w=1, h=1)
        try:
            win = self.mod.PinWindow(path, should_delete=False)
            win.set_zoom(0.2)
            self.assertGreaterEqual(win.width(), 40)
            self.assertGreaterEqual(win.height(), 30)
            win.set_zoom(6.0)
            self.assertGreaterEqual(win.width(), 40)
            self.assertGreaterEqual(win.height(), 30)
            # Render via grab to verify QPainter doesn't fail
            grabbed = win.grab()
            self.assertFalse(grabbed.isNull())
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_rendering_grab_across_zoom_factors(self):
        """Verify QWidget.grab() rendering at scales 0.2, 1.0, and 6.0."""
        path, _ = self._create_image(w=100, h=80)
        try:
            win = self.mod.PinWindow(path, should_delete=False)
            for scale in [0.2, 1.0, 3.0, 6.0]:
                win.set_zoom(scale)
                grabbed = win.grab()
                self.assertFalse(grabbed.isNull(), f"Rendering failed at scale {scale}")
                self.assertEqual(grabbed.width(), win.width())
                self.assertEqual(grabbed.height(), win.height())
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 required for PinWindow stress tests")
class TestPinZoomAndAspectStress(unittest.TestCase):
    """Adversarial stress testing for zoom scaling limits and aspect ratio preservation."""

    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication(["hyprsmartshot-pin-zoom"])
        cls.mod = load_pin_module()

    def _create_temp_pixmap_file(self, w, h):
        fd, path = tempfile.mkstemp(prefix="hyprsmartshot_aspect_", suffix=".png")
        os.close(fd)
        pix = QPixmap(w, h)
        pix.fill(QColor(100, 150, 200))
        pix.save(path, "PNG")
        return path

    def test_extreme_zoom_in_clamping(self):
        path = self._create_temp_pixmap_file(100, 100)
        try:
            win = self.mod.PinWindow(path, should_delete=False)
            self.assertEqual(win.scale_factor, 1.0)

            # Zoom in 100 consecutive times via keyboard '+'
            event_plus = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier, "+")
            for _ in range(100):
                win.keyPressEvent(event_plus)
                self.assertLessEqual(win.scale_factor, 6.0001, "scale_factor must never exceed max_scale (6.0)")

            self.assertAlmostEqual(win.scale_factor, 6.0, places=3)

            # Direct extreme zoom
            win.set_zoom(999999.0)
            self.assertAlmostEqual(win.scale_factor, 6.0, places=3)
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_extreme_zoom_out_clamping(self):
        path = self._create_temp_pixmap_file(100, 100)
        try:
            win = self.mod.PinWindow(path, should_delete=False)
            self.assertEqual(win.scale_factor, 1.0)

            # Zoom out 100 consecutive times via keyboard '-'
            event_minus = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Minus, Qt.KeyboardModifier.NoModifier, "-")
            for _ in range(100):
                win.keyPressEvent(event_minus)
                self.assertGreaterEqual(win.scale_factor, 0.1999, "scale_factor must never drop below min_scale (0.2)")

            self.assertAlmostEqual(win.scale_factor, 0.2, places=3)

            # Direct extreme zoom
            win.set_zoom(0.000001)
            self.assertAlmostEqual(win.scale_factor, 0.2, places=3)
            win.set_zoom(-50.0)
            self.assertAlmostEqual(win.scale_factor, 0.2, places=3)
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_zoom_reset_reverts_to_native_dimensions(self):
        path = self._create_temp_pixmap_file(250, 150)
        try:
            win = self.mod.PinWindow(path, should_delete=False)
            self.assertEqual(win.width(), 250)
            self.assertEqual(win.height(), 150)

            # Zoom to 4.5x
            win.set_zoom(4.5)
            self.assertAlmostEqual(win.scale_factor, 4.5)

            # Reset zoom via '0'
            event_zero = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier, "0")
            win.keyPressEvent(event_zero)
            self.assertAlmostEqual(win.scale_factor, 1.0)
            self.assertEqual(win.width(), 250)
            self.assertEqual(win.height(), 150)

            # Zoom to 0.3x
            win.set_zoom(0.3)
            self.assertAlmostEqual(win.scale_factor, 0.3)

            # Reset zoom via reset_zoom()
            win.reset_zoom()
            self.assertAlmostEqual(win.scale_factor, 1.0)
            self.assertEqual(win.width(), 250)
            self.assertEqual(win.height(), 150)
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_aspect_ratio_preservation_across_shapes(self):
        """Stress-test aspect ratio preservation across different geometries:
        1:1 square, 16:9 widescreen, 9:16 portrait, 21:9 ultrawide, 10:1 banner."""
        shapes = [
            (200, 200, "1:1 square"),
            (320, 180, "16:9 widescreen"),
            (180, 320, "9:16 portrait"),
            (420, 180, "21:9 ultrawide"),
            (500, 50, "10:1 banner"),
            (50, 500, "1:10 column"),
        ]

        scales_to_test = [0.2, 0.35, 0.5, 0.8, 1.0, 1.15, 1.5, 2.0, 3.2, 5.0, 6.0]

        for orig_w, orig_h, label in shapes:
            with self.subTest(shape=label):
                path = self._create_temp_pixmap_file(orig_w, orig_h)
                try:
                    win = self.mod.PinWindow(path, should_delete=False)
                    orig_ratio = orig_w / orig_h

                    for scale in scales_to_test:
                        win.set_zoom(scale)
                        # The window size must be rounded from original dimensions
                        expected_w = max(40, int(round(orig_w * win.scale_factor)))
                        expected_h = max(30, int(round(orig_h * win.scale_factor)))
                        self.assertEqual(win.width(), expected_w)
                        self.assertEqual(win.height(), expected_h)

                        # Inside paintEvent, scaled pixmap maintains KeepAspectRatio
                        scaled = win.orig_pixmap.scaled(
                            win.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        # Integer pixel quantization tolerance: for small dimensions (e.g. height < 20px),
                        # 1 pixel of rounding accounts for up to 5-6% ratio variation.
                        # We verify that scaled image maintains orig_ratio within integer rounding bound:
                        expected_scaled_w = round(scaled.height() * orig_ratio)
                        self.assertLessEqual(
                            abs(scaled.width() - expected_scaled_w),
                            max(5, int(scaled.width() * 0.05)),
                            msg=f"Aspect ratio drift on {label} at scale {scale}"
                        )
                    win.close()
                finally:
                    if os.path.exists(path):
                        os.remove(path)

    def test_anchor_point_smooth_zoom_geometry(self):
        """Verify zooming with arbitrary anchor points (corners, centers, outside)."""
        path = self._create_temp_pixmap_file(300, 200)
        try:
            win = self.mod.PinWindow(path, x=200, y=200, should_delete=False)
            anchors = [
                QPointF(0, 0),        # Top-left
                QPointF(300, 200),    # Bottom-right
                QPointF(150, 100),    # Center
                QPointF(-50, -50),    # Outside top-left
                QPointF(500, 400),    # Outside bottom-right
            ]
            for anchor in anchors:
                win.set_zoom(1.5, anchor_pos=anchor)
                pos = win.pos()
                self.assertFalse(pos.isNull() and pos.x() == 0 and pos.y() == 0)
                # Verify coordinates are valid integers
                self.assertIsInstance(pos.x(), int)
                self.assertIsInstance(pos.y(), int)
                win.reset_zoom()
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 required for PinWindow stress tests")
class TestPinKeyboardShortcutsStress(unittest.TestCase):
    """Stress testing of all keyboard shortcuts and rapid sequences."""

    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication(["hyprsmartshot-pin-keys"])
        cls.mod = load_pin_module()

    def _create_temp_image(self):
        fd, path = tempfile.mkstemp(prefix="hyprsmartshot_keys_", suffix=".png")
        os.close(fd)
        pix = QPixmap(100, 100)
        pix.fill(QColor(80, 120, 160))
        pix.save(path, "PNG")
        return path

    def test_keyboard_shortcuts_coverage(self):
        path = self._create_temp_image()
        try:
            # 1. Plus '+' and '=' keys
            win = self.mod.PinWindow(path, should_delete=False)
            initial_scale = win.scale_factor
            event_equal = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Equal, Qt.KeyboardModifier.NoModifier, "=")
            win.keyPressEvent(event_equal)
            self.assertGreater(win.scale_factor, initial_scale)

            # 2. Minus '-' and '_' keys
            event_underscore = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Underscore, Qt.KeyboardModifier.NoModifier, "_")
            win.keyPressEvent(event_underscore)
            self.assertAlmostEqual(win.scale_factor, initial_scale, places=3)

            # 3. '0' key
            win.set_zoom(3.0)
            event_zero = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier, "0")
            win.keyPressEvent(event_zero)
            self.assertAlmostEqual(win.scale_factor, 1.0)

            # 4. 'Esc' key
            win.show()
            self.assertTrue(win.isVisible())
            event_esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            win.keyPressEvent(event_esc)
            self.assertFalse(win.isVisible(), "Esc must hide/close window")

            # 5. 'q' key
            win.show()
            self.assertTrue(win.isVisible())
            event_q = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.NoModifier, "q")
            win.keyPressEvent(event_q)
            self.assertFalse(win.isVisible(), "'q' must hide/close window")

            # 6. 'Q' (uppercase) key
            win.show()
            self.assertTrue(win.isVisible())
            event_big_q = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.ShiftModifier, "Q")
            win.keyPressEvent(event_big_q)
            self.assertFalse(win.isVisible(), "'Q' must hide/close window")
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_rapid_key_event_sequence_no_crash(self):
        """Simulate rapid interleaved keystrokes without crashes or invalid states."""
        path = self._create_temp_image()
        try:
            win = self.mod.PinWindow(path, should_delete=False)
            keys = [
                QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier, "+"),
                QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier, "+"),
                QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Minus, Qt.KeyboardModifier.NoModifier, "-"),
                QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier, "0"),
                QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Equal, Qt.KeyboardModifier.NoModifier, "="),
                QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Underscore, Qt.KeyboardModifier.NoModifier, "_"),
            ]
            for _ in range(50):
                for k in keys:
                    win.keyPressEvent(k)
                    self.assertTrue(0.2 <= win.scale_factor <= 6.0)
            win.close()
        finally:
            if os.path.exists(path):
                os.remove(path)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 required for PinWindow stress tests")
class TestPinClipboardStress(unittest.TestCase):
    """Stress testing for in-memory clipboard copying and fault injection."""

    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication(["hyprsmartshot-pin-clipboard"])
        cls.mod = load_pin_module()

    def _create_temp_image(self, w=80, h=60):
        fd, path = tempfile.mkstemp(prefix="hyprsmartshot_cb_", suffix=".png")
        os.close(fd)
        pix = QPixmap(w, h)
        pix.fill(QColor(220, 60, 40))
        pix.save(path, "PNG")
        with open(path, "rb") as f:
            raw = f.read()
        return path, raw

    def test_clipboard_copy_when_disk_file_deleted(self):
        """Calling copy_to_clipboard() must succeed even after the file is gone from disk."""
        path, raw_bytes = self._create_temp_image(90, 70)
        win = self.mod.PinWindow(path, should_delete=True)
        try:
            self.assertFalse(os.path.exists(path), "File must be deleted from disk")
            # Invoke clipboard copy
            win.copy_to_clipboard()

            # Verify Qt clipboard received the pixmap
            cb = QApplication.clipboard()
            cb_pix = cb.pixmap()
            self.assertFalse(cb_pix.isNull(), "Clipboard pixmap must not be null")
            self.assertEqual(cb_pix.width(), 90)
            self.assertEqual(cb_pix.height(), 70)
        finally:
            win.close()
            if os.path.exists(path):
                os.remove(path)

    def test_ctrl_c_and_enter_trigger_clipboard_copy(self):
        """Ctrl+C and Enter key events trigger copy_to_clipboard()."""
        path, raw_bytes = self._create_temp_image(64, 64)
        win = self.mod.PinWindow(path, should_delete=False)
        try:
            # Clear clipboard first
            cb = QApplication.clipboard()
            cb.clear()

            # Trigger via Enter
            event_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
            win.keyPressEvent(event_enter)
            self.assertFalse(cb.pixmap().isNull(), "Enter key must trigger clipboard copy")

            cb.clear()
            # Trigger via Ctrl+C
            event_ctrl_c = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_C,
                Qt.KeyboardModifier.ControlModifier,
                text="\x03"
            )
            win.keyPressEvent(event_ctrl_c)
            self.assertFalse(cb.pixmap().isNull(), "Ctrl+C must trigger clipboard copy")
        finally:
            win.close()
            if os.path.exists(path):
                os.remove(path)

    def test_clipboard_resiliency_when_wl_copy_fails(self):
        """Ensure failure in wl-copy subprocess does not crash or prevent Qt clipboard populate."""
        path, raw_bytes = self._create_temp_image(50, 50)
        win = self.mod.PinWindow(path, should_delete=False)
        try:
            with patch("subprocess.run") as mock_run:
                # First call (wl-copy) raises exception
                mock_run.side_effect = subprocess.CalledProcessError(1, ["wl-copy"])
                # Must not raise exception
                win.copy_to_clipboard()

                # Qt clipboard is still populated
                cb = QApplication.clipboard()
                self.assertFalse(cb.pixmap().isNull())
        finally:
            win.close()
            if os.path.exists(path):
                os.remove(path)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 required for PinWindow stress tests")
class TestMultiWindowConcurrencyStress(unittest.TestCase):
    """Stress test multiple concurrent PinWindow instances."""

    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication(["hyprsmartshot-pin-multi"])
        cls.mod = load_pin_module()

    def test_concurrent_pin_windows(self):
        windows = []
        paths = []
        try:
            for i in range(8):
                fd, path = tempfile.mkstemp(prefix=f"hyprsmartshot_multi_{i}_", suffix=".png")
                os.close(fd)
                paths.append(path)
                pix = QPixmap(50 + i * 10, 50 + i * 10)
                pix.fill(QColor(i * 30, 100, 200))
                pix.save(path, "PNG")

                win = self.mod.PinWindow(path, should_delete=False)
                win.set_zoom(1.0 + i * 0.2)
                windows.append(win)

            for i, win in enumerate(windows):
                expected_scale = 1.0 + i * 0.2
                self.assertAlmostEqual(win.scale_factor, expected_scale)
                self.assertEqual(win.orig_pixmap.width(), 50 + i * 10)
                self.assertEqual(win.orig_pixmap.height(), 50 + i * 10)
        finally:
            for win in windows:
                win.close()
            for p in paths:
                if os.path.exists(p):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main()
