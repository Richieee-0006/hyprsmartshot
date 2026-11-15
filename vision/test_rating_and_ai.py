#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot modular config loader, Pywal palette sync,
Satty palette export, heuristic+adaptive rating system, and AI VLM client.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VISION_DIR = os.path.join(REPO_DIR, "vision")
if VISION_DIR not in sys.path:
    sys.path.insert(0, VISION_DIR)

import ai_detector  # noqa: E402
import config_loader  # noqa: E402
import rating  # noqa: E402


class TestConfigLoaderAndPywal(unittest.TestCase):
    def test_layered_modular_and_dropin_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            xdg_cfg = os.path.join(tmp, "xdg_cfg")
            app_dir = os.path.join(xdg_cfg, "hyprsmartshot")
            drop_dir = os.path.join(app_dir, "config.d")
            os.makedirs(drop_dir, exist_ok=True)

            with open(os.path.join(app_dir, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"language": "cs", "theme": {"dimOpacity": 0.50}}, f)
            with open(os.path.join(app_dir, "rating.json"), "w", encoding="utf-8") as f:
                json.dump({"minConfidence": 0.42}, f)
            with open(os.path.join(drop_dir, "10-ai.json"), "w", encoding="utf-8") as f:
                json.dump({"ai": {"enabled": True, "trigger": "auto"}}, f)

            old_env = os.environ.copy()
            try:
                os.environ["XDG_CONFIG_HOME"] = xdg_cfg
                os.environ.pop("SMARTSHOT_CONFIG", None)
                cfg = config_loader.load_config(cli_overrides={"activePreset": "game"})

                self.assertEqual(cfg["language"], "cs")
                self.assertAlmostEqual(cfg["theme"]["dimOpacity"], 0.50)
                self.assertAlmostEqual(cfg["rating"]["minConfidence"], 0.42)
                self.assertTrue(cfg["ai"]["enabled"])
                self.assertEqual(cfg["ai"]["trigger"], "auto")
                self.assertEqual(cfg["activePreset"], "game")
                # Unmodified keys preserved cleanly via deep merge
                self.assertIn("providers", cfg["ai"])
                self.assertIn("openai_compatible", cfg["ai"]["providers"])
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_atomic_save_without_bak_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "hyprsmartshot", "config.json")
            saved = config_loader.save_user_config({"language": "cs", "theme": {"borderRadius": 12}}, config_path=target)
            self.assertEqual(saved, target)
            with open(target, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["language"], "cs")
            self.assertEqual(loaded["theme"]["borderRadius"], 12)
            leftovers = [fn for fn in os.listdir(os.path.dirname(target)) if ".bak" in fn or ".tmp" in fn]
            self.assertEqual(leftovers, [])

    def test_pywal_palette_dark_light_and_satty_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            dark_wal = os.path.join(tmp, "wal_dark.json")
            with open(dark_wal, "w", encoding="utf-8") as f:
                json.dump({
                    "special": {"background": "#121016", "foreground": "#ebeaeb"},
                    "colors": {
                        "color0": "#121016", "color1": "#e05a47", "color2": "#68df93",
                        "color3": "#f3c568", "color4": "#6496ff", "color5": "#955eed",
                        "color6": "#68dfdd", "color7": "#b8b8c4", "color8": "#45475a",
                        "color9": "#ff7a68", "color15": "#ebeaeb",
                    },
                }, f)

            cfg_dark = config_loader.deep_merge(
                config_loader.DEFAULT_CONFIG,
                {"theme": {"mode": "pywal", "pywalPath": dark_wal, "overrides": {"pinBorder": "#abcdef"}}},
            )
            pal = config_loader.resolve_pywal_palette(cfg_dark)
            self.assertEqual(pal["source"], "pywal")
            self.assertFalse(pal["isLight"])
            self.assertEqual(pal["accent"], "#e05a47")
            self.assertEqual(pal["aiAccent"], "#955eed")
            self.assertEqual(pal["pinBorder"], "#abcdef")
            self.assertEqual(pal["onAccent"], "#ffffff")

            # Light background + very bright pastel accent flips onAccent to dark ink
            light_wal = os.path.join(tmp, "wal_light.json")
            with open(light_wal, "w", encoding="utf-8") as f:
                json.dump({
                    "special": {"background": "#f7f7fa", "foreground": "#1e1e2e"},
                    "colors": {"color0": "#f7f7fa", "color1": "#f5e0dc", "color15": "#1e1e2e"},
                }, f)
            cfg_light = config_loader.deep_merge(
                config_loader.DEFAULT_CONFIG,
                {"theme": {"mode": "pywal", "pywalPath": light_wal}},
            )
            pal_l = config_loader.resolve_pywal_palette(cfg_light)
            self.assertTrue(pal_l["isLight"])
            self.assertEqual(pal_l["onAccent"], "#111116")

            # Static mode ignores pywalPath cleanly
            cfg_static = config_loader.deep_merge(
                config_loader.DEFAULT_CONFIG,
                {"theme": {"mode": "static", "pywalPath": dark_wal}},
            )
            pal_s = config_loader.resolve_pywal_palette(cfg_static)
            self.assertEqual(pal_s["source"], "static")

            # Non-destructive Satty fragment export
            satty_frag = os.path.join(tmp, "satty-pywal.toml")
            out = config_loader.export_satty_pywal_config(cfg_dark, output_path=satty_frag)
            self.assertEqual(out, satty_frag)
            with open(satty_frag, "r", encoding="utf-8") as f:
                toml_txt = f.read()
            self.assertIn("[color-palette]", toml_txt)
            self.assertIn("#e05a47ff", toml_txt)


