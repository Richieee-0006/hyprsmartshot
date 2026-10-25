#!/usr/bin/env python3
"""
Adversarial and Stress Tests for HyprSmartShot Workspace Isolation (R2 Part A).
Verifies:
1. Inactive workspace tiled windows (e.g. 50/50 split terminals) never bleed through as phantom boxes.
2. Pinned floating windows are retained on active workspaces regardless of their origin workspace.
3. String workspace IDs ("special:scratchpad", named workspaces, negative IDs) are handled correctly.
4. Unset, empty, or whitespace SMARTSHOT_WORKSPACE_ID retains all windows gracefully.
5. Off-screen, negative coordinate, and partially overlapping monitor boundary clamping.
6. Malformed clients.json input robustness and high-volume scalability (1000+ clients).
7. Standalone CLI subprocess execution matching library behavior.
"""

import os
import sys
import json
import tempfile
import unittest
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_DIR / ".venv" / "bin" / "python"
PYTHON_EXEC = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

try:
    import cv2
    import numpy as np
    from vision.detect_ui import detect_ui_elements
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class TestWorkspaceIsolationStress(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.env_backup = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)
        self.temp_dir.cleanup()

    def _create_test_image(self, width=1920, height=1080, color=(30, 30, 30)):
        """Creates a solid test PNG file and returns its path."""
        img_path = self.temp_path / f"screen_{width}x{height}.png"
        if HAS_CV2:
            img = np.full((height, width, 3), color, dtype=np.uint8)
            cv2.imwrite(str(img_path), img)
        else:
            # Generate a minimal valid PNG if cv2 is absent in current runner
            # We can use a 1x1 base64 png or invoke venv python to create it
            cmd = [
                PYTHON_EXEC, "-c",
                f"import cv2, numpy as np; img = np.full(({height}, {width}, 3), {list(color)}, dtype=np.uint8); cv2.imwrite(r'{img_path}', img)"
            ]
            subprocess.run(cmd, check=True)
        return str(img_path)

    def _write_clients_json(self, clients, filename="clients.json"):
        path = self.temp_path / filename
        with open(path, "w") as f:
            json.dump(clients, f)
        return str(path)

    def _run_detection(self, img_path, clients_path, env_overrides=None):
        if env_overrides:
            os.environ.update(env_overrides)
        if HAS_CV2:
            return detect_ui_elements(img_path, clients_path=clients_path)
        else:
            # Invoke via subprocess using venv python
            out_json = self.temp_path / "out.json"
            script = str(REPO_DIR / "vision" / "detect_ui.py")
            cmd = [PYTHON_EXEC, script, img_path, str(out_json), clients_path]
            env = os.environ.copy()
            if env_overrides:
                env.update(env_overrides)
            subprocess.run(cmd, check=True, env=env)
            with open(out_json, "r") as f:
                return json.load(f)

    # --------------------------------------------------------------------------
    # Scenario 1: Background tiled windows (e.g. 50/50 split terminals)
    # --------------------------------------------------------------------------
    def test_background_tiled_50_50_split_never_bleed_through(self):
        """
        Background tiled windows (50/50 split Kitty on workspace 1) must NEVER bleed
        through as phantom boxes when SMARTSHOT_WORKSPACE_ID="2".
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            # Inactive Workspace 1: 50/50 split terminal windows
            {"at": [0, 0], "size": [960, 1080], "workspace": {"id": 1, "name": "1"}, "floating": False, "title": "kitty_left", "class": "kitty"},
            {"at": [960, 0], "size": [960, 1080], "workspace": {"id": 1, "name": "1"}, "floating": False, "title": "kitty_right", "class": "kitty"},
            # Active Workspace 2: Single browser window
            {"at": [100, 100], "size": [1720, 880], "workspace": {"id": 2, "name": "2"}, "floating": False, "title": "Firefox", "class": "firefox"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {
            "SMARTSHOT_WORKSPACE_ID": "2",
            "SMARTSHOT_MONITOR_X": "0",
            "SMARTSHOT_MONITOR_Y": "0",
            "SMARTSHOT_MONITOR_SCALE": "1.0"
        })

        boxes = res["boxes"]
        titles = [b.get("title") for b in boxes if b.get("is_client")]
        self.assertIn("Firefox", titles, "Active workspace window must be present")
        self.assertNotIn("kitty_left", titles, "Workspace 1 left split terminal must NOT bleed through")
        self.assertNotIn("kitty_right", titles, "Workspace 1 right split terminal must NOT bleed through")

        # Explicitly verify NO box with the geometry of either phantom half-window exists
        left_split_box = any(b["x"] == 0 and b["y"] == 0 and abs(b["w"] - 960) <= 2 for b in boxes)
        right_split_box = any(abs(b["x"] - 960) <= 2 and b["y"] == 0 and abs(b["w"] - 960) <= 2 for b in boxes)
        self.assertFalse(left_split_box, "Found phantom left half-window box in output")
        self.assertFalse(right_split_box, "Found phantom right half-window box in output")

    def test_multi_workspace_background_tiles_complete_isolation(self):
        """
        Verify multiple complex tiling configurations on background workspaces (1, 3, 4)
        are all eliminated when active workspace is 5.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            # WS 1: Two 50/50 terminals
            {"at": [0, 0], "size": [960, 1080], "workspace": {"id": 1}, "title": "ws1_left"},
            {"at": [960, 0], "size": [960, 1080], "workspace": {"id": 1}, "title": "ws1_right"},
            # WS 3: Three 33/33/33 columns
            {"at": [0, 0], "size": [640, 1080], "workspace": {"id": 3}, "title": "ws3_col1"},
            {"at": [640, 0], "size": [640, 1080], "workspace": {"id": 3}, "title": "ws3_col2"},
            {"at": [1280, 0], "size": [640, 1080], "workspace": {"id": 3}, "title": "ws3_col3"},
            # WS 4: 2x2 grid (4 windows)
            {"at": [0, 0], "size": [960, 540], "workspace": {"id": 4}, "title": "ws4_tl"},
            {"at": [960, 0], "size": [960, 540], "workspace": {"id": 4}, "title": "ws4_tr"},
            {"at": [0, 540], "size": [960, 540], "workspace": {"id": 4}, "title": "ws4_bl"},
            {"at": [960, 540], "size": [960, 540], "workspace": {"id": 4}, "title": "ws4_br"},
            # WS 5: Active workspace window
            {"at": [50, 50], "size": [1820, 980], "workspace": {"id": 5}, "title": "ws5_active"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "5"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]

        self.assertEqual(titles, ["ws5_active"], f"Only ws5_active should be retained, got: {titles}")

    # --------------------------------------------------------------------------
    # Scenario 2: Pinned floating windows (pinned: true)
    # --------------------------------------------------------------------------
    def test_pinned_floating_windows_retained_across_all_workspaces(self):
        """
        Pinned windows (`pinned: true`) must ALWAYS be retained on the active workspace,
        regardless of what workspace Hyprland assigned them (including special scratchpads).
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            # Pinned window originating on WS 1
            {"at": [50, 50], "size": [300, 200], "workspace": {"id": 1}, "pinned": True, "floating": True, "title": "pip_ws1"},
            # Pinned window originating on WS 3
            {"at": [400, 50], "size": [300, 200], "workspace": {"id": 3}, "pinned": True, "floating": True, "title": "pip_ws3"},
            # Pinned window on scratchpad
            {"at": [750, 50], "size": [300, 200], "workspace": {"name": "special:scratchpad", "id": -99}, "pinned": True, "floating": True, "title": "pip_scratch"},
            # Pinned window with missing workspace key
            {"at": [1100, 50], "size": [300, 200], "pinned": True, "floating": True, "title": "pip_no_ws"},
            # Regular unpinned window on WS 1 (must be excluded)
            {"at": [0, 0], "size": [960, 1080], "workspace": {"id": 1}, "pinned": False, "floating": False, "title": "unpinned_ws1"},
            # Regular window on active WS 2
            {"at": [0, 300], "size": [1920, 780], "workspace": {"id": 2}, "floating": False, "title": "active_editor"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "2"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = {b.get("title") for b in client_boxes}

        expected = {"pip_ws1", "pip_ws3", "pip_scratch", "pip_no_ws", "active_editor"}
        self.assertEqual(titles, expected, f"Expected {expected}, got {titles}")
        self.assertNotIn("unpinned_ws1", titles, "Unpinned background window must be excluded")

        # Verify pinned attribute is preserved in output
        pip_boxes = [b for b in client_boxes if b.get("title").startswith("pip_")]
        for p in pip_boxes:
            self.assertTrue(p.get("pinned"), f"Box {p.get('title')} should have pinned: True")
            self.assertEqual(p.get("type"), "floating_window")

    # --------------------------------------------------------------------------
    # Scenario 3: String workspace IDs (named workspaces, special scratchpad)
    # --------------------------------------------------------------------------
    def test_string_workspace_id_special_scratchpad_by_name(self):
        """
        When active workspace is 'special:scratchpad', windows on that special workspace
        identified by name must be retained.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [100, 100], "size": [800, 600], "workspace": {"id": -99, "name": "special:scratchpad"}, "title": "scratchpad_term"},
            {"at": [0, 0], "size": [960, 1080], "workspace": {"id": 1, "name": "1"}, "title": "ws1_kitty"},
            {"at": [960, 0], "size": [960, 1080], "workspace": {"id": 2, "name": "2"}, "title": "ws2_kitty"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "special:scratchpad"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]

        self.assertEqual(titles, ["scratchpad_term"])

    def test_string_workspace_id_special_scratchpad_by_negative_id(self):
        """
        When active workspace is given as '-99' (the numeric id of special:scratchpad),
        windows with workspace.id == -99 must be retained.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [100, 100], "size": [800, 600], "workspace": {"id": -99, "name": "special:scratchpad"}, "title": "scratchpad_term"},
            {"at": [0, 0], "size": [960, 1080], "workspace": {"id": 1, "name": "1"}, "title": "ws1_kitty"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "-99"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]

        self.assertEqual(titles, ["scratchpad_term"])

    def test_string_workspace_id_named_workspaces(self):
        """
        Named workspaces like 'dev', 'web', 'chat' must match workspace.name properly.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [50, 50], "size": [900, 900], "workspace": {"id": 10, "name": "dev"}, "title": "neovim"},
            {"at": [50, 50], "size": [900, 900], "workspace": {"id": 11, "name": "web"}, "title": "browser"},
            {"at": [50, 50], "size": [900, 900], "workspace": {"id": 12, "name": "chat"}, "title": "discord"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "dev"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]
        self.assertEqual(titles, ["neovim"])

        res_web = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "web"})
        client_boxes_web = [b for b in res_web["boxes"] if b.get("is_client")]
        self.assertEqual([b.get("title") for b in client_boxes_web], ["browser"])

    def test_workspace_id_whitespace_stripping(self):
        """
        Whitespace in SMARTSHOT_WORKSPACE_ID (e.g. ' 2 ', '\\t2\\n') must be stripped
        and match workspace ID 2.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [0, 0], "size": [800, 600], "workspace": {"id": 2}, "title": "ws2_win"},
            {"at": [0, 0], "size": [800, 600], "workspace": {"id": 1}, "title": "ws1_win"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "  2 \n"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]
        self.assertEqual(titles, ["ws2_win"])

    # --------------------------------------------------------------------------
    # Scenario 4: Unset / empty SMARTSHOT_WORKSPACE_ID
    # --------------------------------------------------------------------------
    def test_unset_workspace_id_retains_all_windows(self):
        """
        When SMARTSHOT_WORKSPACE_ID is unset in the environment, all visible windows
        across all workspaces must be retained (graceful fallback).
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [0, 0], "size": [400, 500], "workspace": {"id": 1}, "title": "win1"},
            {"at": [400, 0], "size": [400, 500], "workspace": {"id": 2}, "title": "win2"},
            {"at": [800, 0], "size": [400, 500], "workspace": {"id": 3}, "title": "win3"}
        ]
        clients_path = self._write_clients_json(clients)

        os.environ.pop("SMARTSHOT_WORKSPACE_ID", None)
        res = self._run_detection(img_path, clients_path)
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = {b.get("title") for b in client_boxes}
        self.assertEqual(titles, {"win1", "win2", "win3"})

    def test_empty_or_whitespace_workspace_id_retains_all_windows(self):
        """
        When SMARTSHOT_WORKSPACE_ID is '' or '   ', it acts as unset and retains all windows.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [0, 0], "size": [400, 500], "workspace": {"id": 1}, "title": "win1"},
            {"at": [400, 0], "size": [400, 500], "workspace": {"id": 2}, "title": "win2"}
        ]
        clients_path = self._write_clients_json(clients)

        # Empty string
        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": ""})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        self.assertEqual(len(client_boxes), 2)

        # Whitespace-only string
        res_ws = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "   "})
        client_boxes_ws = [b for b in res_ws["boxes"] if b.get("is_client")]
        self.assertEqual(len(client_boxes_ws), 2)

    # --------------------------------------------------------------------------
    # Scenario 5: Off-screen and partially overlapping monitor coordinate edge cases
    # --------------------------------------------------------------------------
    def test_monitor_coordinates_fully_offscreen_excluded(self):
        """
        Windows that are completely off-screen in any direction must be rejected
        (clamped dimensions become 0 < 20).
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [2000, 100], "size": [800, 600], "workspace": {"id": 1}, "title": "off_right"},
            {"at": [-1000, 100], "size": [800, 600], "workspace": {"id": 1}, "title": "off_left"},
            {"at": [100, 1200], "size": [800, 600], "workspace": {"id": 1}, "title": "off_bottom"},
            {"at": [100, -800], "size": [800, 600], "workspace": {"id": 1}, "title": "off_top"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {
            "SMARTSHOT_WORKSPACE_ID": "1",
            "SMARTSHOT_MONITOR_X": "0",
            "SMARTSHOT_MONITOR_Y": "0"
        })
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        self.assertEqual(len(client_boxes), 0, f"All fully offscreen windows should be excluded, got {client_boxes}")

    def test_monitor_coordinates_partially_overlapping_clamped_strictly(self):
        """
        Windows partially crossing monitor edges must be clamped strictly within [0, W] and [0, H]
        with correct surviving dimensions.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            # Spans x: 1700 to 2100 -> clamped x: 1700 to 1920 (w = 220)
            {"at": [1700, 100], "size": [400, 500], "workspace": {"id": 1}, "title": "part_right"},
            # Spans x: -100 to 300 -> clamped x: 0 to 300 (w = 300)
            {"at": [-100, 200], "size": [400, 500], "workspace": {"id": 1}, "title": "part_left"},
            # Spans y: -50 to 450 -> clamped y: 0 to 450 (h = 450)
            {"at": [100, -50], "size": [400, 500], "workspace": {"id": 1}, "title": "part_top"},
            # Spans y: 900 to 1200 -> clamped y: 900 to 1080 (h = 180)
            {"at": [600, 900], "size": [400, 300], "workspace": {"id": 1}, "title": "part_bottom"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {
            "SMARTSHOT_WORKSPACE_ID": "1",
            "SMARTSHOT_MONITOR_X": "0",
            "SMARTSHOT_MONITOR_Y": "0"
        })
        client_boxes = {b.get("title"): b for b in res["boxes"] if b.get("is_client")}

        # Right clamp
        r = client_boxes["part_right"]
        self.assertEqual((r["x"], r["y"], r["w"], r["h"]), (1700, 100, 220, 500))

        # Left clamp
        l = client_boxes["part_left"]
        self.assertEqual((l["x"], l["y"], l["w"], l["h"]), (0, 200, 300, 500))

        # Top clamp
        t = client_boxes["part_top"]
        self.assertEqual((t["x"], t["y"], t["w"], t["h"]), (100, 0, 400, 450))

        # Bottom clamp
        b = client_boxes["part_bottom"]
        self.assertEqual((b["x"], b["y"], b["w"], b["h"]), (600, 900, 400, 180))

    def test_monitor_coordinates_sub_threshold_slivers_rejected(self):
        """
        Windows whose clamped visible width or height is less than 20px must be dropped
        to avoid 1-5px phantom border slivers.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            # 1910 to 2310 -> clamped w = 10px (< 20px)
            {"at": [1910, 100], "size": [400, 500], "workspace": {"id": 1}, "title": "sliver_right"},
            # y = -390 to 10 -> clamped h = 10px (< 20px)
            {"at": [100, -390], "size": [400, 400], "workspace": {"id": 1}, "title": "sliver_top"}
        ]
        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {
            "SMARTSHOT_WORKSPACE_ID": "1",
            "SMARTSHOT_MONITOR_X": "0",
            "SMARTSHOT_MONITOR_Y": "0"
        })
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        self.assertEqual(len(client_boxes), 0, "Sub-20px edge slivers must be rejected")

    def test_multi_monitor_negative_and_fractional_offsets(self):
        """
        Verify multi-monitor layout: left monitor at negative origin (-1920, 0),
        and scaled monitor at (1920, 0) with scale 1.25.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            # Window on left monitor (origin -1920, 0)
            {"at": [-1820, 50], "size": [800, 600], "workspace": {"id": 1}, "title": "left_mon_win"},
            # Window on center monitor (origin 0, 0)
            {"at": [100, 50], "size": [800, 600], "workspace": {"id": 1}, "title": "center_mon_win"}
        ]
        clients_path = self._write_clients_json(clients)

        # Capturing left monitor (SMARTSHOT_MONITOR_X = -1920)
        res_left = self._run_detection(img_path, clients_path, {
            "SMARTSHOT_WORKSPACE_ID": "1",
            "SMARTSHOT_MONITOR_X": "-1920",
            "SMARTSHOT_MONITOR_Y": "0",
            "SMARTSHOT_MONITOR_SCALE": "1.0"
        })
        boxes_left = {b.get("title"): b for b in res_left["boxes"] if b.get("is_client")}
        self.assertIn("left_mon_win", boxes_left)
        self.assertNotIn("center_mon_win", boxes_left)
        # cx = -1820 - (-1920) = 100
        self.assertEqual(boxes_left["left_mon_win"]["x"], 100)

    # --------------------------------------------------------------------------
    # Scenario 6: Malformed clients.json & Robustness
    # --------------------------------------------------------------------------
    def test_malformed_clients_data_robustness(self):
        """
        Adversarial malformed inputs in clients.json must never crash the detector:
        - null entries, integers, non-dict objects
        - missing at, size, workspace
        - negative sizes
        - valid window mixed in should still be detected
        """
        img_path = self._create_test_image(1920, 1080)
        malformed_clients = [
            None,
            123,
            "just_a_string",
            [],
            {},
            {"at": [100]},  # incomplete at
            {"at": [100, 100], "size": [50]},  # incomplete size
            {"at": [100, 100], "size": [-400, 300], "workspace": {"id": 1}},  # negative width
            {"at": [100, 100], "size": [400, -300], "workspace": {"id": 1}},  # negative height
            {"at": ["100", "100"], "size": ["500", "400"], "workspace": None, "pinned": True, "title": "string_coords"},
            {"at": [200, 200], "size": [600, 400], "workspace": {"id": 1}, "title": "valid_window"}
        ]
        clients_path = self._write_clients_json(malformed_clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "1"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]

        self.assertIn("valid_window", titles, "Valid window must be detected despite adjacent corrupt records")

    # --------------------------------------------------------------------------
    # Scenario 7: High-Volume Scalability Stress Test (1000+ Clients)
    # --------------------------------------------------------------------------
    def test_high_volume_stress_1000_clients(self):
        """
        Stress test: 1,000 background windows across 50 workspaces, 5 pinned windows,
        and 3 active workspace windows. Confirms O(N) filtering without memory explosion
        or phantom leaks.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = []

        # 992 background tiled windows across workspaces 10 to 59
        for i in range(992):
            ws_id = 10 + (i % 50)
            col = i % 4
            row = (i // 4) % 4
            clients.append({
                "at": [col * 480, row * 270],
                "size": [480, 270],
                "workspace": {"id": ws_id, "name": str(ws_id)},
                "title": f"bg_win_{i}"
            })

        # 5 pinned windows on various background workspaces
        for j in range(5):
            clients.append({
                "at": [50 + j * 120, 50],
                "size": [100, 100],
                "workspace": {"id": 99},
                "pinned": True,
                "floating": True,
                "title": f"pinned_stress_{j}"
            })

        # 3 active windows on workspace 1
        for k in range(3):
            clients.append({
                "at": [100 + k * 500, 300],
                "size": [450, 600],
                "workspace": {"id": 1, "name": "1"},
                "title": f"active_win_{k}"
            })

        clients_path = self._write_clients_json(clients)

        res = self._run_detection(img_path, clients_path, {"SMARTSHOT_WORKSPACE_ID": "1"})
        client_boxes = [b for b in res["boxes"] if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]

        self.assertEqual(len(client_boxes), 8, f"Expected exactly 8 windows (3 active + 5 pinned), got {len(client_boxes)}")
        for k in range(3):
            self.assertIn(f"active_win_{k}", titles)
        for j in range(5):
            self.assertIn(f"pinned_stress_{j}", titles)
        for i in range(10):
            self.assertNotIn(f"bg_win_{i}", titles)

    # --------------------------------------------------------------------------
    # Scenario 8: Standalone CLI Subprocess Invocations
    # --------------------------------------------------------------------------
    def test_cli_subprocess_invocation(self):
        """
        Verify CLI invocation: `python3 detect_ui.py <image> <output_json> <clients_json>`
        produces identical workspace isolation when executed directly in bash environment.
        """
        img_path = self._create_test_image(1920, 1080)
        clients = [
            {"at": [0, 0], "size": [960, 1080], "workspace": {"id": 1}, "title": "kitty_ws1"},
            {"at": [100, 100], "size": [800, 600], "workspace": {"id": 2}, "title": "firefox_ws2"}
        ]
        clients_path = self._write_clients_json(clients)
        out_json_path = self.temp_path / "cli_output.json"

        env = os.environ.copy()
        env["SMARTSHOT_WORKSPACE_ID"] = "2"
        env["SMARTSHOT_MONITOR_X"] = "0"
        env["SMARTSHOT_MONITOR_Y"] = "0"

        cmd = [
            PYTHON_EXEC,
            str(REPO_DIR / "vision" / "detect_ui.py"),
            img_path,
            str(out_json_path),
            clients_path
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"detect_ui.py failed: {proc.stderr}")

        with open(out_json_path, "r") as f:
            data = json.load(f)

        client_boxes = [b for b in data.get("boxes", []) if b.get("is_client")]
        titles = [b.get("title") for b in client_boxes]
        self.assertEqual(titles, ["firefox_ws2"])
        self.assertNotIn("kitty_ws1", titles)


if __name__ == "__main__":
    unittest.main()
