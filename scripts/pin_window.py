#!/usr/bin/env python3
"""
HyprSmartShot Native Wayland Pin Window
Displays a pinned screenshot in a native Wayland XDG toplevel floating window.

Features:
- Native Wayland app-id: "hyprsmartshot-pin"
- Drag to move: left mouse button uses Wayland startSystemMove()
- Zoom: mouse wheel (0.25x - 5.0x), double-click to reset (1.0x)
- Copy: Ctrl+C or Enter copies image back to clipboard
- Close: Esc, q, or middle/right click
- Hyprland integration: sets floating and pin via hyprctl IPC
"""

import sys
import os
import subprocess
import shutil

def fallback_viewer(image_path):
    """Fallback when PySide6 is not available."""
    viewers = [
        ["swayimg", "--app-id=hyprsmartshot-pin", image_path],
        ["imv", image_path],
        ["feh", "-.", "-B", "black", image_path],
        ["xdg-open", image_path]
    ]
    for cmd in viewers:
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd)
                return 0
            except Exception:
                continue
    return 1

def run_pyside6_viewer(image_path, init_x=None, init_y=None, init_w=None, init_h=None):
    from PySide6.QtCore import Qt, QTimer, QPointF
    from PySide6.QtGui import QPixmap, QPainter, QAction, QKeySequence, QColor
    from PySide6.QtWidgets import QApplication, QWidget, QMenu

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("hyprsmartshot-pin")
    app.setDesktopFileName("hyprsmartshot-pin")

    class PinWindow(QWidget):
        def __init__(self, path, x=None, y=None, w=None, h=None):
            super().__init__()
            self.image_path = path
            self.orig_pixmap = QPixmap(path)
            if self.orig_pixmap.isNull():
                raise ValueError(f"Failed to load image: {path}")

            self.scale_factor = 1.0
            self.min_scale = 0.2
            self.max_scale = 6.0
            self.drag_start_pos = None

            # Window setup
            self.setWindowTitle("HyprSmartShot Pin")
            self.setObjectName("hyprsmartshot-pin")
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

            # Determine initial size
            img_w = self.orig_pixmap.width()
            img_h = self.orig_pixmap.height()
            win_w = w if (w and w > 20) else img_w
            win_h = h if (h and h > 20) else img_h

            self.resize(win_w, win_h)
            if x is not None and y is not None:
                self.move(int(x), int(y))

            # Enable Hyprland floating and pin after window maps
            QTimer.singleShot(150, self._hyprland_pin)

        def _hyprland_pin(self):
            """Dispatch Hyprland rules to ensure floating and pinned status."""
            if shutil.which("hyprctl"):
                try:
                    subprocess.run(["hyprctl", "dispatch", "setfloating", "active"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    subprocess.run(["hyprctl", "dispatch", "pin", "active"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            # Draw background border / shadow
            painter.fillRect(self.rect(), QColor(20, 20, 25))

            # Draw scaled image
            scaled = self.orig_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            # Center image in widget
            ox = (self.width() - scaled.width()) // 2
            oy = (self.height() - scaled.height()) // 2
            painter.drawPixmap(ox, oy, scaled)

            # Draw thin subtle border around pinned window
            painter.setPen(QColor(100, 150, 255, 160))
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                # Native Wayland system move initiation
                wh = self.windowHandle()
                if wh and hasattr(wh, "startSystemMove") and wh.startSystemMove():
                    return
                # Fallback manual drag for environments without startSystemMove
                self.drag_start_pos = event.globalPosition().toPoint() - self.pos()
                event.accept()
            elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
                self.close()

        def mouseMoveEvent(self, event):
            if self.drag_start_pos and (event.buttons() & Qt.MouseButton.LeftButton):
                self.move(event.globalPosition().toPoint() - self.drag_start_pos)
                event.accept()

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_start_pos = None

        def mouseDoubleClickEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                # Reset to 1:1 original scale
                self.scale_factor = 1.0
                self.resize(self.orig_pixmap.width(), self.orig_pixmap.height())
                self.update()

        def wheelEvent(self, event):
            delta = event.angleDelta().y()
            if delta == 0:
                return

            zoom_step = 1.15 if delta > 0 else (1.0 / 1.15)
            new_scale = max(self.min_scale, min(self.max_scale, self.scale_factor * zoom_step))
            if abs(new_scale - self.scale_factor) < 1e-4:
                return

            self.scale_factor = new_scale
            new_w = max(40, int(self.orig_pixmap.width() * self.scale_factor))
            new_h = max(30, int(self.orig_pixmap.height() * self.scale_factor))

            # Anchor zoom around cursor position
            cursor_pos = event.position()
            rx = cursor_pos.x() / max(1, self.width())
            ry = cursor_pos.y() / max(1, self.height())

            old_pos = self.pos()
            dw = new_w - self.width()
            dh = new_h - self.height()

            new_x = int(old_pos.x() - dw * rx)
            new_y = int(old_pos.y() - dh * ry)

            self.resize(new_w, new_h)
            self.move(new_x, new_y)
            self.update()
            event.accept()

        def keyPressEvent(self, event):
            if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
                self.close()
            elif event.matches(QKeySequence.StandardKey.Copy) or event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.copy_to_clipboard()
            else:
                super().keyPressEvent(event)

        def copy_to_clipboard(self):
            """Copy image to clipboard using wl-copy or Qt clipboard."""
            copied = False
            if shutil.which("wl-copy") and os.path.isfile(self.image_path):
                try:
                    subprocess.run(
                        ["wl-copy", "--type", "image/png"],
                        input=open(self.image_path, "rb").read(),
                        check=True
                    )
                    copied = True
                except Exception:
                    pass

            if not copied:
                cb = QApplication.clipboard()
                if cb:
                    cb.setPixmap(self.orig_pixmap)
                    copied = True

            if copied and shutil.which("notify-send"):
                try:
                    subprocess.run([
                        "notify-send",
                        "-a", "HyprSmartShot",
                        "-i", self.image_path,
                        "HyprSmartShot",
                        "Screenshot copied to clipboard"
                    ], check=False)
                except Exception:
                    pass

    pin_win = PinWindow(image_path, init_x, init_y, init_w, init_h)
    pin_win.show()
    return app.exec()

def main():
    if len(sys.argv) < 2:
        print("Usage: pin_window.py <image_path> [x] [y] [width] [height]", file=sys.stderr)
        return 1

    image_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(image_path):
        print(f"Error: Image not found: {image_path}", file=sys.stderr)
        return 1

    x = int(float(sys.argv[2])) if len(sys.argv) > 2 else None
    y = int(float(sys.argv[3])) if len(sys.argv) > 3 else None
    w = int(float(sys.argv[4])) if len(sys.argv) > 4 else None
    h = int(float(sys.argv[5])) if len(sys.argv) > 5 else None

    try:
        import PySide6
        return run_pyside6_viewer(image_path, x, y, w, h)
    except ImportError:
        return fallback_viewer(image_path)
    except Exception as e:
        print(f"PySide6 viewer error: {e}", file=sys.stderr)
        return fallback_viewer(image_path)

if __name__ == "__main__":
    sys.exit(main())
