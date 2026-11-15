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
        self.assertEqual(cfg["ocrLanguages"], "eng")
        self.assertIn("postSaveHook", cfg)
        self.assertEqual(cfg["postSaveHook"], "")
        self.assertIn("postCopyHook", cfg)
        self.assertEqual(cfg["postCopyHook"], "")
        self.assertIn("activePreset", cfg)
        self.assertEqual(cfg["activePreset"], "default")
        self.assertIn("presets", cfg)
        self.assertIn("default", cfg["presets"])
        self.assertIn("browser", cfg["presets"])
        self.assertIn("terminal", cfg["presets"])
        self.assertIn("game", cfg["presets"])
        self.assertIn("appRules", cfg)
        self.assertIn("firefox", cfg["appRules"])
        self.assertIn("kitty", cfg["appRules"])

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
        self.assertIn("property string activePreset:", content)
        self.assertIn("property var presets:", content)
        self.assertIn("property var appRules:", content)
        self.assertIn("function resolvePresetForApp(", content)
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
        self.assertIn("yyyy-MM-dd_HH-mm-ss", content, "Timestamps must use 24-hour HH format")
        self.assertNotIn("yyyy-MM-dd_hh-mm-ss", content, "Timestamps must not use 12-hour hh format")

    def test_do_annotate_satty_command_quoting(self):
        shell_qml = os.path.join(REPO_DIR, "shell.qml")
        with open(shell_qml, "r", encoding="utf-8") as f:
            content = f.read()

        # Ensure satty --copy-command uses shellEscape instead of raw nested double quotes
        self.assertNotIn('\\"Snímek', content)
        self.assertIn("--copy-command ${shellEscape(sattyCopyCmd)}", content)

        # Verify generated command syntax and mock satty argument parsing with spaces/diacritics
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_bin = os.path.join(tmp_dir, "bin")
            os.makedirs(mock_bin, exist_ok=True)
            args_log = os.path.join(tmp_dir, "satty_args.json")
            mock_satty = os.path.join(mock_bin, "satty")
            with open(mock_satty, "w", encoding="utf-8") as f:
                f.write(
                    "#!/usr/bin/env python3\n"
                    "import json, sys\n"
                    f"with open({args_log!r}, 'w', encoding='utf-8') as out:\n"
                    "    json.dump(sys.argv[1:], out)\n"
                )
            os.chmod(mock_satty, 0o755)

            import shlex
            copy_desc = "Výřez byl zkopírován do schránky"
            satty_copy_cmd = (
                "sh -c 'wl-copy --type image/png && "
                "(caelestia-toast -t success -i content_copy -a Satty \"$1\" \"$2\" 2>/dev/null "
                "|| notify-send -a Satty \"$1\" \"$2\" 2>/dev/null || true)' _ 'Satty' "
                + shlex.quote(copy_desc)
            )
            temp_crop = os.path.join(tmp_dir, "annot.png")
            out_path = os.path.join(tmp_dir, "out.png")
            with open(temp_crop, "wb") as f:
                f.write(b"png")

            cmd = (
                f"if command -v satty >/dev/null 2>&1; then "
                f"satty --filename {shlex.quote(temp_crop)} --output-filename {shlex.quote(out_path)} "
                f"--early-exit --copy-command {shlex.quote(satty_copy_cmd)} --initial-tool brush; "
                f"rm -f {shlex.quote(temp_crop)}; fi"
            )
            env = os.environ.copy()
            env["PATH"] = mock_bin + os.pathsep + env.get("PATH", "")
            proc = subprocess.run(["sh", "-c", cmd], env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(os.path.exists(temp_crop), "tempCrop should be removed after satty exits")
            with open(args_log, "r", encoding="utf-8") as f:
                argv = json.load(f)
            self.assertEqual(
                argv,
                [
                    "--filename", temp_crop,
                    "--output-filename", out_path,
                    "--early-exit",
                    "--copy-command", satty_copy_cmd,
                    "--initial-tool", "brush",
                ],
            )

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

    def test_app_rules_and_smart_selector_preset_filters(self):
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for app_key, expected_preset in (("librewolf", "browser"), ("steam_app", "game"), ("ghostty", "terminal")):
            self.assertEqual(cfg["appRules"].get(app_key), expected_preset)

        with open(os.path.join(REPO_DIR, "components", "Config.qml"), "r", encoding="utf-8") as f:
            config_qml = f.read()
        self.assertIn('"librewolf": "browser"', config_qml)
        self.assertIn('"steam_app": "game"', config_qml)

        with open(os.path.join(REPO_DIR, "components", "SmartSelector.qml"), "r", encoding="utf-8") as f:
            selector_qml = f.read()
        self.assertIn('preset.filter === "dense"', selector_qml)
        self.assertIn('preset.filter === "window"', selector_qml)
        self.assertIn('preset.filter === "content"', selector_qml)
        self.assertIn("bongocat", selector_qml)

    def test_modular_config_sections_and_qml_components(self):
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for sec in ("theme", "detection", "rating", "ai", "ui", "capture"):
            self.assertIn(sec, cfg, f"Missing modular section '{sec}' in default config.json")
        self.assertFalse(cfg["ai"]["enabled"], "Publishable default must have AI disabled out-of-the-box")

        qmldir_path = os.path.join(REPO_DIR, "components", "qmldir")
        with open(qmldir_path, "r", encoding="utf-8") as f:
            qmldir = f.read()
        self.assertIn("SettingsModal 1.0 SettingsModal.qml", qmldir)
        self.assertTrue(os.path.isfile(os.path.join(REPO_DIR, "components", "SettingsModal.qml")))

        with open(os.path.join(REPO_DIR, "components", "Theme.qml"), "r", encoding="utf-8") as f:
            theme_qml = f.read()
        self.assertNotIn("property color onAccent", theme_qml, "onAccent breaks QML signal-handler naming rules")

    def test_quickshell_theme_pywal_and_settings_modal_smoke(self):
        if not shutil.which("quickshell"):
            self.skipTest("quickshell not installed in environment")

        with tempfile.TemporaryDirectory() as tmp_xdg:
            wal_path = os.path.join(tmp_xdg, "wal_colors.json")
            with open(wal_path, "w", encoding="utf-8") as f:
                json.dump({
                    "special": {"background": "#121318", "foreground": "#e6e7eb"},
                    "colors": {
                        "color0": "#121318", "color1": "#123456", "color2": "#22aa55",
                        "color3": "#ddaa33", "color4": "#3377ff", "color5": "#aa55ff",
                        "color7": "#c0c2cc", "color8": "#44475a", "color9": "#234567",
                        "color15": "#e6e7eb",
                    },
                }, f)

            cfg_dir = os.path.join(tmp_xdg, "hyprsmartshot")
            os.makedirs(cfg_dir, exist_ok=True)
            with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"theme": {"mode": "pywal", "pywalPath": wal_path}}, f)

            test_qml = f"""
            import QtQuick
            import Quickshell
            import "file://{REPO_DIR}/components"

            Scope {{
                id: root
                SettingsModal {{ id: modal; open: false }}
                Timer {{
                    interval: 20
                    repeat: true
                    running: true
                    property int ticks: 0
                    onTriggered: {{
                        ticks++;
                        const acc = String(Theme.accent).toLowerCase();
                        if (acc === "#123456") {{
                            console.log("THEME_OK:" + acc + "|source=" + Theme.themeSource);
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }} else if (ticks > 40) {{
                            console.log("THEME_FAIL:" + acc + "|source=" + Theme.themeSource);
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }}
                    }}
                }}
            }}
            """
            with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as tf:
                tf.write(test_qml)
                tf_path = tf.name
            try:
                env = os.environ.copy()
                env["SMARTSHOT_DIR"] = REPO_DIR
                env["XDG_CONFIG_HOME"] = tmp_xdg
                proc = subprocess.run(["quickshell", "-p", tf_path], capture_output=True, text=True, env=env)
                output = proc.stdout + proc.stderr
                self.assertIn("THEME_OK:#123456|source=pywal", output)
            finally:
                if os.path.exists(tf_path):
                    os.remove(tf_path)


if __name__ == "__main__":
    unittest.main()
