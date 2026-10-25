#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot i18n & configuration.
Verifies JSON validity, key parity across languages, config loading, and runner i18n.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCALIZATION_DIR = os.path.join(REPO_DIR, "localization")
EN_JSON = os.path.join(LOCALIZATION_DIR, "en.json")
CS_JSON = os.path.join(LOCALIZATION_DIR, "cs.json")
CONFIG_JSON = os.path.join(REPO_DIR, "config", "hyprsmartshot", "config.json")
RUNNER_BIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot")

REQUIRED_KEYS = {
    "modeSmart",
    "modeScreen",
    "copy",
    "save",
    "pin",
    "annotate",
    "ocr",
    "cancel",
    "close",
    "hintConfirmed",
    "hintUnconfirmed",
    "tagGrid",
    "tagRow",
    "tagFloating",
    "tagWindow",
    "tagSlot",
    "tagItem",
    "tagPanel",
    "tagButton",
    "tagInput",
    "tagText",
    "tagParagraph",
    "tagScreen",
    "scrollHint",
    "copyTitle",
    "copyDesc",
    "saveTitle",
    "saveDesc",
    "pinTitle",
    "pinDesc",
    "fullscreenTitle",
    "fullscreenDesc",
    "annotateNotFoundTitle",
    "annotateNotFoundDesc",
    "ocrTitle",
    "ocrDesc",
    "ocrNoTextTitle",
    "ocrNoTextDesc",
    "ocrNotFoundTitle",
    "ocrNotFoundDesc"
}

