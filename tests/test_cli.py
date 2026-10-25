#!/usr/bin/env python3
"""
Unit tests for HyprSmartShot CLI argument handling, help/version flags, and installer.
"""

import os
import subprocess
import unittest

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNNER_BIN = os.path.join(REPO_DIR, "bin", "hyprsmartshot")
INSTALL_SH = os.path.join(REPO_DIR, "install.sh")

class TestCLIArguments(unittest.TestCase):
    def test_help_flag_long(self):
        proc = subprocess.run([RUNNER_BIN, "--help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("HyprSmartShot v", proc.stdout)
        self.assertIn("Usage:", proc.stdout)
        self.assertIn("universal", proc.stdout)
        self.assertIn("screen", proc.stdout)
        self.assertIn("full", proc.stdout)
        self.assertIn("pin", proc.stdout)

    def test_help_flag_short(self):
        proc = subprocess.run([RUNNER_BIN, "-h"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("HyprSmartShot v", proc.stdout)
        self.assertIn("Usage:", proc.stdout)

    def test_help_subcommand(self):
        proc = subprocess.run([RUNNER_BIN, "help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("HyprSmartShot v", proc.stdout)
        self.assertIn("Usage:", proc.stdout)

    def test_version_flag_long(self):
        proc = subprocess.run([RUNNER_BIN, "--version"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hyprsmartshot v0.0.1", proc.stdout)

    def test_version_flag_short(self):
        proc = subprocess.run([RUNNER_BIN, "-v"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hyprsmartshot v0.0.1", proc.stdout)

    def test_version_subcommand(self):
        proc = subprocess.run([RUNNER_BIN, "version"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hyprsmartshot v0.0.1", proc.stdout)

    def test_unknown_option_error(self):
        proc = subprocess.run([RUNNER_BIN, "--unknown-flag"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Unknown option '--unknown-flag'", proc.stderr)
        self.assertIn("Run 'hyprsmartshot --help' for usage.", proc.stderr)

    def test_unknown_command_error(self):
        proc = subprocess.run([RUNNER_BIN, "invalid_action"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Unknown command 'invalid_action'", proc.stderr)
        self.assertIn("Valid commands: universal, screen, full, pin", proc.stderr)

    def test_pin_missing_argument(self):
        proc = subprocess.run([RUNNER_BIN, "pin"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Missing image path for 'pin'", proc.stderr)
        self.assertIn("Usage: hyprsmartshot pin", proc.stderr)

    def test_pin_nonexistent_image(self):
        proc = subprocess.run([RUNNER_BIN, "pin", "/tmp/nonexistent_image_12345.png"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Image not found:", proc.stderr)

    def test_unexpected_extra_arguments(self):
        proc = subprocess.run([RUNNER_BIN, "universal", "extra_argument"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Unexpected argument 'extra_argument'", proc.stderr)
        self.assertIn("Run 'hyprsmartshot --help' for usage.", proc.stderr)

    def test_help_flag_with_subcommand(self):
        proc = subprocess.run([RUNNER_BIN, "universal", "--help"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage:", proc.stdout)

    def test_version_flag_with_subcommand(self):
        proc = subprocess.run([RUNNER_BIN, "screen", "-v"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hyprsmartshot v0.0.1", proc.stdout)

    def test_symlink_execution_and_dir_resolution(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            symlink_bin = os.path.join(tmp_dir, "hyprsmartshot")
            os.symlink(RUNNER_BIN, symlink_bin)

            # Test invocation via symlink
            proc = subprocess.run([symlink_bin, "--version"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("hyprsmartshot v0.0.1", proc.stdout)

            proc_help = subprocess.run([symlink_bin, "--help"], capture_output=True, text=True)
            self.assertEqual(proc_help.returncode, 0)
            self.assertIn("HyprSmartShot v", proc_help.stdout)

            # Verify DIR was resolved to REPO_DIR
            proc_trace = subprocess.run(["bash", "-x", symlink_bin, "--version"], capture_output=True, text=True)
            self.assertEqual(proc_trace.returncode, 0)
            self.assertIn(f"+ DIR={REPO_DIR}", proc_trace.stderr)

    def test_install_script_custom_dirs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_bin = os.path.join(tmp_dir, "bin")
            custom_config = os.path.join(tmp_dir, "config")
            env = os.environ.copy()
            env["BIN_DIR"] = custom_bin
            env["XDG_CONFIG_HOME"] = custom_config

            # Run install script without reinstalling pip packages in temp
            # by executing bash up to the symlink and config steps
            proc = subprocess.run([
                "bash", "-c",
                f'source "{INSTALL_SH}"'
            ], env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Verify symlink created in custom BIN_DIR
            symlink_path = os.path.join(custom_bin, "hyprsmartshot")
            self.assertTrue(os.path.islink(symlink_path))
            self.assertEqual(os.path.realpath(symlink_path), RUNNER_BIN)

            # Verify config created in custom XDG_CONFIG_HOME
            app_cfg = os.path.join(custom_config, "hyprsmartshot", "config.json")
            satty_cfg = os.path.join(custom_config, "satty", "config.toml")
            self.assertTrue(os.path.isfile(app_cfg))
            self.assertTrue(os.path.isfile(satty_cfg))

    def test_install_script_syntax(self):
        proc = subprocess.run(["bash", "-n", INSTALL_SH], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_runner_script_syntax(self):
        proc = subprocess.run(["bash", "-n", RUNNER_BIN], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_pin_script_usage(self):
        pin_script = os.path.join(REPO_DIR, "scripts", "pin_window.py")
        proc = subprocess.run(["python3", pin_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Usage: pin_window.py", proc.stderr)

    def test_pin_script_missing_file(self):
        pin_script = os.path.join(REPO_DIR, "scripts", "pin_window.py")
        proc = subprocess.run(["python3", pin_script, "/nonexistent/test.png"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Error: Image not found:", proc.stderr)

if __name__ == "__main__":
    unittest.main()
