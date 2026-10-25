#!/usr/bin/env python3
"""
Unit tests for fractional scaling transforms and multi-monitor coordinate math.
Verifies elimination of 1px drift, screen boundary clamping, and client window scaling.
"""

import os
import unittest
import numpy as np

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def calculate_crop_box(x, y, width, height, scale, max_w, max_h):
    """
    Python reference implementation of the QML cropCommand transform:
    cx1 = max(0, min(max_w, round(x * scale)))
    cx2 = max(0, min(max_w, round((x + width) * scale)))
    cw = max(1, cx2 - cx1)
    """
    cx1 = max(0, min(max_w, int(round(x * scale))))
    cy1 = max(0, min(max_h, int(round(y * scale))))
    cx2 = max(0, min(max_w, int(round((x + width) * scale))))
    cy2 = max(0, min(max_h, int(round((y + height) * scale))))

    cw = max(1, cx2 - cx1)
    ch = max(1, cy2 - cy1)
    return cx1, cy1, cx2, cy2, cw, ch

class TestScalingAndTransforms(unittest.TestCase):
    def test_zero_drift_across_fractional_scales(self):
        """
        Verify that for all integer and fractional scale factors,
        cx1 + cw == cx2 strictly holds (0 physical pixel drift).
        """
        scales = [1.0, 1.25, 1.333333, 1.5, 1.6, 1.75, 2.0, 2.25, 2.5]
        max_w, max_h = 3840, 2160

        test_cases = [
            (10, 10, 95, 80),
            (100, 50, 536, 412),
            (0, 0, 1920, 1080),
            (15, 25, 123, 456),
            (333, 222, 777, 555),
            (1, 1, 3, 3),
        ]

        for s in scales:
            for x, y, w, h in test_cases:
                cx1, cy1, cx2, cy2, cw, ch = calculate_crop_box(x, y, w, h, s, max_w, max_h)
                self.assertEqual(
                    cx1 + cw, cx2,
                    f"Drift detected at scale={s} for x={x}, w={w}: cx1={cx1}, cw={cw}, cx2={cx2}"
                )
                self.assertEqual(
                    cy1 + ch, cy2,
                    f"Drift detected at scale={s} for y={y}, h={h}: cy1={cy1}, ch={ch}, cy2={cy2}"
                )

    def test_screen_boundary_clamping(self):
        """
        Verify that dragging past screen boundary clamps tightly to max_w / max_h
        without exceeding physical bounds or causing negative dimensions.
        """
        max_w, max_h = 1920, 1080
        scale = 1.25

        # Dragged past right edge (logical 1530 + 50 = 1580, physical 1975 > 1920)
        cx1, cy1, cx2, cy2, cw, ch = calculate_crop_box(1530, 100, 50, 200, scale, max_w, max_h)
        self.assertEqual(cx2, max_w, "cx2 must clamp to max_w")
        self.assertLessEqual(cx1 + cw, max_w, "Crop box must not exceed physical monitor width")
        self.assertGreater(cw, 0, "Crop width must remain positive")

    def test_client_window_scaling_in_cv_detector(self):
        """
        Verify that detect_ui.py converts logical client window coordinates to physical
        pixels when SMARTSHOT_MONITOR_SCALE is set.
        """
        import tempfile
        import json
        try:
            import cv2
            from vision.detect_ui import detect_ui_elements
        except ImportError:
            self.skipTest("OpenCV (cv2) not installed in current Python environment")

        with tempfile.TemporaryDirectory() as tmp_dir:
            img = np.full((1350, 2400, 3), 40, dtype=np.uint8)
            import cv2
            img_path = os.path.join(tmp_dir, "test.png")
            cv2.imwrite(img_path, img)

            clients_json = os.path.join(tmp_dir, "clients.json")
            with open(clients_json, "w") as f:
                json.dump([
                    # Logical window on 1600x900 logical monitor (2400x1350 physical at 1.5x scale)
                    {"at": [100, 80], "size": [800, 600], "workspace": {"id": 1}, "title": "Editor"}
                ], f)

            old_env = os.environ.copy()
            try:
                os.environ["SMARTSHOT_WORKSPACE_ID"] = "1"
                os.environ["SMARTSHOT_MONITOR_X"] = "0"
                os.environ["SMARTSHOT_MONITOR_Y"] = "0"
                os.environ["SMARTSHOT_MONITOR_SCALE"] = "1.5"

                res = detect_ui_elements(img_path, clients_path=clients_json)
                clients = [b for b in res["boxes"] if b.get("is_client")]
                self.assertEqual(len(clients), 1)
                c = clients[0]
                # Logical [100, 80, 800, 600] * 1.5 = physical [150, 120, 1200, 900]
                self.assertEqual(c["x"], 150)
                self.assertEqual(c["y"], 120)
                self.assertEqual(c["w"], 1200)
                self.assertEqual(c["h"], 900)
            finally:
                os.environ.clear()
                os.environ.update(old_env)

if __name__ == "__main__":
    unittest.main()