class TestRatingSystem(unittest.TestCase):
    def test_scoring_ranking_and_min_confidence_filtering(self):
        strong_panel = {
            "x": 100, "y": 100, "w": 420, "h": 280, "area": 420 * 280,
            "type": "panel", "contrast": 30.0, "extent": 0.94, "edge_score": 0.92, "interior_edge": 0.08,
        }
        weak_noise = {
            "x": 10, "y": 10, "w": 600, "h": 14, "area": 8400,
            "type": "detected", "contrast": 2.0, "extent": 0.25, "edge_score": 0.15, "interior_edge": 0.85,
        }
        window_box = {
            "x": 0, "y": 0, "w": 1920, "h": 1080, "area": 1920 * 1080,
            "type": "window", "is_client": True,
        }

        cfg = config_loader.deep_merge(
            config_loader.DEFAULT_CONFIG,
            {"rating": {"enabled": True, "minConfidence": 0.45, "adaptiveLearning": False}},
        )
        rated = rating.rate_and_filter_boxes([weak_noise, strong_panel, window_box], active_preset="browser", config=cfg)
        types = [b["type"] for b in rated]
        self.assertIn("panel", types)
        self.assertIn("window", types)
        self.assertNotIn("detected", types)
        panel_out = [b for b in rated if b["type"] == "panel"][0]
        self.assertGreaterEqual(panel_out["confidence"], 0.70)
        self.assertGreaterEqual(panel_out["score"], 70)

        # Preset sensitivity check: slot ranks higher under game preset than terminal preset
        slot_box = {"x": 50, "y": 50, "w": 48, "h": 48, "area": 2304, "type": "slot", "contrast": 24.0, "extent": 0.92}
        conf_game, _ = rating.score_box(slot_box, active_preset="game")
        conf_term, _ = rating.score_box(slot_box, active_preset="terminal")
        self.assertGreater(conf_game, conf_term)

    def test_adaptive_feedback_bounded_ema_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof_path = os.path.join(tmp, "rating_profile.json")
            cfg = config_loader.deep_merge(
                config_loader.DEFAULT_CONFIG,
                {"rating": {"enabled": True, "adaptiveLearning": True, "learningRate": 0.08, "profilePath": prof_path}},
            )
            box = {"x": 20, "y": 20, "w": 160, "h": 40, "area": 6400, "type": "button", "contrast": 14.0, "extent": 0.80}

            base_conf, _ = rating.score_box(box, active_preset="browser", rating_cfg=cfg["rating"])
            for _ in range(15):
                prof = rating.record_feedback("button", 160, 40, liked=True, preset_key="browser", config=cfg, profile_path=prof_path)
            self.assertGreater(prof["samples"], 10)
            up_conf, _ = rating.score_box(box, active_preset="browser", rating_cfg=cfg["rating"], profile=prof)
            self.assertGreater(up_conf, base_conf)
            for bias_val in prof["biases"].values():
                self.assertLessEqual(bias_val, 0.25)
                self.assertGreaterEqual(bias_val, -0.25)

            for _ in range(30):
                prof = rating.record_feedback("button", 160, 40, liked=False, preset_key="browser", config=cfg, profile_path=prof_path)
            for bias_val in prof["biases"].values():
                self.assertGreaterEqual(bias_val, -0.25)


