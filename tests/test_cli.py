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
        self.assertIn("Valid commands: universal, screen, full", proc.stderr)

    def test_install_script_syntax(self):
        proc = subprocess.run(["bash", "-n", INSTALL_SH], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_runner_script_syntax(self):
        proc = subprocess.run(["bash", "-n", RUNNER_BIN], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

if __name__ == "__main__":
    unittest.main()
