#!/usr/bin/env python3
"""
Empirical Stress Test Harness for Web Page Body & Column Detection (R2 Part B)
Author: Challenger M1-2
Target: vision/detect_ui.py
"""

import os
import sys
import json
import unittest
import tempfile
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import cv2
    from vision.detect_ui import (
        detect_ui_elements,
        deduplicate_boxes,
        cluster_adjacent_columns,
        detect_window_content_areas,
        compute_iou,
        compute_containment,
    )
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class TestBrowserDetectionStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_CV2:
            raise unittest.SkipTest("OpenCV or NumPy not installed in current environment")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _save_img(self, name, img):
        path = os.path.join(self.temp_dir.name, name)
        cv2.imwrite(path, img)
        return path

    def _save_clients(self, name, clients):
        path = os.path.join(self.temp_dir.name, name)
        with open(path, "w") as f:
            json.dump(clients, f)
        return path

    # =========================================================================
    # SCENARIO 1: Viewport & Client Window Deduplication Resilience
    # =========================================================================

    def test_dedup_never_swallows_viewport_into_client_window(self):
        """
        Direct stress test on deduplicate_boxes():
        Ensure that client window NEVER merges with inner content viewport,
        across a wide range of window dimensions, toolbar heights, and positions.
        """
        for win_w, win_h in [(800, 600), (1280, 800), (1920, 1080), (2560, 1440), (3840, 2160)]:
            for tb_h in [40, 50, 65, 75, 80, 95, 120, 150]:
                for win_x, win_y in [(0, 0), (100, 80), (350, 200)]:
                    client_box = {
                        "x": win_x,
                        "y": win_y,
                        "w": win_w,
                        "h": win_h,
                        "area": win_w * win_h,
                        "type": "window",
                        "is_client": True,
                        "extent": 1.0,
                    }
                    viewport_box = {
                        "x": win_x,
                        "y": win_y + tb_h,
                        "w": win_w,
                        "h": win_h - tb_h,
                        "area": win_w * (win_h - tb_h),
                        "type": "panel",
                        "is_client": False,
                        "extent": 1.0,
                    }

                    # Test with both [client, viewport] and [viewport, client] input ordering
                    for boxes_input in [[client_box, viewport_box], [viewport_box, client_box]]:
                        deduped = deduplicate_boxes(boxes_input)
                        self.assertEqual(
                            len(deduped),
                            2,
                            f"deduplicate_boxes merged client and viewport! win=({win_w}x{win_h}), tb={tb_h}, pos=({win_x},{win_y})",
                        )
                        # Verify both boxes retain their distinct vertical boundaries
                        has_full = any(b["y"] == win_y and b["h"] == win_h for b in deduped)
                        has_body = any(b["y"] == win_y + tb_h and b["h"] == win_h - tb_h for b in deduped)
                        self.assertTrue(has_full, "Full window was lost or modified during deduplication")
                        self.assertTrue(has_body, "Body viewport was swallowed during deduplication")

    def test_dedup_pure_cv_fallback_distinct_structural_regions(self):
        """
        Test deduplicate_boxes when neither box has is_client (pure CV fallback).
        Max edge difference > 25px must preserve distinct structural regions
        like window vs page body even if IoU/containment is high.
        """
        win = {
            "x": 0, "y": 0, "w": 1000, "h": 700, "area": 700000, "type": "panel", "extent": 1.0
        }
        # Viewport starting below toolbar (tb_h = 42px > 25px)
        viewport = {
            "x": 0, "y": 42, "w": 1000, "h": 658, "area": 658000, "type": "panel", "extent": 1.0
        }
        deduped = deduplicate_boxes([win, viewport])
        self.assertEqual(len(deduped), 2, "Pure CV window and viewport must not merge when edge diff > 25px")

    def test_dedup_multi_window_viewports_coexistence(self):
        """
        Test multiple windows side by side (e.g. two tiled browser windows),
        each having its own content viewport.
        """
        win1 = {"x": 0, "y": 0, "w": 960, "h": 1080, "area": 960 * 1080, "type": "window", "is_client": True}
        vp1 = {"x": 0, "y": 80, "w": 960, "h": 1000, "area": 960 * 1000, "type": "panel", "is_client": False}
        win2 = {"x": 960, "y": 0, "w": 960, "h": 1080, "area": 960 * 1080, "type": "window", "is_client": True}
        vp2 = {"x": 960, "y": 80, "w": 960, "h": 1000, "area": 960 * 1000, "type": "panel", "is_client": False}

        deduped = deduplicate_boxes([win1, vp1, win2, vp2])
        self.assertEqual(len(deduped), 4, f"Expected 4 distinct boxes for two side-by-side browser windows, got {len(deduped)}")

    # =========================================================================
    # SCENARIO 2: Diverse Browser Mockups & Layout Topologies
    # =========================================================================

    def test_browser_2column_equal_split(self):
        """2-column 50/50 split layout with 20px margins and 80px dark toolbar."""
        w, h = 1200, 800
        img = np.full((h, w, 3), 40, dtype=np.uint8)  # Toolbar chrome
        # Left col: x=30 to 580 (w=550), y=80 to 760 (h=680)
        cv2.rectangle(img, (30, 80), (580, 760), (250, 250, 250), -1)
        cv2.rectangle(img, (30, 80), (580, 760), (190, 190, 190), 2)
        # Right col: x=620 to 1170 (w=550), y=80 to 760 (h=680)
        cv2.rectangle(img, (620, 80), (1170, 760), (240, 240, 240), -1)
        cv2.rectangle(img, (620, 80), (1170, 760), (190, 190, 190), 2)

        img_path = self._save_img("browser_2col.png", img)
        clients_path = self._save_clients("clients_2col.json", [
            {"at": [0, 0], "size": [w, h], "title": "Browser 2Col", "class": "firefox"}
        ])

        res = detect_ui_elements(img_path, clients_path=clients_path)
        boxes = res["boxes"]

        # 1. Full browser window candidate
        win = [b for b in boxes if b.get("is_client") and b["w"] == w and b["h"] == h]
        self.assertEqual(len(win), 1, "Outer window must be present")

        # 2. Page body viewport below toolbar (starts near y=80, spans full width)
        body = [b for b in boxes if 70 <= b["y"] <= 90 and b["w"] >= 1100 and b["h"] >= 650]
        self.assertGreaterEqual(len(body), 1, "Full web page body viewport below toolbar must be detected")

        # 3. Individual columns
        left_col = [b for b in boxes if abs(b["x"] - 30) <= 8 and abs(b["y"] - 80) <= 8 and abs(b["w"] - 550) <= 15]
        right_col = [b for b in boxes if abs(b["x"] - 620) <= 8 and abs(b["y"] - 80) <= 8 and abs(b["w"] - 550) <= 15]
        self.assertGreaterEqual(len(left_col), 1, "Left column must be detected")
        self.assertGreaterEqual(len(right_col), 1, "Right column must be detected")

    def test_browser_3column_layout(self):
        """
        3-column web page: Left nav (250px), Main content (600px), Right sidebar (250px).
        Columns have 20px gutters.
        """
        w, h = 1200, 800
        img = np.full((h, w, 3), 35, dtype=np.uint8)  # dark chrome
        # Left nav: x=20, w=250, y=75, h=700 -> (20, 75, 270, 775)
        cv2.rectangle(img, (20, 75), (270, 775), (235, 235, 235), -1)
        cv2.rectangle(img, (20, 75), (270, 775), (180, 180, 180), 2)
        # Main content: x=290, w=580, y=75, h=700 -> (290, 75, 870, 775)
        cv2.rectangle(img, (290, 75), (870, 775), (255, 255, 255), -1)
        cv2.rectangle(img, (290, 75), (870, 775), (180, 180, 180), 2)
        # Right sidebar: x=890, w=290, y=75, h=700 -> (890, 75, 1180, 775)
        cv2.rectangle(img, (890, 75), (1180, 775), (240, 240, 240), -1)
        cv2.rectangle(img, (890, 75), (1180, 775), (180, 180, 180), 2)

        img_path = self._save_img("browser_3col.png", img)
        clients_path = self._save_clients("clients_3col.json", [
            {"at": [0, 0], "size": [w, h], "title": "3-Column Page", "class": "chromium"}
        ])

        res = detect_ui_elements(img_path, clients_path=clients_path)
        boxes = res["boxes"]

        # Viewport covering the full page body below the toolbar
        body = [b for b in boxes if 65 <= b["y"] <= 85 and b["w"] >= 1100 and b["h"] >= 680]
        self.assertGreaterEqual(len(body), 1, "Full 3-column page body viewport must be detected")

        # Columns detected
        cols = [b for b in boxes if abs(b["y"] - 75) <= 8 and abs(b["h"] - 700) <= 15 and b.get("type") in ("panel", "detected")]
        self.assertGreaterEqual(len(cols), 3, f"All 3 columns should be detected as candidate panels, got {len(cols)}")

    def test_asymmetrical_columns_clustering(self):
        """
        Asymmetrical columns: Sidebar (280px) + Main content (700px), gutter = 20px.
        Tests cluster_adjacent_columns() handling of unequal column widths.
        """
        col_nav = {"x": 50, "y": 80, "w": 280, "h": 600, "area": 280 * 600, "type": "panel", "contrast": 30.0}
        col_main = {"x": 350, "y": 80, "w": 700, "h": 600, "area": 700 * 600, "type": "panel", "contrast": 30.0}

        unions = cluster_adjacent_columns([col_nav, col_main])
        self.assertEqual(len(unions), 1, "Asymmetrical columns (280px + 700px) must cluster into composite container")
        u = unions[0]
        self.assertEqual(u["x"], 50)
        self.assertEqual(u["y"], 80)
        self.assertEqual(u["w"], 1000)
        self.assertEqual(u["h"], 600)

    def test_diverse_gutter_widths(self):
        """
        Test column clustering across diverse gutter margins:
        0px (divider line), 10px, 20px, 30px, 40px (boundary max), 42px (beyond max).
        """
        for gutter in [0, 10, 20, 30, 40]:
            col1 = {"x": 100, "y": 100, "w": 300, "h": 500, "area": 150000, "type": "panel", "contrast": 25.0}
            col2 = {"x": 100 + 300 + gutter, "y": 100, "w": 300, "h": 500, "area": 150000, "type": "panel", "contrast": 25.0}
            unions = cluster_adjacent_columns([col1, col2])
            self.assertEqual(
                len(unions),
                1,
                f"Columns with gutter={gutter}px failed to cluster into union! Got: {unions}",
            )
            self.assertEqual(unions[0]["w"], 600 + gutter)

        # Gutter > 40px must NOT cluster
        col1 = {"x": 100, "y": 100, "w": 300, "h": 500, "area": 150000, "type": "panel", "contrast": 25.0}
        col2 = {"x": 100 + 300 + 45, "y": 100, "w": 300, "h": 500, "area": 150000, "type": "panel", "contrast": 25.0}
        unions = cluster_adjacent_columns([col1, col2])
        self.assertEqual(len(unions), 0, "Columns separated by 45px (>40px) must not cluster")

    def test_subtle_gradient_toolbar_demarcation(self):
        """
        Test header demarcation when the toolbar has a subtle gradient from top to bottom:
        e.g. y=0 to y=69 is gradient from 60 to 45 (diff per row is ~0.2),
        followed by page body at y=70 (pixel value 220, row diff = 175).
        """
        w, h = 900, 600
        gray = np.full((h, w), 220, dtype=np.uint8)  # White/light page body
        # Gradient toolbar
        for y in range(70):
            val = int(60 - (y / 70.0) * 15)
            gray[y, :] = val

        client_box = [{"x": 0, "y": 0, "w": w, "h": h, "title": "Gradient Chrome", "class": "zen"}]
        content_boxes = detect_window_content_areas(gray, client_box)

        self.assertGreaterEqual(len(content_boxes), 1, "Content viewport must be detected below gradient toolbar")
        cb = content_boxes[0]
        self.assertEqual(cb["x"], 0)
        self.assertEqual(cb["w"], w)
        self.assertTrue(68 <= cb["y"] <= 72, f"Expected demarcation near y=70, got {cb['y']}")
        self.assertTrue(528 <= cb["h"] <= 532, f"Expected height near 530, got {cb['h']}")

    def test_dark_mode_subtle_contrast_demarcation(self):
        """
        Test dark-mode browser where toolbar is (42, 42, 42) and page body is (28, 28, 28)
        with a 1px boundary line of (60, 60, 60).
        """
        w, h = 1000, 700
        gray = np.full((h, w), 28, dtype=np.uint8)  # Dark page body
        gray[0:65, :] = 42  # Dark toolbar
        gray[64, :] = 60    # 1px border separator

        client_box = [{"x": 0, "y": 0, "w": w, "h": h, "title": "Dark Mode Browser", "class": "firefox"}]
        content_boxes = detect_window_content_areas(gray, client_box)

        self.assertGreaterEqual(len(content_boxes), 1, "Content viewport must be detected in dark mode")
        cb = content_boxes[0]
        self.assertTrue(63 <= cb["y"] <= 67, f"Expected demarcation near y=65, got {cb['y']}")

    def test_multi_tier_browser_header_hierarchy(self):
        """
        Mock realistic browser chrome with 3 tiers:
        - Tab bar: y=0..36 (color 35)
        - URL bar: y=36..80 (color 45)
        - Bookmark bar: y=80..110 (color 50)
        - Web page content: y=110..800 (color 240)
        Detects that the demarcation correctly isolates the web page body (y=110),
        and verifies hierarchy depth calculation.
        """
        w, h = 1200, 800
        img = np.full((h, w, 3), 240, dtype=np.uint8)  # White page content
        img[0:36, :] = 35   # Tab bar
        img[36:80, :] = 45  # URL bar
        img[80:110, :] = 50 # Bookmark bar

        # Two columns inside web page
        cv2.rectangle(img, (40, 130), (580, 750), (255, 255, 255), -1)
        cv2.rectangle(img, (40, 130), (580, 750), (180, 180, 180), 2)
        cv2.rectangle(img, (620, 130), (1160, 750), (255, 255, 255), -1)
        cv2.rectangle(img, (620, 130), (1160, 750), (180, 180, 180), 2)

        img_path = self._save_img("multitier_chrome.png", img)
        clients_path = self._save_clients("clients_multitier.json", [
            {"at": [0, 0], "size": [w, h], "title": "Multi-tier Browser", "class": "brave"}
        ])

        res = detect_ui_elements(img_path, clients_path=clients_path)
        boxes = res["boxes"]

        # Viewport candidate below the bookmark bar (near y=110)
        body = [b for b in boxes if 105 <= b["y"] <= 115 and b["w"] >= 1150]
        self.assertGreaterEqual(len(body), 1, "Page body viewport below bookmark bar must be detected")

        # Check hierarchy depths: window (0) < viewport (1) <= columns (2+)
        win = next(b for b in boxes if b.get("is_client") and b["w"] == w and b["h"] == h)
        body_box = body[0]
        self.assertEqual(win["depth"], 0)
        self.assertGreater(body_box["depth"], win["depth"])

    def test_degenerate_and_malformed_clients_json(self):
        """
        Stress test detect_ui_elements with corrupt/malformed clients.json:
        - string instead of list
        - dict instead of list
        - list with non-dict elements (integers, nulls, empty strings)
        - dicts missing 'at' or 'size' or invalid types
        Detector must handle gracefully without crashing.
        """
        w, h = 600, 400
        img = np.full((h, w, 3), 40, dtype=np.uint8)
        img_path = self._save_img("malformed_test.png", img)

        malformed_payloads = [
            "This is just a raw string, not JSON list",
            {"at": [0, 0], "size": [600, 400]},
            [None, 123, "string", [], {}],
            [{"at": "invalid", "size": [600, 400]}],
            [{"at": [0, 0], "size": "invalid"}],
            [{"at": [0], "size": [600, 400]}],
            [{"at": [0, 0], "size": [600]}],
            [{"at": [float("nan"), 0], "size": [600, 400]}],
        ]

        for idx, payload in enumerate(malformed_payloads):
            clients_path = os.path.join(self.temp_dir.name, f"malformed_{idx}.json")
            with open(clients_path, "w") as f:
                json.dump(payload, f)

            # Must run cleanly without throwing exceptions
            res = detect_ui_elements(img_path, clients_path=clients_path)
            self.assertIsInstance(res, dict)
            self.assertIn("boxes", res)


    # =========================================================================
    # SCENARIO 3: Coordinate Bounds Clamping & Dimensions Rigorous Checks
    # =========================================================================

    def test_coordinate_bounds_clamping_strict_invariants(self):
        """
        Verify that ALL output boxes from detect_ui_elements strictly satisfy:
        1. 0 <= x < screen_width
        2. 0 <= y < screen_height
        3. x + w <= screen_width
        4. y + h <= screen_height
        5. w > 0 and h > 0 and area == w * h
        under diverse adversarial client window scenarios (off-screen, negative coords, scale factors).
        """
        w_img, h_img = 800, 600
        img = np.full((h_img, w_img, 3), 50, dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (400, 300), (200, 200, 200), 2)
        img_path = self._save_img("clamping_test.png", img)

        adversarial_clients = [
            # Partially off-screen left and top
            {"at": [-200, -100], "size": [500, 400], "title": "OffLeftTop"},
            # Partially off-screen right
            {"at": [600, 100], "size": [400, 300], "title": "OffRight"},
            # Partially off-screen bottom
            {"at": [100, 500], "size": [300, 300], "title": "OffBottom"},
            # Completely off-screen (should be dropped or clamped out)
            {"at": [-1000, -1000], "size": [200, 200], "title": "CompletelyOffLeft"},
            {"at": [2000, 2000], "size": [200, 200], "title": "CompletelyOffRight"},
            # Window spanning entire display and beyond
            {"at": [-50, -50], "size": [900, 700], "title": "SuperWindow"},
        ]
        clients_path = self._save_clients("adversarial_clients.json", adversarial_clients)

        # Test across multiple scale factors and monitor offsets
        for scale in [0.75, 1.0, 1.25, 1.5, 2.0]:
            for offset_x, offset_y in [(0, 0), (100, 50), (-50, -50)]:
                old_env = os.environ.copy()
                try:
                    os.environ["SMARTSHOT_MONITOR_SCALE"] = str(scale)
                    os.environ["SMARTSHOT_MONITOR_X"] = str(offset_x)
                    os.environ["SMARTSHOT_MONITOR_Y"] = str(offset_y)

                    res = detect_ui_elements(img_path, clients_path=clients_path)
                    boxes = res["boxes"]

                    for idx, b in enumerate(boxes):
                        bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
                        # Invariant 1 & 2: Non-negative coordinates
                        self.assertGreaterEqual(bx, 0, f"Box {idx} negative x: {b}")
                        self.assertGreaterEqual(by, 0, f"Box {idx} negative y: {b}")
                        # Invariant 3 & 4: Never exceed screen boundaries
                        self.assertLessEqual(bx + bw, w_img, f"Box {idx} exceeds screen width: {b} in {w_img}x{h_img}")
                        self.assertLessEqual(by + bh, h_img, f"Box {idx} exceeds screen height: {b} in {w_img}x{h_img}")
                        # Invariant 5: Positive non-zero dimensions
                        self.assertGreater(bw, 0, f"Box {idx} non-positive width: {b}")
                        self.assertGreater(bh, 0, f"Box {idx} non-positive height: {b}")
                        self.assertEqual(b["area"], bw * bh, f"Box {idx} area mismatch: {b}")
                        # Invariant 6: Integer coordinates
                        self.assertIsInstance(bx, int)
                        self.assertIsInstance(by, int)
                        self.assertIsInstance(bw, int)
                        self.assertIsInstance(bh, int)
                finally:
                    os.environ.clear()
                    os.environ.update(old_env)

    def test_stress_harness_random_adversarial_boxes_fuzzing(self):
        """
        Fuzz deduplicate_boxes() with 1,000 randomized bounding boxes
        having wild scales, negative coordinates, float values, concentric boxes,
        and extreme aspect ratios.
        Ensure deduplicate_boxes() never crashes, raises exceptions, or creates invalid areas.
        """
        np.random.seed(42)
        random_boxes = []
        for i in range(1000):
            x = int(np.random.randint(-500, 2500))
            y = int(np.random.randint(-500, 1500))
            w = int(np.random.randint(1, 1000))
            h = int(np.random.randint(1, 1000))
            is_cl = bool(np.random.choice([True, False]))
            box_type = np.random.choice(["window", "floating_window", "panel", "slot", "detected", "grid_container"])
            random_boxes.append({
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "area": w * h,
                "is_client": is_cl,
                "type": box_type,
                "extent": float(np.random.uniform(0.5, 1.0))
            })

        deduped = deduplicate_boxes(random_boxes)
        self.assertIsInstance(deduped, list)
        self.assertGreater(len(deduped), 0)
        self.assertLessEqual(len(deduped), len(random_boxes))

        for b in deduped:
            self.assertGreater(b["w"], 0)
            self.assertGreater(b["h"], 0)
            self.assertEqual(b["area"], b["w"] * b["h"])


if __name__ == "__main__":
    unittest.main()
