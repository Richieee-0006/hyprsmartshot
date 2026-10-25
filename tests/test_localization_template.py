#!/usr/bin/env python3
"""
Unit tests for scripts/localization_template.py.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT_PATH = os.path.join(REPO_DIR, "scripts", "localization_template.py")
EN_PATH = os.path.join(REPO_DIR, "localization", "en.json")


class TestLocalizationTemplateScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(EN_PATH, "r", encoding="utf-8") as f:
            cls.en_data = json.load(f)

    def run_script(self, args, env=None):
        cmd = [sys.executable, SCRIPT_PATH] + args
        custom_env = os.environ.copy()
        if env:
            custom_env.update(env)
        return subprocess.run(
            cmd,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            env=custom_env,
        )

    def test_help_output(self):
        proc = self.run_script(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("HyprSmartShot Localization Management", proc.stdout)
        self.assertIn("--check", proc.stdout)
        self.assertIn("--list", proc.stdout)

    def test_list_bundled(self):
        proc = self.run_script(["--list"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Reference language: en", proc.stdout)
        self.assertIn("cs", proc.stdout)
        self.assertIn("en", proc.stdout)

    def test_check_all_bundled(self):
        proc = self.run_script(["--check"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("[OK]   localization/cs.json", proc.stdout)
        self.assertIn("[OK]   localization/en.json", proc.stdout)

    def test_check_specific_lang(self):
        proc = self.run_script(["--check", "cs"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("[OK]   localization/cs.json", proc.stdout)

    def test_check_nonexistent_lang(self):
        proc = self.run_script(["--check", "nonexistent_lang_code"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not found", proc.stderr.lower())

    def test_create_template_with_output_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "de.json")
            proc = self.run_script(["de", "-o", out_path])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.isfile(out_path))

            with open(out_path, "r", encoding="utf-8") as f:
                created_data = json.load(f)

            self.assertEqual(set(created_data.keys()), set(self.en_data.keys()))
            self.assertEqual(created_data["modeSmart"], self.en_data["modeSmart"])

    def test_create_empty_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "fr.json")
            proc = self.run_script(["fr", "--empty", "-o", out_path])
            self.assertEqual(proc.returncode, 0, proc.stderr)

            with open(out_path, "r", encoding="utf-8") as f:
                created_data = json.load(f)

            self.assertEqual(set(created_data.keys()), set(self.en_data.keys()))
            for key, val in created_data.items():
                self.assertEqual(val, "", f"Expected empty value for {key}")

    def test_overwrite_protection_and_force(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "es.json")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write('{"modeSmart": "Original"}\n')

            # Without --force should fail
            proc = self.run_script(["es", "-o", out_path])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("already exists", proc.stderr)

            # With --force should succeed
            proc_force = self.run_script(["es", "-f", "-o", out_path])
            self.assertEqual(proc_force.returncode, 0, proc_force.stderr)
            with open(out_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["modeSmart"], self.en_data["modeSmart"])

    def test_invalid_language_code(self):
        proc = self.run_script(["invalid/code!"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("invalid language code", proc.stderr.lower())

    def test_check_validation_catches_missing_and_extra_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "bad.json")
            bad_data = {
                "modeSmart": "Smart",
                "nonexistentKey": "Hello",
            }
            with open(bad_path, "w", encoding="utf-8") as f:
                json.dump(bad_data, f)

            proc = self.run_script(["--check", bad_path])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("[FAIL]", proc.stdout)
            self.assertIn("Missing keys", proc.stdout)
            self.assertIn("Extra keys", proc.stdout)

    def test_create_user_template(self):
        with tempfile.TemporaryDirectory() as tmp_xdg:
            proc = self.run_script(
                ["it", "--user"],
                env={"XDG_CONFIG_HOME": tmp_xdg},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            expected_file = os.path.join(tmp_xdg, "hyprsmartshot", "localization", "it.json")
            self.assertTrue(os.path.isfile(expected_file))


if __name__ == "__main__":
    unittest.main()