class TestAiDetector(unittest.TestCase):
    def test_extract_ai_boxes_parses_thinking_markdown_and_roi_offset(self):
        raw = """
        <think>Let me analyze the screenshot carefully...</think>
        Here are the UI elements:
        ```json
        [
          {"label": "Save Button", "type": "button", "bbox_2d": [100, 200, 300, 500], "confidence": 0.94},
          {"label": "Tiny Dot", "type": "detected", "bbox_2d": [0, 0, 2, 2], "confidence": 0.5},
          {"label": "Normalized Search", "type": "input", "bbox_2d": [0.5, 0.1, 0.7, 0.9], "confidence": 0.91}
        ]
        ```
        """
        boxes = ai_detector.extract_ai_boxes(raw, crop_w=1000, crop_h=500, offset_x=50, offset_y=20)
        self.assertEqual(len(boxes), 2)
        btn = boxes[0]
        self.assertEqual(btn["type"], "button")
        self.assertEqual(btn["label"], "Save Button")
        self.assertEqual(btn["x"], 250)  # 200 + 50
        self.assertEqual(btn["y"], 70)   # 100/1000*500 + 20
        self.assertEqual(btn["w"], 300)
        self.assertEqual(btn["h"], 100)
        self.assertEqual(btn["source"], "ai")
        inp = boxes[1]
        self.assertEqual(inp["type"], "input")
        self.assertEqual(inp["x"], 150)  # 0.1*1000 + 50
        self.assertEqual(inp["w"], 800)

    def test_detect_ai_boxes_openai_and_gemini_mocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_path = os.path.join(tmp, "sample.png")
            img = np.full((400, 800, 3), 30, dtype=np.uint8)
            cv2.rectangle(img, (100, 80), (400, 180), (220, 220, 220), 2)
            cv2.imwrite(img_path, img)

            # 1. Mock OpenAI-compatible provider
            cfg_oai = config_loader.deep_merge(
                config_loader.DEFAULT_CONFIG,
                {
                    "ai": {
                        "enabled": True,
                        "provider": "openai_compatible",
                        "providers": {
                            "openai_compatible": {
                                "baseUrl": "http://127.0.0.1:8080/v1",
                                "model": "mock-vlm",
                                "apiKeyEnv": "",
                            }
                        },
                    }
                },
            )
            mock_oai_resp = mock.MagicMock()
            mock_oai_resp.raise_for_status.return_value = None
            mock_oai_resp.json.return_value = {
                "choices": [{"message": {"content": '[{"label":"Card","type":"panel","bbox_2d":[200,100,800,600],"confidence":0.93}]'}}]
            }

            with mock.patch.object(ai_detector.requests, "post", return_value=mock_oai_resp) as m_post:
                res = ai_detector.detect_ai_boxes(img_path, config=cfg_oai, roi=(50, 40, 500, 250))
                self.assertTrue(res["ok"])
                self.assertEqual(res["count"], 1)
                b = res["boxes"][0]
                self.assertEqual(b["type"], "panel")
                self.assertEqual(b["x"], 100)  # offset_x=50 + 100/1000*500
                self.assertEqual(b["y"], 90)   # offset_y=40 + 200/1000*250
                self.assertIn("/chat/completions", m_post.call_args[0][0])

            # 2. Mock Gemini provider + OCR action
            cfg_gem = config_loader.deep_merge(
                config_loader.DEFAULT_CONFIG,
                {
                    "ai": {
                        "enabled": True,
                        "provider": "gemini",
                        "providers": {
                            "gemini": {
                                "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
                                "model": "gemini-2.5-flash",
                                "apiKey": "test-fake-key",
                            }
                        },
                    }
                },
            )
            mock_gem_resp = mock.MagicMock()
            mock_gem_resp.raise_for_status.return_value = None
            mock_gem_resp.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": "<think>ignored</think>Detected Text"}]}}]
            }

            with mock.patch.object(ai_detector.requests, "post", return_value=mock_gem_resp) as m_gem:
                txt = ai_detector.run_ai_vision_action(img_path, action="ocr", config=cfg_gem)
                self.assertEqual(txt, "Detected Text")
                self.assertIn(":generateContent", m_gem.call_args[0][0])
                self.assertEqual(m_gem.call_args[1]["params"]["key"], "test-fake-key")

    def test_check_ai_status_handles_offline_endpoint(self):
        cfg = config_loader.deep_merge(
            config_loader.DEFAULT_CONFIG,
            {"ai": {"enabled": True, "provider": "openai_compatible"}},
        )
        with mock.patch.object(ai_detector.requests, "get", side_effect=ai_detector.requests.ConnectionError("refused")):
            status = ai_detector.check_ai_status(cfg)
            self.assertTrue(status["enabled"])
            self.assertFalse(status["reachable"])
            self.assertIn("offline", status["detail"])


if __name__ == "__main__":
    unittest.main()