class TestLocalization(unittest.TestCase):
    def test_en_json_valid_and_complete(self):
        self.assertTrue(os.path.isfile(EN_JSON), f"Missing {EN_JSON}")
        with open(EN_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in REQUIRED_KEYS:
            self.assertIn(key, data, f"Missing key '{key}' in en.json")
            self.assertTrue(isinstance(data[key], str) and len(data[key]) > 0, f"Key '{key}' is empty in en.json")

    def test_cs_json_valid_and_complete(self):
        self.assertTrue(os.path.isfile(CS_JSON), f"Missing {CS_JSON}")
        with open(CS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in REQUIRED_KEYS:
            self.assertIn(key, data, f"Missing key '{key}' in cs.json")
            self.assertTrue(isinstance(data[key], str) and len(data[key]) > 0, f"Key '{key}' is empty in cs.json")

    def test_key_parity_between_en_and_cs(self):
        with open(EN_JSON, "r", encoding="utf-8") as f:
            en_data = json.load(f)
        with open(CS_JSON, "r", encoding="utf-8") as f:
            cs_data = json.load(f)
        self.assertEqual(set(en_data.keys()), set(cs_data.keys()), "en.json and cs.json must have identical keys")

    def test_default_config_json(self):
        self.assertTrue(os.path.isfile(CONFIG_JSON), f"Missing {CONFIG_JSON}")
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            config = json.load(f)
        self.assertEqual(config.get("language"), "en", "Default language in bundled config.json must be 'en'")

    def test_all_bundled_languages_valid(self):
        for fname in os.listdir(LOCALIZATION_DIR):
            if fname.endswith(".json"):
                path = os.path.join(LOCALIZATION_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.assertIsInstance(data, dict, f"{fname} must be a JSON object")
                for k, v in data.items():
                    self.assertIn(k, REQUIRED_KEYS, f"Unexpected key '{k}' in {fname}")
                    self.assertTrue(isinstance(v, str) and len(v) > 0, f"Key '{k}' must be non-empty string in {fname}")

    def test_reference_languages_bundled(self):
        # Both en.json and cs.json reference languages must always be present
        self.assertTrue(os.path.isfile(EN_JSON), f"Missing {EN_JSON}")
        self.assertTrue(os.path.isfile(CS_JSON), f"Missing {CS_JSON}")
        # Only .json translation files are allowed in localization/ (no subdirectories or stray files)
        for item in os.listdir(LOCALIZATION_DIR):
            self.assertTrue(item.endswith(".json") and os.path.isfile(os.path.join(LOCALIZATION_DIR, item)),
                            f"Unexpected item in localization directory: {item}")

class TestRunnerLanguageResolution(unittest.TestCase):
    def test_runner_translation_function(self):
        # Test get_translation function defined in bin/hyprsmartshot directly via bash snippet
        bash_script = f"""
        set -e
        DIR="{REPO_DIR}"
        CONFIG_DIR="/nonexistent_config_dir"
        SMARTSHOT_LANG="cs"
        source <(sed -n '/get_translation()/,/^}}/p' "{RUNNER_BIN}")
        get_translation "copyTitle" "FAIL"
        """
        proc = subprocess.run(["bash", "-c", bash_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "Screenshot zkopírován")

        # Test English
        bash_script_en = f"""
        set -e
        DIR="{REPO_DIR}"
        CONFIG_DIR="/nonexistent_config_dir"
        SMARTSHOT_LANG="en"
        source <(sed -n '/get_translation()/,/^}}/p' "{RUNNER_BIN}")
        get_translation "copyTitle" "FAIL"
        """
        proc_en = subprocess.run(["bash", "-c", bash_script_en], capture_output=True, text=True)
        self.assertEqual(proc_en.returncode, 0, proc_en.stderr)
        self.assertEqual(proc_en.stdout.strip(), "Screenshot Copied")

    def test_runner_config_resolution_json(self):
        with tempfile.TemporaryDirectory() as tmp_xdg:
            cfg_dir = os.path.join(tmp_xdg, "hyprsmartshot")
            os.makedirs(cfg_dir, exist_ok=True)

            # Test 1: User config.json
            with open(os.path.join(cfg_dir, "config.json"), "w") as f:
                json.dump({"language": "cs"}, f)

            bash_check = f"""
            DIR="{REPO_DIR}"
            XDG_CONFIG_HOME="{tmp_xdg}"
            unset SMARTSHOT_LANG
            CONFIG_DIR="$XDG_CONFIG_HOME/hyprsmartshot"
            CONFIG_FILE="$CONFIG_DIR/config.json"
            DEFAULT_CONFIG="$DIR/config/hyprsmartshot/config.json"

            if [ -z "$SMARTSHOT_LANG" ]; then
                if [ -f "$CONFIG_FILE" ]; then
                    SMARTSHOT_LANG=$(jq -r '.language // empty' "$CONFIG_FILE" 2>/dev/null || true)
                fi
                if [ -z "$SMARTSHOT_LANG" ] && [ -f "$DEFAULT_CONFIG" ]; then
                    SMARTSHOT_LANG=$(jq -r '.language // empty' "$DEFAULT_CONFIG" 2>/dev/null || true)
                fi
            fi
            echo "$SMARTSHOT_LANG"
            """
            proc = subprocess.run(["bash", "-c", bash_check], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "cs")

            # Test 2: User JSON without language falls back to default
            with open(os.path.join(cfg_dir, "config.json"), "w") as f:
                json.dump({"other_setting": True}, f)

            proc_fallback = subprocess.run(["bash", "-c", bash_check], capture_output=True, text=True)
            self.assertEqual(proc_fallback.returncode, 0)
            self.assertEqual(proc_fallback.stdout.strip(), "en")

            # Test 3: Absence of user config.json falls back to default
            os.remove(os.path.join(cfg_dir, "config.json"))
            proc_def = subprocess.run(["bash", "-c", bash_check], capture_output=True, text=True)
            self.assertEqual(proc_def.returncode, 0)
            self.assertEqual(proc_def.stdout.strip(), "en")

    def test_runner_custom_language_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_xdg:
            cfg_dir = os.path.join(tmp_xdg, "hyprsmartshot")
            loc_dir = os.path.join(cfg_dir, "localization")
            os.makedirs(loc_dir, exist_ok=True)

            with open(os.path.join(loc_dir, "de.json"), "w", encoding="utf-8") as f:
                json.dump({"fullscreenTitle": "Vollbild aufgenommen"}, f)

            bash_script = f"""
            set -e
            DIR="{REPO_DIR}"
            CONFIG_DIR="{cfg_dir}"
            SMARTSHOT_LANG="de"
            source <(sed -n '/get_translation()/,/^}}/p' "{RUNNER_BIN}")
            TITLE=$(get_translation "fullscreenTitle" "FAIL")
            DESC=$(get_translation "fullscreenDesc" "FAIL")
            UNKNOWN=$(get_translation "nonexistentKey" "DefaultVal")
            echo "$TITLE|$DESC|$UNKNOWN"
            """
            proc = subprocess.run(["bash", "-c", bash_script], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            title, desc, unknown = proc.stdout.strip().split("|")
            self.assertEqual(title, "Vollbild aufgenommen")
            self.assertEqual(desc, "Saved to {path} and copied to clipboard")
            self.assertEqual(unknown, "DefaultVal")

    def test_runner_regional_base_language_fallback(self):
        # cs_CZ.UTF-8 should cleanly fall back to cs
        proc = subprocess.run(["bash", "-c", f"""
        set -e
        DIR="{REPO_DIR}"
        CONFIG_DIR="/nonexistent_config_dir"
        SMARTSHOT_LANG="cs_CZ.UTF-8"
        source <(sed -n "/# Sanitize language code/,/export SMARTSHOT_DIR/p" "{RUNNER_BIN}")
        source <(sed -n "/get_translation()/,/^}}/p" "{RUNNER_BIN}")
        get_translation "copyTitle" "FAIL"
        """], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "Screenshot zkopírován")

    def test_runner_path_traversal_sanitization(self):
        proc = subprocess.run(["bash", "-c", f"""
        set -e
        DIR="{REPO_DIR}"
        SMARTSHOT_LANG="../../../../etc/passwd"
        source <(sed -n "/# Sanitize language code/,/export SMARTSHOT_DIR/p" "{RUNNER_BIN}")
        echo "[$SMARTSHOT_LANG]"
        """], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # Should sanitize invalid characters and default to en
        self.assertEqual(proc.stdout.strip(), "[en]")

    def test_runner_whitespace_and_corrupted_json(self):
        # Test whitespace stripping
        proc = subprocess.run(["bash", "-c", f"""
        DIR="{REPO_DIR}"
        SMARTSHOT_LANG="  cs  "
        source <(sed -n "/# Sanitize language code/,/export SMARTSHOT_DIR/p" "{RUNNER_BIN}")
        echo "[$SMARTSHOT_LANG]"
        """], capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "[cs]")

        # Test graceful recovery from broken JSON
        with tempfile.TemporaryDirectory() as tmp_xdg:
            cfg_dir = os.path.join(tmp_xdg, "hyprsmartshot")
            loc_dir = os.path.join(cfg_dir, "localization")
            os.makedirs(loc_dir, exist_ok=True)
            with open(os.path.join(loc_dir, "broken.json"), "w") as f:
                f.write("{{invalid json content!!!")

            proc = subprocess.run(["bash", "-c", f"""
            DIR="{REPO_DIR}"
            CONFIG_DIR="{cfg_dir}"
            SMARTSHOT_LANG="broken"
            source <(sed -n "/get_translation()/,/^}}/p" "{RUNNER_BIN}")
            get_translation "copyTitle" "FAIL"
            """], capture_output=True, text=True)
            self.assertEqual(proc.stdout.strip(), "Screenshot Copied")



@unittest.skipUnless(shutil.which("quickshell"), "quickshell binary not available in environment")
class TestQuickshellQmlIntegration(unittest.TestCase):
    def test_qml_i18n_loading_and_methods(self):
        test_qml = f"""
        import QtQuick
        import Quickshell
        import "file://{REPO_DIR}/components"

        Scope {{
            id: root
            Component.onCompleted: {{
                const copyEn = I18n.t("copy");
                const saveEn = I18n.t("save");
                const hintUnconfirmedEn = I18n.t("hintUnconfirmed");
                console.log("I18N_TEST_RESULT:lang=" + I18n.language + "|copy=" + copyEn + "|save=" + saveEn);
                Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
            }}
        }}
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
            f.write(test_qml)
            f_path = f.name

        try:
            env = os.environ.copy()
            env["SMARTSHOT_DIR"] = REPO_DIR
            env["SMARTSHOT_LANG"] = "en"
            proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
            output = proc.stdout + proc.stderr
            self.assertIn("I18N_TEST_RESULT:lang=en|copy=Copy|save=Save", output)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_qml_i18n_czech_loading(self):
        test_qml = f"""
        import QtQuick
        import Quickshell
        import "file://{REPO_DIR}/components"

        Scope {{
            id: root
            Component.onCompleted: {{
                const copyCs = I18n.t("copy");
                const saveCs = I18n.t("save");
                console.log("I18N_TEST_CS_RESULT:lang=" + I18n.language + "|copy=" + copyCs + "|save=" + saveCs);
                Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
            }}
        }}
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
            f.write(test_qml)
            f_path = f.name

        try:
            env = os.environ.copy()
            env["SMARTSHOT_DIR"] = REPO_DIR
            env["SMARTSHOT_LANG"] = "cs"
            proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
            output = proc.stdout + proc.stderr
            self.assertIn("I18N_TEST_CS_RESULT:lang=cs|copy=Kopírovat|save=Uložit", output)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_qml_custom_language_loading_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_xdg:
            cfg_dir = os.path.join(tmp_xdg, "hyprsmartshot")
            loc_dir = os.path.join(cfg_dir, "localization")
            os.makedirs(loc_dir, exist_ok=True)

            # Custom de.json with only 'copy' and 'modeSmart'
            with open(os.path.join(loc_dir, "de.json"), "w", encoding="utf-8") as f:
                json.dump({"copy": "Kopieren", "modeSmart": "Klug"}, f)

            test_qml = f"""
            import QtQuick
            import Quickshell
            import "file://{REPO_DIR}/components"

            Scope {{
                id: root

                Timer {{
                    interval: 15
                    repeat: true
                    running: true
                    property int count: 0
                    onTriggered: {{
                        count++;
                        if (I18n.t("copy") === "Kopieren") {{
                            const modeDe = I18n.t("modeSmart");
                            const saveFallback = I18n.t("save");
                            console.log("DE_RESULT:copy=" + I18n.t("copy") + "|mode=" + modeDe + "|save=" + saveFallback);
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }} else if (count > 50) {{
                            console.log("TIMEOUT: copy=" + I18n.t("copy"));
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }}
                    }}
                }}
            }}
            """
            with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
                f.write(test_qml)
                f_path = f.name

            try:
                env = os.environ.copy()
                env["SMARTSHOT_DIR"] = REPO_DIR
                env["SMARTSHOT_LANG"] = "de"
                env["XDG_CONFIG_HOME"] = tmp_xdg
                proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
                output = proc.stdout + proc.stderr
                self.assertIn("DE_RESULT:copy=Kopieren|mode=Klug|save=Save", output)
            finally:
                if os.path.exists(f_path):
                    os.remove(f_path)

    def test_qml_unknown_language_fallback(self):
        test_qml = f"""
        import QtQuick
        import Quickshell
        import "file://{REPO_DIR}/components"

        Scope {{
            id: root
            Component.onCompleted: {{
                const copyFb = I18n.t("copy");
                const saveFb = I18n.t("save");
                console.log("UNKNOWN_LANG_RESULT:copy=" + copyFb + "|save=" + saveFb);
                Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
            }}
        }}
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
            f.write(test_qml)
            f_path = f.name

        try:
            env = os.environ.copy()
            env["SMARTSHOT_DIR"] = REPO_DIR
            env["SMARTSHOT_LANG"] = "xy"
            proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
            output = proc.stdout + proc.stderr
            self.assertIn("UNKNOWN_LANG_RESULT:copy=Copy|save=Save", output)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_qml_user_override_precedence(self):
        with tempfile.TemporaryDirectory() as tmp_xdg:
            cfg_dir = os.path.join(tmp_xdg, "hyprsmartshot")
            loc_dir = os.path.join(cfg_dir, "localization")
            os.makedirs(loc_dir, exist_ok=True)

            with open(os.path.join(loc_dir, "cs.json"), "w", encoding="utf-8") as f:
                json.dump({"copy": "Moje Kopírování"}, f)

            test_qml = f"""
            import QtQuick
            import Quickshell
            import "file://{REPO_DIR}/components"

            Scope {{
                id: root

                Timer {{
                    interval: 15
                    repeat: true
                    running: true
                    property int count: 0
                    onTriggered: {{
                        count++;
                        if (I18n.t("copy") === "Moje Kopírování") {{
                            const saveVal = I18n.t("save");
                            console.log("OVERRIDE_RESULT:copy=" + I18n.t("copy") + "|save=" + saveVal);
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }} else if (count > 50) {{
                            console.log("TIMEOUT: copy=" + I18n.t("copy"));
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }}
                    }}
                }}
            }}
            """
            with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
                f.write(test_qml)
                f_path = f.name

            try:
                env = os.environ.copy()
                env["SMARTSHOT_DIR"] = REPO_DIR
                env["SMARTSHOT_LANG"] = "cs"
                env["XDG_CONFIG_HOME"] = tmp_xdg
                proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
                output = proc.stdout + proc.stderr
                self.assertIn("OVERRIDE_RESULT:copy=Moje Kopírování|save=Uložit", output)
            finally:
                if os.path.exists(f_path):
                    os.remove(f_path)

    def test_qml_config_json_dynamic_language_switch(self):
        with tempfile.TemporaryDirectory() as tmp_xdg:
            cfg_dir = os.path.join(tmp_xdg, "hyprsmartshot")
            loc_dir = os.path.join(cfg_dir, "localization")
            os.makedirs(loc_dir, exist_ok=True)

            with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"language": "de"}, f)
            with open(os.path.join(loc_dir, "de.json"), "w", encoding="utf-8") as f:
                json.dump({"copy": "Kopieren_Config"}, f)

            test_qml = f"""
            import QtQuick
            import Quickshell
            import "file://{REPO_DIR}/components"

            Scope {{
                id: root

                Timer {{
                    interval: 15
                    repeat: true
                    running: true
                    property int count: 0
                    onTriggered: {{
                        count++;
                        if (I18n.t("copy") === "Kopieren_Config") {{
                            console.log("CONFIG_SWITCH_RESULT:lang=" + I18n.language + "|copy=" + I18n.t("copy") + "|save=" + I18n.t("save"));
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }} else if (count > 50) {{
                            console.log("TIMEOUT: lang=" + I18n.language + " copy=" + I18n.t("copy"));
                            Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                        }}
                    }}
                }}
            }}
            """
            with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
                f.write(test_qml)
                f_path = f.name

            try:
                env = os.environ.copy()
                env["SMARTSHOT_DIR"] = REPO_DIR
                env.pop("SMARTSHOT_LANG", None)
                env["XDG_CONFIG_HOME"] = tmp_xdg
                proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
                output = proc.stdout + proc.stderr
                self.assertIn("CONFIG_SWITCH_RESULT:lang=de|copy=Kopieren_Config|save=Save", output)
            finally:
                if os.path.exists(f_path):
                    os.remove(f_path)

    def test_qml_regional_base_language_fallback(self):
        # Setting SMARTSHOT_LANG=cs_CZ should cleanly resolve base language cs ("Kopírovat")
        test_qml = f"""
        import QtQuick
        import Quickshell
        import "file://{REPO_DIR}/components"

        Scope {{
            id: root
            Timer {{
                interval: 20
                repeat: true
                running: true
                property int count: 0
                onTriggered: {{
                    count++;
                    if (I18n.t("copy") === "Kopírovat") {{
                        console.log("REGIONAL_RESULT:lang=" + I18n.language + "|base=" + I18n.baseLanguage + "|copy=" + I18n.t("copy"));
                        Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                    }} else if (count > 50) {{
                        console.log("TIMEOUT: copy=" + I18n.t("copy"));
                        Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                    }}
                }}
            }}
        }}
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
            f.write(test_qml)
            f_path = f.name

        try:
            env = os.environ.copy()
            env["SMARTSHOT_DIR"] = REPO_DIR
            env["SMARTSHOT_LANG"] = "cs_CZ"
            proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
            output = proc.stdout + proc.stderr
            self.assertIn("REGIONAL_RESULT:lang=cs_CZ|base=cs|copy=Kopírovat", output)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_qml_path_traversal_sanitization(self):
        # Malicious SMARTSHOT_LANG with directory traversal must be sanitized
        test_qml = f"""
        import QtQuick
        import Quickshell
        import "file://{REPO_DIR}/components"

        Scope {{
            id: root
            Component.onCompleted: {{
                console.log("SANITIZED_LANG:" + I18n.language);
                Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
            }}
        }}
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
            f.write(test_qml)
            f_path = f.name

        try:
            env = os.environ.copy()
            env["SMARTSHOT_DIR"] = REPO_DIR
            env["SMARTSHOT_LANG"] = "../../../../etc/passwd"
            proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
            output = proc.stdout + proc.stderr
            # "../../../../etc/passwd" -> sanitized to "etc" or "en"
            self.assertNotIn("../", output)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_qml_suppresses_missing_override_warnings(self):
        # Missing optional user override files must not spam stderr with "File does not exist" warnings
        with tempfile.TemporaryDirectory() as tmp_xdg:
            test_qml = f"""
            import QtQuick
            import Quickshell
            import "file://{REPO_DIR}/components"

            Scope {{
                id: root
                Component.onCompleted: {{
                    console.log("READY:" + I18n.t("copy"));
                    Quickshell.execDetached(["quickshell", "kill", "--pid", Quickshell.processId.toString()]);
                }}
            }}
            """
            with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", delete=False) as f:
                f.write(test_qml)
                f_path = f.name

            try:
                env = os.environ.copy()
                env["SMARTSHOT_DIR"] = REPO_DIR
                env["XDG_CONFIG_HOME"] = tmp_xdg
                env["SMARTSHOT_LANG"] = "en"
                proc = subprocess.run(["quickshell", "-p", f_path], capture_output=True, text=True, env=env)
                combined = proc.stdout + proc.stderr
                self.assertNotIn("Read of /", combined)
                self.assertNotIn("File does not exist", combined)
            finally:
                if os.path.exists(f_path):
                    os.remove(f_path)


if __name__ == "__main__":
    unittest.main()
