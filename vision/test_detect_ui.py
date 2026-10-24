#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot Computer Vision UI Detector (vision/detect_ui.py)
"""

import os
import unittest
import tempfile
import cv2
import numpy as np

from vision.detect_ui import detect_ui_elements, compute_border_contrast, cluster_slots_and_grids

class TestUIDetector(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _save_img(self, name, img):
        path = os.path.join(self.temp_dir.name, name)
        cv2.imwrite(path, img)
        return path

    def test_invalid_path(self):
        res = detect_ui_elements("/nonexistent/path/to/image.png")
        self.assertIn("error", res)
        self.assertEqual(res["boxes"], [])

    def test_solid_black_image(self):
        img = np.zeros((600, 800, 3), dtype=np.uint8)
        path = self._save_img("solid_black.png", img)
        res = detect_ui_elements(path)
        self.assertEqual(res["count"], 0)
        self.assertEqual(len(res["boxes"]), 0)

    def test_low_contrast_fantasy_panel(self):
        # Dark fantasy panel: background is 20, body is 30, border is 55
        img = np.full((600, 800, 3), 20, dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (700, 500), (30, 30, 30), -1)
        cv2.rectangle(img, (100, 100), (700, 500), (55, 50, 45), 2)
        path = self._save_img("fantasy_panel.png", img)

        res = detect_ui_elements(path)
        self.assertGreaterEqual(res["count"], 1)
        # Find the main panel
        panel = None
        for b in res["boxes"]:
            if abs(b["x"] - 100) <= 8 and abs(b["y"] - 100) <= 8 and abs(b["w"] - 600) <= 12 and abs(b["h"] - 400) <= 12:
                panel = b
                break
        self.assertIsNotNone(panel, "Expected low-contrast fantasy panel to be detected")

    def test_split_hotbars(self):
        # Two 3-slot action bars on the same Y separated by 300px
        img = np.full((300, 800, 3), 30, dtype=np.uint8)
        # Left bar: 3 slots of 40x40 at x=50, y=100
        for i in range(3):
            cv2.rectangle(img, (50 + i*48, 100), (50 + i*48 + 40, 140), (80, 80, 80), -1)
            cv2.rectangle(img, (50 + i*48, 100), (50 + i*48 + 40, 140), (200, 200, 200), 2)
        # Right bar: 3 slots of 40x40 at x=500, y=100
        for i in range(3):
            cv2.rectangle(img, (500 + i*48, 100), (500 + i*48 + 40, 140), (80, 80, 80), -1)
            cv2.rectangle(img, (500 + i*48, 100), (500 + i*48 + 40, 140), (200, 200, 200), 2)
        path = self._save_img("split_hotbars.png", img)

        res = detect_ui_elements(path)
        # Should detect both rows independently
        row_boxes = [b for b in res["boxes"] if b["type"] == "grid_row"]
        self.assertGreaterEqual(len(row_boxes), 2, "Expected at least 2 distinct grid_rows for split hotbars")

        # Verify left row and right row coordinates
        left_found = any(abs(r["x"] - 50) <= 8 and abs(r["y"] - 100) <= 8 for r in row_boxes)
        right_found = any(abs(r["x"] - 500) <= 8 and abs(r["y"] - 100) <= 8 for r in row_boxes)
        self.assertTrue(left_found, "Left hotbar row should be detected")
        self.assertTrue(right_found, "Right hotbar row should be detected")

    def test_inventory_grid_container(self):
        # 4x4 inventory grid: container at (400, 200, 240, 240)
        img = np.full((700, 900, 3), 25, dtype=np.uint8)
        cv2.rectangle(img, (400, 200), (640, 440), (40, 40, 40), -1)
        cv2.rectangle(img, (400, 200), (640, 440), (160, 150, 130), 2)
        for r in range(4):
            for c in range(4):
                sx = 410 + c * 56
                sy = 210 + r * 56
                cv2.rectangle(img, (sx, sy), (sx + 50, sy + 50), (60, 60, 60), -1)
                cv2.rectangle(img, (sx, sy), (sx + 50, sy + 50), (200, 190, 180), 1)
        path = self._save_img("inventory_grid.png", img)

        res = detect_ui_elements(path)
        # Check for grid_container synthesis
        grid_containers = [b for b in res["boxes"] if b["type"] == "grid_container"]
        self.assertGreaterEqual(len(grid_containers), 1, "Expected a synthesized grid_container")
        grid = grid_containers[0]
        self.assertTrue(abs(grid["x"] - 410) <= 10 and abs(grid["y"] - 210) <= 10)

    def test_3d_background_noise_filtering(self):
        # High frequency background noise + floor tiles
        np.random.seed(99)
        img = np.random.normal(30, 8, (600, 800, 3)).clip(0, 255).astype(np.uint8)
        # Add floor tile lines
        for y in range(0, 600, 60):
            cv2.line(img, (0, y), (800, y), (35, 30, 25), 1)
        for x in range(0, 800, 60):
            cv2.line(img, (x, 0), (x, 600), (35, 30, 25), 1)

        # Real UI element: Health bar at (50, 500, 250, 30)
        cv2.rectangle(img, (50, 500), (300, 530), (20, 20, 20), -1)
        cv2.rectangle(img, (50, 500), (300, 530), (50, 60, 210), -1)
        cv2.rectangle(img, (50, 500), (300, 530), (220, 220, 230), 2)

        path = self._save_img("game_noise.png", img)
        res = detect_ui_elements(path)

        # Noise tiles should be heavily suppressed; count should not explode into hundreds
        self.assertLess(res["count"], 40, f"Expected < 40 boxes, got {res['count']}")
        # The health bar should be present
        health_found = any(abs(b["x"] - 50) <= 6 and abs(b["y"] - 500) <= 6 and abs(b["w"] - 250) <= 8 for b in res["boxes"])
        self.assertTrue(health_found, "Real health bar UI should be detected despite background texture noise")

    def test_corrupt_file_handling(self):
        # Create non-image garbage file
        path = os.path.join(self.temp_dir.name, "corrupt.png")
        with open(path, "wb") as f:
            f.write(b"NOT_A_PNG_FILE_DATA_CORRUPT")
        res = detect_ui_elements(path)
        self.assertIn("error", res)
        self.assertEqual(res["boxes"], [])

    def test_hierarchy_depth_ordering(self):
        # Nested boxes: Outer (100, 100, 500, 400), Mid (150, 150, 300, 200), Inner (200, 200, 100, 80)
        img = np.full((600, 800, 3), 15, dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (600, 500), (40, 40, 40), -1)
        cv2.rectangle(img, (100, 100), (600, 500), (180, 180, 180), 2)

        cv2.rectangle(img, (150, 150), (450, 350), (70, 70, 70), -1)
        cv2.rectangle(img, (150, 150), (450, 350), (210, 210, 210), 2)

        cv2.rectangle(img, (200, 200), (300, 280), (100, 100, 100), -1)
        cv2.rectangle(img, (200, 200), (300, 280), (240, 240, 240), 2)

        path = self._save_img("nested_depth.png", img)
        res = detect_ui_elements(path)
        self.assertGreaterEqual(res["count"], 3)

        # Verify depths are ordered properly
        outer = next(b for b in res["boxes"] if abs(b["x"] - 100) <= 6 and abs(b["w"] - 500) <= 8)
        mid = next(b for b in res["boxes"] if abs(b["x"] - 150) <= 6 and abs(b["w"] - 300) <= 8)
        inner = next(b for b in res["boxes"] if abs(b["x"] - 200) <= 6 and abs(b["w"] - 100) <= 8)

        self.assertEqual(outer["depth"], 0)
        self.assertGreater(mid["depth"], outer["depth"])
        self.assertGreater(inner["depth"], mid["depth"])

if __name__ == "__main__":
    unittest.main()
