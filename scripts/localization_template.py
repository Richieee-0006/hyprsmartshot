#!/usr/bin/env python3
"""
HyprSmartShot Localization Management & Template Generator.

Generates translation templates from en.json, validates key parity,
and manages bundled and user-level localization files.
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
REPO_LOCALIZATION_DIR = os.path.join(REPO_DIR, "localization")
EN_FILE = os.path.join(REPO_LOCALIZATION_DIR, "en.json")


def get_user_localization_dir() -> str:
    xdg_config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg_config, "hyprsmartshot", "localization")


def extract_placeholders(text: str) -> Set[str]:
    return set(re.findall(r"\{([a-zA-Z0-9_]+)\}", text))


def load_en_reference() -> Dict[str, str]:
    if not os.path.isfile(EN_FILE):
        sys.stderr.write(f"Error: Reference localization file not found: {EN_FILE}\n")
        sys.exit(1)
    with open(EN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_lang_code(code: str) -> bool:
    return bool(re.match(r"^[a-zA-Z]{2,3}([-_][a-zA-Z0-9]+)?$", code))


def create_template(
    lang: str,
    output_path: Optional[str] = None,
    empty: bool = False,
    force: bool = False,
    user: bool = False,
) -> int:
    if not output_path:
        if not validate_lang_code(lang):
            sys.stderr.write(
                f"Error: Invalid language code '{lang}'. Expected format like 'de', 'fr', 'pt_BR', 'zh_CN'.\n"
            )
            return 1
        clean_code = lang.replace("-", "_").lower()
        if user:
            dest_dir = get_user_localization_dir()
        else:
            dest_dir = REPO_LOCALIZATION_DIR
        target = os.path.join(dest_dir, f"{clean_code}.json")
    else:
        target = os.path.abspath(output_path)

    if os.path.exists(target) and not force:
        sys.stderr.write(
            f"Error: Target file already exists: {target}\nUse --force to overwrite.\n"
        )
        return 1

    en_data = load_en_reference()
    if empty:
        template_data = {k: "" for k in en_data.keys()}
    else:
        template_data = dict(en_data)

    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(template_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    mode_str = "empty " if empty else ""
    print(f"Created {mode_str}localization template: {target} ({len(template_data)} keys)")
    return 0


def check_file(path: str, en_data: Dict[str, str]) -> Tuple[bool, List[str]]:
    rel_path = os.path.relpath(path, REPO_DIR) if path.startswith(REPO_DIR) else path
    issues: List[str] = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"[FAIL] {rel_path}: Invalid JSON syntax ({e})"]

    if not isinstance(data, dict):
        return False, [f"[FAIL] {rel_path}: Root JSON element must be an object"]

    en_keys = set(en_data.keys())
    data_keys = set(data.keys())

    missing_keys = [k for k in en_data.keys() if k not in data_keys]
    extra_keys = [k for k in data.keys() if k not in en_keys]

    failed = False
    if missing_keys:
        failed = True
        issues.append(f"  Missing keys ({len(missing_keys)}): {', '.join(missing_keys)}")
    if extra_keys:
        failed = True
        issues.append(f"  Extra keys ({len(extra_keys)}): {', '.join(extra_keys)}")

    # Check placeholder parity
    for k in en_keys.intersection(data_keys):
        en_ph = extract_placeholders(en_data[k])
        val = data[k]
        if isinstance(val, str):
            val_ph = extract_placeholders(val)
            if en_ph != val_ph:
                issues.append(
                    f"  Warning: Placeholder mismatch in '{k}': expected {sorted(en_ph)}, got {sorted(val_ph)}"
                )
        else:
            failed = True
            issues.append(f"  Type error: Key '{k}' value must be a string, got {type(val).__name__}")

    # Check for empty strings
    empty_keys = [k for k, v in data.items() if isinstance(v, str) and not v.strip()]
    if empty_keys:
        issues.append(f"  Notice: {len(empty_keys)} untranslated / empty keys")

    if failed:
        header = f"[FAIL] {rel_path}"
    else:
        header = f"[OK]   {rel_path}: {len(data_keys)}/{len(en_keys)} keys valid"

    return not failed, [header] + issues


def run_check(target: Optional[str]) -> int:
    en_data = load_en_reference()
    files_to_check: List[str] = []

    if target and target != "__ALL__":
        if os.path.isfile(target):
            files_to_check.append(os.path.abspath(target))
        else:
            clean_code = target.replace("-", "_").lower()
            repo_candidate = os.path.join(REPO_LOCALIZATION_DIR, f"{clean_code}.json")
            user_candidate = os.path.join(get_user_localization_dir(), f"{clean_code}.json")
            if os.path.isfile(repo_candidate):
                files_to_check.append(repo_candidate)
            elif os.path.isfile(user_candidate):
                files_to_check.append(user_candidate)
            else:
                sys.stderr.write(
                    f"Error: Localization file for '{target}' not found (checked repo and user config).\n"
                )
                return 1
    else:
        if os.path.isdir(REPO_LOCALIZATION_DIR):
            for fname in sorted(os.listdir(REPO_LOCALIZATION_DIR)):
                if fname.endswith(".json"):
                    files_to_check.append(os.path.join(REPO_LOCALIZATION_DIR, fname))

    if not files_to_check:
        print("No localization files found to check.")
        return 0

    all_passed = True
    for file_path in files_to_check:
        passed, log_lines = check_file(file_path, en_data)
        if not passed:
            all_passed = False
        for line in log_lines:
            print(line)

    return 0 if all_passed else 1


def list_localizations() -> int:
    en_data = load_en_reference()
    total_keys = len(en_data)

    print(f"Reference language: en ({total_keys} keys)")
    print(f"\nBundled localizations ({REPO_LOCALIZATION_DIR}):")
    bundled = []
    if os.path.isdir(REPO_LOCALIZATION_DIR):
        for fname in sorted(os.listdir(REPO_LOCALIZATION_DIR)):
            if fname.endswith(".json"):
                fpath = os.path.join(REPO_LOCALIZATION_DIR, fname)
                passed, _ = check_file(fpath, en_data)
                code = fname[:-5]
                status = "OK" if passed else "INCOMPLETE"
                bundled.append(f"  - {code:8} [{status}] ({fpath})")

    if bundled:
        for line in bundled:
            print(line)
    else:
        print("  (none)")

    user_dir = get_user_localization_dir()
    print(f"\nUser localizations ({user_dir}):")
    user_files = []
    if os.path.isdir(user_dir):
        for fname in sorted(os.listdir(user_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(user_dir, fname)
                passed, _ = check_file(fpath, en_data)
                code = fname[:-5]
                status = "OK" if passed else "INCOMPLETE"
                user_files.append(f"  - {code:8} [{status}] ({fpath})")

    if user_files:
        for line in user_files:
            print(line)
    else:
        print("  (none)")

    return 0


def main() -> int:
    # Normalize subcommand syntax: e.g. "create de" -> "de", "check cs" -> "--check cs", "list" -> "--list"
    raw_args = sys.argv[1:]
    if raw_args:
        first = raw_args[0]
        if first == "create":
            raw_args.pop(0)
        elif first == "check":
            raw_args.pop(0)
            raw_args = ["--check"] + raw_args
        elif first == "list":
            raw_args.pop(0)
            raw_args = ["--list"] + raw_args

    parser = argparse.ArgumentParser(
        description="HyprSmartShot Localization Management & Template Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  scripts/localization_template.py de                          # Create localization/de.json from en.json
  scripts/localization_template.py de --empty                  # Create localization/de.json with empty values
  scripts/localization_template.py de --user                   # Create ~/.config/hyprsmartshot/localization/de.json
  scripts/localization_template.py --check                     # Check all bundled localization files
  scripts/localization_template.py --check cs                  # Check specific language (cs)
  scripts/localization_template.py --check path/to/file.json   # Check specific json file
  scripts/localization_template.py --list                      # List available language files
""",
    )

    parser.add_argument(
        "lang",
        nargs="?",
        default=None,
        help="Language code to generate template for (e.g. 'de', 'fr', 'ja', 'pt_BR')",
    )
    parser.add_argument(
        "-c",
        "--check",
        nargs="?",
        const="__ALL__",
        default=None,
        metavar="LANG_OR_FILE",
        help="Validate key parity and formatting for all or specified language",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List all bundled and user localizations",
    )
    parser.add_argument(
        "-u",
        "--user",
        action="store_true",
        help="Write template to user config directory (~/.config/hyprsmartshot/localization/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="Explicit destination file path for generated template",
    )
    parser.add_argument(
        "--empty",
        action="store_true",
        help="Populate template values with empty strings instead of English reference",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )

    args = parser.parse_args(raw_args)

    if args.list:
        return list_localizations()

    if args.check is not None:
        return run_check(args.check)

    if args.lang or args.output:
        return create_template(
            lang=args.lang or "",
            output_path=args.output,
            empty=args.empty,
            force=args.force,
            user=args.user,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
