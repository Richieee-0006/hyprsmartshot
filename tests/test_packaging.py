#!/usr/bin/env python3
"""
Unit tests for Arch Linux packaging (PKGBUILD, PKGBUILD-git, .SRCINFO, and desktop entry).
"""

import os
import shutil
import subprocess
import unittest

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARCH_DIR = os.path.join(REPO_DIR, "packaging", "arch")
PKGBUILD = os.path.join(ARCH_DIR, "PKGBUILD")
PKGBUILD_GIT = os.path.join(ARCH_DIR, "PKGBUILD-git")
DESKTOP_FILE = os.path.join(ARCH_DIR, "hyprsmartshot.desktop")
SRCINFO = os.path.join(ARCH_DIR, ".SRCINFO")
SRCINFO_GIT = os.path.join(ARCH_DIR, ".SRCINFO-git")

class TestArchPackaging(unittest.TestCase):
    def test_pkgbuild_files_exist(self):
        self.assertTrue(os.path.isfile(PKGBUILD), f"Missing {PKGBUILD}")
        self.assertTrue(os.path.isfile(PKGBUILD_GIT), f"Missing {PKGBUILD_GIT}")
        self.assertTrue(os.path.isfile(DESKTOP_FILE), f"Missing {DESKTOP_FILE}")
        self.assertTrue(os.path.isfile(SRCINFO), f"Missing {SRCINFO}")
        self.assertTrue(os.path.isfile(SRCINFO_GIT), f"Missing {SRCINFO_GIT}")

    def test_pkgbuild_syntax(self):
        proc = subprocess.run(["bash", "-n", PKGBUILD], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Syntax error in PKGBUILD: {proc.stderr}")

        proc_git = subprocess.run(["bash", "-n", PKGBUILD_GIT], capture_output=True, text=True)
        self.assertEqual(proc_git.returncode, 0, f"Syntax error in PKGBUILD-git: {proc_git.stderr}")

    def test_desktop_file_validation(self):
        if not shutil.which("desktop-file-validate"):
            self.skipTest("desktop-file-validate not available on host")
        proc = subprocess.run(["desktop-file-validate", DESKTOP_FILE], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Desktop file validation failed:\n{proc.stdout}\n{proc.stderr}")

    def test_srcinfo_generation(self):
        if not shutil.which("makepkg"):
            self.skipTest("makepkg not available on host")

        # Test release PKGBUILD .SRCINFO
        proc = subprocess.run(["makepkg", "--printsrcinfo"], cwd=ARCH_DIR, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"makepkg --printsrcinfo failed: {proc.stderr}")
        self.assertIn("pkgname = hyprsmartshot", proc.stdout)
        self.assertIn("depends = quickshell", proc.stdout)
        self.assertIn("depends = python-pyside6", proc.stdout)
        self.assertIn("depends = grim", proc.stdout)

        # Test git PKGBUILD .SRCINFO
        proc_git = subprocess.run(["makepkg", "-p", "PKGBUILD-git", "--printsrcinfo"], cwd=ARCH_DIR, capture_output=True, text=True)
        self.assertEqual(proc_git.returncode, 0, f"makepkg -p PKGBUILD-git --printsrcinfo failed: {proc_git.stderr}")
        self.assertIn("pkgname = hyprsmartshot-git", proc_git.stdout)
        self.assertIn("provides = hyprsmartshot", proc_git.stdout)
        self.assertIn("conflicts = hyprsmartshot", proc_git.stdout)

    def test_srcinfo_content(self):
        with open(SRCINFO, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("pkgname = hyprsmartshot", content)
        self.assertIn("depends = quickshell", content)
        self.assertIn("depends = python-pyside6", content)
        self.assertIn("depends = satty", content)
        self.assertIn("depends = wl-clipboard", content)

    def test_desktop_entry_fields(self):
        with open(DESKTOP_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[Desktop Entry]", content)
        self.assertIn("Type=Application", content)
        self.assertIn("Name=HyprSmartShot", content)
        self.assertIn("Exec=hyprsmartshot universal", content)
        self.assertIn("Icon=accessories-screenshot", content)

if __name__ == "__main__":
    unittest.main()
