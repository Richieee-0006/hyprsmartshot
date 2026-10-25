#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot configuration (config.json, OCR settings, post-capture hooks).
"""

import json
import os
import subprocess
import tempfile
import unittest

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_JSON = os.path.join(REPO_DIR, "config", "hyprsmartshot", "config.json")
RUNNER_BIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot")


class TestConfiguration(unittest.TestCase):
    def test_default_config_json_structure(self):
        self.assertTrue(os.path.isfile(CONFIG_JSON), f"Missing {CONFIG_JSON}")
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.assertIn("language", cfg)
        self.assertEqual(cfg["language"], "en")
        self.assertIn("ocrLanguages", cfg)
        self.assertEqual(cfg["ocrLanguages"], "eng+ces")
        self.assertIn("postSaveHook", cfg)
        self.assertEqual(cfg["postSaveHook"], "")
        self.assertIn("postCopyHook", cfg)
        self.assertEqual(cfg["postCopyHook"], "")

    def test_runner_post_save_hook_resolution(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_dir = os.path.join(tmp_dir, "hyprsmartshot")
            os.makedirs(cfg_dir, exist_ok=True)
            log_file = os.path.join(tmp_dir, "hook.log")

            config_data = {
                "language": "en",
                "postSaveHook": f"echo 'HOOK_RUN: {{path}}' > '{log_file}'",
            }
            with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as f:
                json.dump(config_data, f)

            # Test resolution logic extracted from bin/hyprsmartshot
            bash_snippet = f"""
            CONFIG_DIR="{cfg_dir}"
            CONFIG_FILE="$CONFIG_DIR/config.json"
            DEFAULT_CONFIG="{CONFIG_JSON}"
            FILEPATH="/tmp/fake_screenshot.png"

            POST_SAVE_HOOK=""
            if [ -f "$CONFIG_FILE" ]; then
                POST_SAVE_HOOK=$(jq -r '.postSaveHook // empty' "$CONFIG_FILE" 2>/dev/null || true)
            fi
            if [ -z "$POST_SAVE_HOOK" ] && [ -f "$DEFAULT_CONFIG" ]; then
                POST_SAVE_HOOK=$(jq -r '.postSaveHook // empty' "$DEFAULT_CONFIG" 2>/dev/null || true)
            fi
            if [ -n "$POST_SAVE_HOOK" ]; then
                shopt -u patsub_replacement 2>/dev/null || true
                HOOK_CMD="${{POST_SAVE_HOOK//\\{{path\\}}/"$FILEPATH"}}"
                eval "$HOOK_CMD"
            fi
            """
            proc = subprocess.run(["bash", "-c", bash_snippet], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.isfile(log_file), "Expected hook to create log file")
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self.assertEqual(content, "HOOK_RUN: /tmp/fake_screenshot.png")

    def test_qml_config_properties_exist(self):
        config_qml = os.path.join(REPO_DIR, "components", "Config.qml")
        self.assertTrue(os.path.isfile(config_qml))
        with open(config_qml, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("property string ocrLanguages:", content)
        self.assertIn("property string postSaveHook:", content)
        self.assertIn("property string postCopyHook:", content)
        self.assertIn("configJsonPath:", content)
        # Ensure TOML is not referenced in Config.qml
        self.assertNotIn("config.toml", content.lower())

    def test_qmllint_components(self):
        proc = subprocess.run(
            ["qmllint", "shell.qml", "components/Config.qml", "components/I18n.qml"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"qmllint failed:\n{proc.stdout}\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
