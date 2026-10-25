#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot configuration (config.json, OCR settings, post-capture hooks).
"""

import json
import os
import shutil
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

    def test_qmldir_singleton_config_registered(self):
        qmldir_path = os.path.join(REPO_DIR, "components", "qmldir")
        self.assertTrue(os.path.isfile(qmldir_path), f"Missing {qmldir_path}")
        with open(qmldir_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        self.assertIn("singleton Config 1.0 Config.qml", lines,
                      "components/qmldir must register singleton Config 1.0 Config.qml")

    def test_shell_qml_action_defensive_cleanup(self):
        shell_qml = os.path.join(REPO_DIR, "shell.qml")
        self.assertTrue(os.path.isfile(shell_qml))
        with open(shell_qml, "r", encoding="utf-8") as f:
            content = f.read()
        for action in ["function doCopy", "function doSave", "function doAnnotate", "function doOcr"]:
            self.assertIn(action, content, f"Action {action} missing in shell.qml")
        self.assertIn("finally {", content)
        self.assertIn("root.closeOverlay();", content)
        self.assertIn("function shellEscape(s)", content, "shellEscape must be defined in shell.qml")

    def test_qmllint_components(self):
        if not shutil.which("qmllint"):
            self.skipTest("qmllint not installed in environment")
        qml_files = [os.path.join(REPO_DIR, "shell.qml")]
        comp_dir = os.path.join(REPO_DIR, "components")
        for f in sorted(os.listdir(comp_dir)):
            if f.endswith(".qml"):
                qml_files.append(os.path.join(comp_dir, f))
        proc = subprocess.run(
            ["qmllint"] + qml_files,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"qmllint failed:\n{proc.stdout}\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
