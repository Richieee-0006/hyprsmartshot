#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot Computer Vision UI Detector (vision/detect_ui.py)
"""

import os
import sys
import unittest
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import cv2
    import numpy as np
    from vision.detect_ui import (
        detect_ui_elements,
        compute_border_contrast,
        cluster_slots_and_grids,
        cluster_adjacent_columns,
        detect_window_content_areas,
    )
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

class TestUIDetector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_CV2:
            raise unittest.SkipTest("OpenCV (cv2) or NumPy not installed in current Python environment")

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

    def test_true_low_contrast_dark_fantasy(self):
        # Realistic dark fantasy frame: background=18, interior=24, border=32 (contrast diff ~6-8)
        img = np.full((600, 800, 3), 18, dtype=np.uint8)
        cv2.rectangle(img, (120, 120), (680, 480), (24, 24, 24), -1)
        cv2.rectangle(img, (120, 120), (680, 480), (32, 30, 28), 2)
        path = self._save_img("true_low_contrast.png", img)

        res = detect_ui_elements(path)
        self.assertGreaterEqual(res["count"], 1)
        panel = next((b for b in res["boxes"] if abs(b["x"] - 120) <= 8 and abs(b["y"] - 120) <= 8 and abs(b["w"] - 560) <= 12), None)
        self.assertIsNotNone(panel, "Expected subtle dark fantasy panel (contrast ~6) to be detected")

    def test_no_duplicate_concentric_boxes(self):
        # 4px thick frame should yield exactly 1 deduplicated box, not 2 inner/outer concentric duplicates
        img = np.full((500, 600, 3), 20, dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (500, 400), (40, 40, 40), -1)
        cv2.rectangle(img, (100, 100), (500, 400), (180, 180, 180), 4)
        path = self._save_img("thick_frame.png", img)

        res = detect_ui_elements(path)
        panels = [b for b in res["boxes"] if b["type"] == "panel"]
        self.assertEqual(len(panels), 1, f"Expected exactly 1 panel, got {len(panels)} (duplicate inner/outer border detected)")

    def test_inventory_with_nested_items(self):
        # Inventory container with 4 slots containing item sprites (potion, sword, stack text)
        img = np.full((300, 500, 3), 30, dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (450, 250), (45, 45, 45), -1)
        cv2.rectangle(img, (50, 50), (450, 250), (120, 110, 100), 2)

        for i in range(4):
            sx = 70 + i * 90
            sy = 80
            cv2.rectangle(img, (sx, sy), (sx + 70, sy + 70), (20, 20, 20), -1)
            cv2.rectangle(img, (sx, sy), (sx + 70, sy + 70), (150, 140, 120), 2)
            if i == 0:
                cv2.circle(img, (sx + 35, sy + 40), 18, (40, 40, 220), -1)
            elif i == 1:
                cv2.line(img, (sx + 15, sy + 55), (sx + 55, sy + 15), (220, 220, 220), 4)
            elif i == 2:
                cv2.putText(img, "64", (sx + 38, sy + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        path = self._save_img("inventory_items.png", img)
        res = detect_ui_elements(path)

        rows = [b for b in res["boxes"] if b["type"] == "grid_row"]
        self.assertEqual(len(rows), 1, "Expected exactly 1 unified grid_row for 4 adjacent slots")
        self.assertTrue(abs(rows[0]["w"] - 340) <= 20, "Unified row should span all 4 slots")

        slots = [b for b in res["boxes"] if b["type"] == "slot"]
        self.assertEqual(len(slots), 4, f"Expected 4 distinct slots, got {len(slots)}")

        # Items inside slots should have type item and deeper hierarchy
        items = [b for b in res["boxes"] if b["type"] == "item"]
        self.assertGreaterEqual(len(items), 1, "Items inside slots should be classified as item")
        for it in items:
            self.assertGreater(it["depth"], slots[0]["depth"], "Item depth should be deeper than parent slot")

    def test_ornate_beveled_frame(self):
        # Ornate fantasy frame with corner notches
        img = np.full((500, 600, 3), 20, dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (500, 400), (35, 35, 35), -1)
        cv2.rectangle(img, (100, 100), (500, 400), (110, 100, 80), 2)
        # Add decorative notches at corners
        cv2.rectangle(img, (90, 90), (115, 115), (110, 100, 80), 2)
        cv2.rectangle(img, (485, 90), (510, 115), (110, 100, 80), 2)
        path = self._save_img("ornate_frame.png", img)

        res = detect_ui_elements(path)
        panels = [b for b in res["boxes"] if b["type"] == "panel"]
        self.assertGreaterEqual(len(panels), 1, "Ornate frame with decorative corners should be detected as panel")

    def test_floating_window_seeding(self):
        import json
        img = np.full((600, 800, 3), 20, dtype=np.uint8)
        path = self._save_img("clients_test.png", img)
        clients = [
            {"at": [150, 120], "size": [400, 300], "floating": True, "title": "Overlay Window", "class": "kitty", "hidden": False, "mapped": True},
            {"at": [0, 0], "size": [800, 600], "floating": False, "title": "Tiled Window", "class": "kitty", "hidden": False, "mapped": True}
        ]
        clients_path = os.path.join(self.temp_dir.name, "clients.json")
        with open(clients_path, "w") as f:
            json.dump(clients, f)

        res = detect_ui_elements(path, clients_path=clients_path)
        floating_wins = [b for b in res["boxes"] if b.get("type") == "floating_window"]
        self.assertGreaterEqual(len(floating_wins), 1, "Seeded floating overlay window should be detected")
        self.assertEqual(floating_wins[0]["x"], 150)
        self.assertEqual(floating_wins[0]["y"], 120)
        self.assertEqual(floating_wins[0]["w"], 400)
        self.assertEqual(floating_wins[0]["h"], 300)

    def test_small_inventory_slots_and_shapes(self):
        # Small 14x14 item slots and 24x12 button
        img = np.full((300, 400, 3), 30, dtype=np.uint8)
        # Small slot 14x14
        cv2.rectangle(img, (50, 50), (64, 64), (50, 50, 50), -1)
        cv2.rectangle(img, (50, 50), (64, 64), (180, 180, 180), 1)

        # Small slot 16x16
        cv2.rectangle(img, (100, 50), (116, 66), (50, 50, 50), -1)
        cv2.rectangle(img, (100, 50), (116, 66), (180, 180, 180), 1)

        # Small button 28x14
        cv2.rectangle(img, (150, 50), (178, 64), (60, 60, 60), -1)
        cv2.rectangle(img, (150, 50), (178, 64), (200, 200, 200), 1)

        path = self._save_img("small_shapes.png", img)
        res = detect_ui_elements(path)

        # Check that 14x14 slot is detected
        slot14 = [b for b in res["boxes"] if abs(b["x"] - 50) <= 2 and abs(b["y"] - 50) <= 2]
        self.assertGreaterEqual(len(slot14), 1, "Small 14x14 slot should be detected")
        self.assertTrue(12 <= slot14[0]["w"] <= 16 and 12 <= slot14[0]["h"] <= 16)

        # Check that 16x16 slot is detected
        slot16 = [b for b in res["boxes"] if abs(b["x"] - 100) <= 2 and abs(b["y"] - 50) <= 2]
        self.assertGreaterEqual(len(slot16), 1, "Small 16x16 slot should be detected")

        # Check button
        btn = [b for b in res["boxes"] if abs(b["x"] - 150) <= 2 and abs(b["y"] - 50) <= 2]
        self.assertGreaterEqual(len(btn), 1, "Small button should be detected")

    def test_small_slots_grid_cluster(self):
        # 3 small 16x16 slots with 4px gap in a row
        img = np.full((200, 300, 3), 25, dtype=np.uint8)
        for i in range(3):
            sx = 40 + i * 20
            sy = 40
            cv2.rectangle(img, (sx, sy), (sx + 16, sy + 16), (50, 50, 50), -1)
            cv2.rectangle(img, (sx, sy), (sx + 16, sy + 16), (190, 190, 190), 1)

        path = self._save_img("small_grid.png", img)
        res = detect_ui_elements(path)

        slots = [b for b in res["boxes"] if b["type"] == "slot" and abs(b["y"] - 40) <= 3]
        self.assertEqual(len(slots), 3, f"Expected 3 distinct small slots, got {len(slots)}")

        rows = [b for b in res["boxes"] if b["type"] == "grid_row"]
        self.assertGreaterEqual(len(rows), 1, "Expected clustered grid_row for small slots")

    def test_cluster_adjacent_columns(self):
        col1 = {"x": 50, "y": 80, "w": 400, "h": 600, "area": 240000, "type": "panel", "contrast": 30.0}
        col2 = {"x": 450, "y": 80, "w": 400, "h": 600, "area": 240000, "type": "panel", "contrast": 30.0}

        unions = cluster_adjacent_columns([col1, col2])
        self.assertEqual(len(unions), 1, "Expected 1 synthesized union panel for adjacent columns")
        u = unions[0]
        self.assertEqual(u["x"], 50)
        self.assertEqual(u["y"], 80)
        self.assertEqual(u["w"], 800)
        self.assertEqual(u["h"], 600)
        self.assertEqual(u["area"], 480000)

    def test_browser_window_content_viewport_detection(self):
        # 800x600 image: 0-80 is dark header (value 40), 80-600 is light page body (value 230)
        gray = np.full((600, 800), 230, dtype=np.uint8)
        gray[0:80, :] = 40

        client_box = [{"x": 0, "y": 0, "w": 800, "h": 600, "title": "Mozilla Firefox", "class": "firefox"}]
        content_boxes = detect_window_content_areas(gray, client_box)

        self.assertGreaterEqual(len(content_boxes), 1, "Expected browser content viewport to be detected")
        cb = content_boxes[0]
        self.assertEqual(cb["x"], 0)
        self.assertEqual(cb["w"], 800)
        # Sep Y should be at or near 80
        self.assertTrue(78 <= cb["y"] <= 82, f"Expected sep_y near 80, got {cb['y']}")
        self.assertTrue(518 <= cb["h"] <= 522, f"Expected body height near 520, got {cb['h']}")

    def test_browser_split_page_body_e2e(self):
        # Full mockup of browser: top 80px toolbar, then left half (white) and right half (light gray)
        img = np.full((700, 1000, 3), 40, dtype=np.uint8) # dark browser chrome
        # Left column of page
        cv2.rectangle(img, (20, 80), (500, 680), (255, 255, 255), -1)
        cv2.rectangle(img, (20, 80), (500, 680), (180, 180, 180), 1)
        # Right column of page
        cv2.rectangle(img, (500, 80), (980, 680), (245, 245, 245), -1)
        cv2.rectangle(img, (500, 80), (980, 680), (180, 180, 180), 1)

        path = self._save_img("browser_columns.png", img)
        clients_json = os.path.join(self.temp_dir.name, "clients.json")
        import json
        with open(clients_json, "w") as f:
            json.dump([{"at": [0, 0], "size": [1000, 700], "title": "Web Browser", "class": "zen-browser"}], f)

        res = detect_ui_elements(path, clients_path=clients_json)
        # Check that a box spanning the combined body (~960px wide, ~600px high at y=80) exists
        full_body_candidates = [
            b for b in res["boxes"]
            if b["w"] >= 850 and b["h"] >= 500 and 65 <= b["y"] <= 100
        ]
        self.assertGreaterEqual(len(full_body_candidates), 1, "Expected full web page body candidate starting below header to be detected")
        window_candidates = [
            b for b in res["boxes"]
            if b["w"] >= 990 and b["h"] >= 690 and b["y"] == 0
        ]
        self.assertGreaterEqual(len(window_candidates), 1, "Expected outer browser window to be preserved in hierarchy")

    def test_workspace_and_monitor_filtering(self):
        img = np.full((600, 800, 3), 30, dtype=np.uint8)
        path = self._save_img("ws_test.png", img)
        clients_json = os.path.join(self.temp_dir.name, "clients_ws.json")
        import json
        with open(clients_json, "w") as f:
            json.dump([
                # Inactive workspace 1 (two tiled terminals)
                {"at": [0, 0], "size": [400, 600], "workspace": {"id": 1}, "title": "kitty1", "class": "kitty"},
                {"at": [400, 0], "size": [400, 600], "workspace": {"id": 1}, "title": "kitty2", "class": "kitty"},
                # Active workspace 2 (full browser)
                {"at": [0, 0], "size": [800, 600], "workspace": {"id": 2}, "title": "LibreWolf", "class": "librewolf"},
                # Inactive workspace 3 but PINNED (should be visible)
                {"at": [50, 50], "size": [200, 200], "workspace": {"id": 3}, "pinned": True, "title": "Picture-in-Picture"},
                # Window on another monitor (at 1920, 0)
                {"at": [1920, 0], "size": [800, 600], "workspace": {"id": 2}, "title": "OtherMon"}
            ], f)

        # Run with SMARTSHOT_WORKSPACE_ID=2, SMARTSHOT_MONITOR_X=0, SMARTSHOT_MONITOR_Y=0
        old_env = os.environ.copy()
        try:
            os.environ["SMARTSHOT_WORKSPACE_ID"] = "2"
            os.environ["SMARTSHOT_MONITOR_X"] = "0"
            os.environ["SMARTSHOT_MONITOR_Y"] = "0"

            res = detect_ui_elements(path, clients_path=clients_json)
            client_boxes = [b for b in res["boxes"] if b.get("is_client")]

            titles = [b.get("title") for b in client_boxes]
            self.assertIn("LibreWolf", titles, "Active workspace window should be included")
            self.assertIn("Picture-in-Picture", titles, "Pinned window should be included regardless of workspace")
            self.assertNotIn("kitty1", titles, "Inactive workspace window must NOT be included")
            self.assertNotIn("kitty2", titles, "Inactive workspace window must NOT be included")
            self.assertNotIn("OtherMon", titles, "Off-monitor window must NOT be included")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_workspace_filtering_active_and_pinned(self):
        img = np.full((600, 800, 3), 30, dtype=np.uint8)
        path = self._save_img("ws_active.png", img)
        clients_json = os.path.join(self.temp_dir.name, "clients_active.json")
        import json
        with open(clients_json, "w") as f:
            json.dump([
                {"at": [0, 0], "size": [400, 600], "workspace": {"id": 1}, "title": "term_split_left", "class": "kitty"},
                {"at": [400, 0], "size": [400, 600], "workspace": {"id": 1}, "title": "term_split_right", "class": "kitty"},
                {"at": [0, 0], "size": [800, 600], "workspace": {"id": 2}, "title": "active_browser", "class": "firefox"},
                {"at": [100, 100], "size": [250, 200], "workspace": {"id": 3}, "pinned": True, "title": "pip_player"},
                {"at": [50, 50], "size": [300, 300], "workspace": {"id": 2}, "hidden": True, "title": "hidden_window"},
                {"at": [50, 50], "size": [300, 300], "workspace": {"id": 2}, "mapped": False, "title": "unmapped_window"},
                {"at": [1920, 0], "size": [800, 600], "workspace": {"id": 2}, "title": "offscreen_window"}
            ], f)

        old_env = os.environ.copy()
        try:
            os.environ["SMARTSHOT_WORKSPACE_ID"] = "2"
            os.environ["SMARTSHOT_MONITOR_X"] = "0"
            os.environ["SMARTSHOT_MONITOR_Y"] = "0"

            res = detect_ui_elements(path, clients_path=clients_json)
            client_boxes = [b for b in res["boxes"] if b.get("is_client")]
            titles = [b.get("title") for b in client_boxes]

            self.assertIn("active_browser", titles, "Active workspace window should be included")
            self.assertIn("pip_player", titles, "Pinned window should be included regardless of workspace")
            self.assertNotIn("term_split_left", titles, "Inactive workspace window must be excluded")
            self.assertNotIn("term_split_right", titles, "Inactive workspace window must be excluded")
            self.assertNotIn("hidden_window", titles, "Hidden window must be excluded")
            self.assertNotIn("unmapped_window", titles, "Unmapped window must be excluded")
            self.assertNotIn("offscreen_window", titles, "Off-monitor window must be excluded")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_workspace_filtering_unset_retains_all(self):
        img = np.full((600, 800, 3), 30, dtype=np.uint8)
        path = self._save_img("ws_unset.png", img)
        clients_json = os.path.join(self.temp_dir.name, "clients_unset.json")
        import json
        with open(clients_json, "w") as f:
            json.dump([
                {"at": [0, 0], "size": [400, 600], "workspace": {"id": 1}, "title": "term_ws1"},
                {"at": [400, 0], "size": [400, 600], "workspace": {"id": 2}, "title": "browser_ws2"},
            ], f)

        old_env = os.environ.copy()
        try:
            os.environ.pop("SMARTSHOT_WORKSPACE_ID", None)
            os.environ["SMARTSHOT_MONITOR_X"] = "0"
            os.environ["SMARTSHOT_MONITOR_Y"] = "0"

            res = detect_ui_elements(path, clients_path=clients_json)
            client_boxes = [b for b in res["boxes"] if b.get("is_client")]
            titles = [b.get("title") for b in client_boxes]

            self.assertIn("term_ws1", titles, "When workspace ID is unset, ws1 window should be retained")
            self.assertIn("browser_ws2", titles, "When workspace ID is unset, ws2 window should be retained")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_cluster_adjacent_columns_with_gutter_gap(self):
        col1 = {"x": 50, "y": 100, "w": 380, "h": 500, "area": 190000, "type": "panel", "contrast": 30.0}
        col2 = {"x": 454, "y": 100, "w": 380, "h": 500, "area": 190000, "type": "panel", "contrast": 30.0} # gap = 24px

        unions = cluster_adjacent_columns([col1, col2])
        self.assertEqual(len(unions), 1, "Columns separated by 24px gutter should cluster into union")
        u = unions[0]
        self.assertEqual(u["x"], 50)
        self.assertEqual(u["y"], 100)
        self.assertEqual(u["w"], 784)
        self.assertEqual(u["h"], 500)

    def test_cluster_adjacent_columns_exceeding_gap_threshold(self):
        col1 = {"x": 50, "y": 100, "w": 300, "h": 500, "area": 150000, "type": "panel", "contrast": 30.0}
        col2 = {"x": 410, "y": 100, "w": 300, "h": 500, "area": 150000, "type": "panel", "contrast": 30.0} # gap = 60px > 40px

        unions = cluster_adjacent_columns([col1, col2])
        self.assertEqual(len(unions), 0, "Columns separated by >40px margin should not cluster")

    def test_cluster_adjacent_columns_height_mismatch(self):
        col1 = {"x": 50, "y": 100, "w": 400, "h": 600, "area": 240000, "type": "panel", "contrast": 30.0}
        col2 = {"x": 450, "y": 300, "w": 400, "h": 300, "area": 120000, "type": "panel", "contrast": 30.0}

        unions = cluster_adjacent_columns([col1, col2])
        self.assertEqual(len(unions), 0, "Panels with different heights/offsets should not cluster")

    def test_browser_content_viewport_offset_window(self):
        gray = np.full((700, 1000), 240, dtype=np.uint8)
        # Window at (100, 50, 800, 600), header from y=50 to y=120
        gray[50:120, 100:900] = 35
        client_box = [{"x": 100, "y": 50, "w": 800, "h": 600, "title": "Chromium", "class": "chromium"}]

        content_boxes = detect_window_content_areas(gray, client_box)
        self.assertGreaterEqual(len(content_boxes), 1)
        cb = content_boxes[0]
        self.assertEqual(cb["x"], 100)
        self.assertEqual(cb["w"], 800)
        self.assertTrue(118 <= cb["y"] <= 122)
        self.assertTrue(528 <= cb["h"] <= 532)

    def test_browser_content_viewport_no_demarcation(self):
        gray = np.full((600, 800), 230, dtype=np.uint8)
        client_box = [{"x": 0, "y": 0, "w": 800, "h": 600, "title": "Terminal", "class": "foot"}]

        content_boxes = detect_window_content_areas(gray, client_box)
        self.assertEqual(len(content_boxes), 0, "Uniform window should produce no content viewport")

    def test_browser_content_viewport_small_window_ignored(self):
        gray = np.full((400, 500), 230, dtype=np.uint8)
        gray[0:60, :] = 40
        client_box = [{"x": 0, "y": 0, "w": 250, "h": 180, "title": "Popup", "class": "popup"}]

        content_boxes = detect_window_content_areas(gray, client_box)
        self.assertEqual(len(content_boxes), 0, "Windows smaller than 300x200 should be ignored")

    def test_browser_split_page_body_e2e_coexistence(self):
        img = np.full((700, 1000, 3), 40, dtype=np.uint8)
        cv2.rectangle(img, (20, 80), (500, 680), (255, 255, 255), -1)
        cv2.rectangle(img, (20, 80), (500, 680), (180, 180, 180), 1)
        cv2.rectangle(img, (500, 80), (980, 680), (245, 245, 245), -1)
        cv2.rectangle(img, (500, 80), (980, 680), (180, 180, 180), 1)

        path = self._save_img("browser_e2e.png", img)
        clients_json = os.path.join(self.temp_dir.name, "clients_e2e.json")
        import json
        with open(clients_json, "w") as f:
            json.dump([{"at": [0, 0], "size": [1000, 700], "title": "Web Browser", "class": "zen-browser", "workspace": {"id": 1}}], f)

        old_env = os.environ.copy()
        try:
            os.environ["SMARTSHOT_WORKSPACE_ID"] = "1"
            os.environ["SMARTSHOT_MONITOR_X"] = "0"
            os.environ["SMARTSHOT_MONITOR_Y"] = "0"

            res = detect_ui_elements(path, clients_path=clients_json)
            boxes = res["boxes"]

            # 1. Full browser window exists
            win_boxes = [b for b in boxes if b.get("is_client") and b["w"] == 1000 and b["h"] == 700]
            self.assertEqual(len(win_boxes), 1, "Browser window should be detected")

            # 2. Both columns exist
            left_col = [b for b in boxes if abs(b["x"] - 20) <= 8 and abs(b["y"] - 80) <= 8 and abs(b["w"] - 480) <= 16]
            right_col = [b for b in boxes if abs(b["x"] - 500) <= 8 and abs(b["y"] - 80) <= 8 and abs(b["w"] - 480) <= 16]
            self.assertGreaterEqual(len(left_col), 1, "Left column candidate should be detected")
            self.assertGreaterEqual(len(right_col), 1, "Right column candidate should be detected")

            # 3. Web page body / viewport candidate exists below the toolbar (y ~ 80, not y=0!)
            body_candidates = [
                b for b in boxes
                if 60 <= b["y"] <= 95 and b["w"] >= 850 and b["h"] >= 500
            ]
            self.assertGreaterEqual(len(body_candidates), 1, "Expected full web page body candidate below toolbar to be detected and preserved")

            # 4. Hierarchy depth check: window (depth 0) < page body (depth 1) <= columns (depth 2+)
            self.assertEqual(win_boxes[0]["depth"], 0, "Browser window should be depth 0")
            self.assertGreater(body_candidates[0]["depth"], win_boxes[0]["depth"], "Body viewport must be deeper than window")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

if __name__ == "__main__":
    unittest.main()
