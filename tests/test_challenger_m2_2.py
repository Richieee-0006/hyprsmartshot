#!/usr/bin/env python3
"""
Adversarial Stress Test Suite for HyprSmartShot Milestone 2 (Block 2: Pin to Screen).
Authored by Challenger M2-2 to empirically stress-test:
1. CLI delegation (bin/hyprsmartshot pin <image> -> bin/hyprsmartshot-pin)
2. Wrapper backwards compatibility (scripts/pin_window.py -> bin/hyprsmartshot-pin)
3. Installer permissions and symlinks (install.sh)
4. QML doPin command generation and POSIX shell escaping
5. Localization completeness and parity ("pin", "pinTitle", "pinDesc")
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
import importlib.util

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNNER_BIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot")
PIN_BIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot-pin")
WRAPPER_SCRIPT = os.path.join(REPO_DIR, "scripts", "pin_window.py")
INSTALL_SH = os.path.join(REPO_DIR, "install.sh")
SHELL_QML = os.path.join(REPO_DIR, "shell.qml")
ACTION_PILL_QML = os.path.join(REPO_DIR, "components", "ActionPill.qml")
SMART_SELECTOR_QML = os.path.join(REPO_DIR, "components", "SmartSelector.qml")
LOCALIZATION_DIR = os.path.join(REPO_DIR, "localization")


def qml_shell_escape(s):
    """Exact JavaScript shellEscape implementation from shell.qml."""
    if s is None:
        return "''"
    return "'" + str(s).replace("'", "'\\''") + "'"


class TestCLIDelegation(unittest.TestCase):
    """Stress-test bin/hyprsmartshot pin delegation to bin/hyprsmartshot-pin."""

    def test_cli_pin_missing_argument(self):
        proc = subprocess.run([RUNNER_BIN, "pin"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Missing image path for 'pin'", proc.stderr)
        self.assertIn("Usage: hyprsmartshot pin <image_path>", proc.stderr)

    def test_cli_pin_nonexistent_image(self):
        bogus = "/tmp/nonexistent_pin_test_123456789.png"
        proc = subprocess.run([RUNNER_BIN, "pin", bogus], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"Error: Image not found: {bogus}", proc.stderr)

    def test_cli_pin_path_with_spaces(self):
        bogus_space = "/tmp/image file with several spaces in name 987654.png"
        proc = subprocess.run([RUNNER_BIN, "pin", bogus_space], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        # Must preserve whole path without word-splitting
        self.assertIn(f"Error: Image not found: {bogus_space}", proc.stderr)

    def test_cli_pin_path_with_special_characters(self):
        bogus_spec = "/tmp/test'quote\"$VAR;echo`hacked`.png"
        proc = subprocess.run([RUNNER_BIN, "pin", bogus_spec], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"Error: Image not found: {bogus_spec}", proc.stderr)

    def test_cli_pin_flag_keep_passed_to_pin_script(self):
        bogus = "/tmp/test_keep_flag_nonexistent.png"
        proc = subprocess.run([RUNNER_BIN, "pin", "--keep", bogus], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        # Verifies --keep was recognized by hyprsmartshot-pin and not rejected as unknown arg
        self.assertIn(f"Error: Image not found: {bogus}", proc.stderr)

    def test_cli_pin_flag_delete_passed_to_pin_script(self):
        bogus = "/tmp/test_delete_flag_nonexistent.png"
        proc = subprocess.run([RUNNER_BIN, "pin", "--delete", bogus], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"Error: Image not found: {bogus}", proc.stderr)

    def test_cli_pin_geometry_coordinates_passed(self):
        bogus = "/tmp/test_geometry_nonexistent.png"
        proc = subprocess.run([RUNNER_BIN, "pin", bogus, "100", "200", "640", "480"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"Error: Image not found: {bogus}", proc.stderr)

    def test_cli_pin_delegates_to_wrapper_when_binary_missing(self):
        """Verify fallback from bin/hyprsmartshot-pin to scripts/pin_window.py."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock repo structure
            bin_dir = os.path.join(tmp_dir, "bin")
            scripts_dir = os.path.join(tmp_dir, "scripts")
            os.makedirs(bin_dir)
            os.makedirs(scripts_dir)

            # Copy runner
            runner_copy = os.path.join(bin_dir, "hyprsmartshot")
            shutil.copy(RUNNER_BIN, runner_copy)
            os.chmod(runner_copy, 0o755)

            # Put a dummy pin_window.py in scripts
            dummy_wrapper = os.path.join(scripts_dir, "pin_window.py")
            with open(dummy_wrapper, "w") as f:
                f.write("#!/usr/bin/env python3\nimport sys\nprint('MOCK_WRAPPER_INVOKED:' + sys.argv[1])\n")
            os.chmod(dummy_wrapper, 0o755)

            proc = subprocess.run([runner_copy, "pin", "test_img.png"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("MOCK_WRAPPER_INVOKED:test_img.png", proc.stdout)

    def test_cli_pin_error_when_neither_script_exists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bin_dir = os.path.join(tmp_dir, "bin")
            os.makedirs(bin_dir)
            runner_copy = os.path.join(bin_dir, "hyprsmartshot")
            shutil.copy(RUNNER_BIN, runner_copy)
            os.chmod(runner_copy, 0o755)

            proc = subprocess.run([runner_copy, "pin", "test_img.png"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("Error: Pin script not found at", proc.stderr)


class TestPinWindowWrapper(unittest.TestCase):
    """Stress-test scripts/pin_window.py wrapper and backwards compatibility."""

    def test_wrapper_exports_required_symbols(self):
        loader = SourceFileLoader("pin_window_wrapper", WRAPPER_SCRIPT)
        mod = loader.load_module()

        expected_symbols = ["PinWindow", "run_pyside6_viewer", "fallback_viewer", "is_temporary_path"]
        for sym in expected_symbols:
            self.assertTrue(hasattr(mod, sym), f"scripts/pin_window.py is missing exported symbol: '{sym}'")
            val = getattr(mod, sym)
            self.assertIsNotNone(val, f"Exported symbol '{sym}' is None")

    def test_wrapper_symbols_match_pin_binary(self):
        loader_wrap = SourceFileLoader("pin_wrap", WRAPPER_SCRIPT)
        mod_wrap = loader_wrap.load_module()

        import sys
        # scripts/pin_window.py loads BIN_PIN under name "hyprsmartshot_pin"
        mod_bin = sys.modules.get("hyprsmartshot_pin")
        self.assertIsNotNone(mod_bin, "hyprsmartshot_pin module was not registered in sys.modules")

        for sym in ["PinWindow", "run_pyside6_viewer", "fallback_viewer", "is_temporary_path"]:
            self.assertIs(getattr(mod_wrap, sym), getattr(mod_bin, sym),
                          f"Symbol '{sym}' in wrapper does not match binary module")


    def test_is_temporary_path_logic(self):
        loader = SourceFileLoader("pin_window_wrapper", WRAPPER_SCRIPT)
        mod = loader.load_module()
        fn = getattr(mod, "is_temporary_path")

        # Temporary locations should return True
        self.assertTrue(fn("/tmp/hyprsmartshot_pin_123.png"))
        self.assertTrue(fn("/tmp/screenshot.png"))
        self.assertTrue(fn("/var/tmp/test.png"))
        self.assertTrue(fn(os.path.join(tempfile.gettempdir(), "image.png")))
        self.assertTrue(fn("/home/user/Pictures/hyprsmartshot_2026.png"))

        # Permanent user files should return False
        self.assertFalse(fn("/home/user/Pictures/Screenshots/capture.png"))
        self.assertFalse(fn("/home/user/Documents/diagram.png"))
        self.assertFalse(fn("/home/user/Downloads/wallpaper.jpg"))

    def test_wrapper_cli_help(self):
        proc = subprocess.run(["python3", WRAPPER_SCRIPT, "--help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage: pin_window.py <image_path>", proc.stdout)
        self.assertIn("--keep", proc.stdout)
        self.assertIn("--delete", proc.stdout)

    def test_wrapper_cli_version(self):
        proc = subprocess.run(["python3", WRAPPER_SCRIPT, "--version"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("pin_window.py v0.0.1", proc.stdout)

    def test_wrapper_cli_missing_args(self):
        proc = subprocess.run(["python3", WRAPPER_SCRIPT], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Usage: pin_window.py", proc.stderr)

    def test_wrapper_cli_nonexistent_file(self):
        bogus = "/tmp/nonexistent_wrapper_test_54321.png"
        proc = subprocess.run(["python3", WRAPPER_SCRIPT, bogus], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"Error: Image not found: {bogus}", proc.stderr)


class TestInstallerIntegration(unittest.TestCase):
    """Stress-test install.sh permissions, symlinks, and idempotence."""

    def test_pin_binary_is_executable_on_disk(self):
        self.assertTrue(os.path.isfile(PIN_BIN))
        mode = os.stat(PIN_BIN).st_mode
        self.assertTrue(bool(mode & stat.S_IXUSR), "bin/hyprsmartshot-pin must have user execute permission")

    def test_installer_creates_executable_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_bin = os.path.join(tmp_dir, "custom_bin")
            custom_cfg = os.path.join(tmp_dir, "custom_cfg")

            env = os.environ.copy()
            env["BIN_DIR"] = custom_bin
            env["XDG_CONFIG_HOME"] = custom_cfg

            # Run install.sh up to symlink creation
            proc = subprocess.run(["bash", "-c", f'source "{INSTALL_SH}"'], env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Check symlink exists
            symlink_pin = os.path.join(custom_bin, "hyprsmartshot-pin")
            self.assertTrue(os.path.islink(symlink_pin), f"Symlink {symlink_pin} was not created")
            self.assertEqual(os.path.realpath(symlink_pin), PIN_BIN)

            # Check symlink target is executable
            self.assertTrue(os.access(symlink_pin, os.X_OK))

            # Run via symlink
            proc_run = subprocess.run([symlink_pin, "--version"], capture_output=True, text=True)
            self.assertEqual(proc_run.returncode, 0)
            self.assertIn("hyprsmartshot-pin v0.0.1", proc_run.stdout)

    def test_installer_custom_bin_with_spaces_and_special_chars(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_bin = os.path.join(tmp_dir, "bin with spaces and 'quotes'")
            custom_cfg = os.path.join(tmp_dir, "config with spaces")

            env = os.environ.copy()
            env["BIN_DIR"] = custom_bin
            env["XDG_CONFIG_HOME"] = custom_cfg

            proc = subprocess.run(["bash", "-c", f'source "{INSTALL_SH}"'], env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            symlink_pin = os.path.join(custom_bin, "hyprsmartshot-pin")
            self.assertTrue(os.path.islink(symlink_pin))
            self.assertEqual(os.path.realpath(symlink_pin), PIN_BIN)

    def test_installer_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_bin = os.path.join(tmp_dir, "bin")
            custom_cfg = os.path.join(tmp_dir, "config")

            env = os.environ.copy()
            env["BIN_DIR"] = custom_bin
            env["XDG_CONFIG_HOME"] = custom_cfg

            # Run 1
            proc1 = subprocess.run(["bash", "-c", f'source "{INSTALL_SH}"'], env=env, capture_output=True, text=True)
            self.assertEqual(proc1.returncode, 0)

            # Run 2
            proc2 = subprocess.run(["bash", "-c", f'source "{INSTALL_SH}"'], env=env, capture_output=True, text=True)
            self.assertEqual(proc2.returncode, 0)

            symlink_pin = os.path.join(custom_bin, "hyprsmartshot-pin")
            self.assertTrue(os.path.islink(symlink_pin))
            self.assertEqual(os.path.realpath(symlink_pin), PIN_BIN)


class TestQMLDoPinCommandAndEscaping(unittest.TestCase):
    """Stress-test QML shellEscape and doPin command construction against adversarial payloads."""

    ADVERSARIAL_PAYLOADS = [
        "/tmp/normal_image.png",
        "/tmp/path with multiple spaces/image.png",
        "/tmp/path'with'single'quotes.png",
        '/tmp/path"with"double"quotes.png',
        "/tmp/path;echo HACKED;rm -rf /.png",
        "/tmp/path$(id;whoami).png",
        "/tmp/path`id`.png",
        "/tmp/path$HOME$USER.png",
        "/tmp/path\\with\\backslashes.png",
        "/tmp/path\nwith\nnewlines.png",
        "/tmp/path&bg_command.png",
        "/tmp/path|pipe_command.png",
        "/tmp/path<input>output.png",
        "/tmp/path*glob?.png",
        "/tmp/!@#$%^&*()_+-=[]{}|;':,.<>?.png",
        "L'image d'écran sélectionnée",
        "Výřez 'připnut' na obrazovku $TEST",
    ]

    def test_shell_escape_posix_equivalence_and_injection_immunity(self):
        for payload in self.ADVERSARIAL_PAYLOADS:
            escaped = qml_shell_escape(payload)

            # Test in sh -c that payload is preserved verbatim without shell evaluation
            # We use a python helper to read argv[1]
            test_cmd = f"python3 -c 'import sys; print(sys.argv[1])' {escaped}"
            proc = subprocess.run(["sh", "-c", test_cmd], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"Failed on payload: {payload}")
            self.assertEqual(proc.stdout.strip(), payload.strip(), f"Mismatch on payload: {payload}")

    def test_qml_do_pin_template_syntax_validation(self):
        """Validate bash syntax of the exact doPin command template from shell.qml."""
        # Read doPin section from shell.qml
        with open(SHELL_QML, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("function doPin(x, y, width, height)", content)
        self.assertIn("hyprsmartshot-pin", content)

        # Reconstruct the exact command template with adversarial arguments
        for payload in self.ADVERSARIAL_PAYLOADS[:8]:
            tempCrop = payload
            x, y, width, height = 150, 250, 800, 600
            title = "Screenshot 'Pinned'"
            desc = "Selection $HOME 'pinned' & safe"

            crop = f"grim -g '{x},{y} {width}x{height}' {qml_shell_escape(tempCrop)}"
            pinCmd = (
                f'if command -v hyprsmartshot-pin >/dev/null 2>&1; then '
                f'hyprsmartshot-pin {qml_shell_escape(tempCrop)} {round(x)} {round(y)} {round(width)} {round(height)}; '
                f'elif [ -n "$SMARTSHOT_DIR" ] && [ -x "$SMARTSHOT_DIR/bin/hyprsmartshot-pin" ]; then '
                f'"$SMARTSHOT_DIR/bin/hyprsmartshot-pin" {qml_shell_escape(tempCrop)} {round(x)} {round(y)} {round(width)} {round(height)}; '
                f'else hyprsmartshot pin {qml_shell_escape(tempCrop)} {round(x)} {round(y)} {round(width)} {round(height)}; fi'
            )
            fullCmd = (
                f"{crop} && notify-send -a \"HyprSmartShot\" -i {qml_shell_escape(tempCrop)} "
                f"{qml_shell_escape(title)} {qml_shell_escape(desc)} && ({pinCmd}; rm -f {qml_shell_escape(tempCrop)}) &"
            )

            # Test bash syntax check: bash -n -c fullCmd
            proc = subprocess.run(["bash", "-n", "-c", fullCmd], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"Bash syntax error for payload '{payload}': {proc.stderr}")

            # Test sh syntax check (since Quickshell uses sh -c)
            proc_sh = subprocess.run(["sh", "-n", "-c", fullCmd], capture_output=True, text=True)
            self.assertEqual(proc_sh.returncode, 0, f"sh syntax error for payload '{payload}': {proc_sh.stderr}")

    def test_qml_action_pill_and_smart_selector_pin_wiring(self):
        with open(ACTION_PILL_QML, "r", encoding="utf-8") as f:
            pill_src = f.read()
        self.assertIn("root.pinRequested()", pill_src)
        self.assertIn('text: I18n.t("pin")', pill_src)

        with open(SMART_SELECTOR_QML, "r", encoding="utf-8") as f:
            selector_src = f.read()
        self.assertIn("signal pinAction(real x, real y, real width, real height)", selector_src)
        self.assertIn("onPinRequested: root.pinAction(", selector_src)

        with open(SHELL_QML, "r", encoding="utf-8") as f:
            shell_src = f.read()
        self.assertIn("onPinAction: (x, y, w, h) => root.doPin(x, y, w, h)", shell_src)
        self.assertIn("Qt.Key_P", shell_src)
        self.assertIn("root.doPin(", shell_src)


class TestLocalizationParityAndCompleteness(unittest.TestCase):
    """Stress-test localization completeness for pin keys across all translation files."""

    PIN_KEYS = {
        "pin": {"en": "Pin", "cs": "Připnout"},
        "pinTitle": {"en": "Screenshot Pinned", "cs": "Snímek připnut"},
        "pinDesc": {"en": "Selection pinned to screen", "cs": "Výřez připnut na obrazovku"},
    }

    def test_pin_keys_in_all_bundled_json_files(self):
        json_files = [f for f in os.listdir(LOCALIZATION_DIR) if f.endswith(".json")]
        self.assertGreaterEqual(len(json_files), 2, "Expected at least en.json and cs.json")

        for fname in json_files:
            fpath = os.path.join(LOCALIZATION_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            for key, expected_dict in self.PIN_KEYS.items():
                self.assertIn(key, data, f"Missing key '{key}' in {fname}")
                val = data[key]
                self.assertIsInstance(val, str, f"Key '{key}' in {fname} must be a string")
                self.assertTrue(len(val.strip()) > 0, f"Key '{key}' in {fname} must not be empty")

                # If reference lang, verify expected translation
                lang_code = fname[:-5]
                if lang_code in expected_dict:
                    self.assertEqual(val, expected_dict[lang_code], f"Unexpected translation for '{key}' in {fname}")

    def test_localization_template_check_tool(self):
        tool = os.path.join(REPO_DIR, "scripts", "localization_template.py")
        proc = subprocess.run(["python3", tool, "--check"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[OK]", proc.stdout)
        self.assertNotIn("[FAIL]", proc.stdout)

    def test_runner_pin_translation_lookup(self):
        """Test runner get_translation function for pin keys."""
        for lang in ["en", "cs"]:
            cmd = f"""
            set -e
            DIR="{REPO_DIR}"
            SMARTSHOT_LANG="{lang}"
            source <(sed -n "/# Sanitize language code/,/export SMARTSHOT_DIR/p" "{RUNNER_BIN}")
            source <(sed -n "/get_translation()/,/^}}/p" "{RUNNER_BIN}")
            echo "$(get_translation 'pin' 'FAIL')|$(get_translation 'pinTitle' 'FAIL')|$(get_translation 'pinDesc' 'FAIL')"
            """
            proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            pin_val, title_val, desc_val = proc.stdout.strip().split("|")
            self.assertEqual(pin_val, self.PIN_KEYS["pin"][lang])
            self.assertEqual(title_val, self.PIN_KEYS["pinTitle"][lang])
            self.assertEqual(desc_val, self.PIN_KEYS["pinDesc"][lang])


if __name__ == "__main__":
    unittest.main()
