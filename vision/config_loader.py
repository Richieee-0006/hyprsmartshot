#!/usr/bin/env python3
"""
Modular configuration, drop-in merging, and Pywal theme resolver for HyprSmartShot.
"""

import copy
import glob
import json
import os


MODULE_FILES = (
    "theme.json",
    "detection.json",
    "rating.json",
    "ai.json",
    "ui.json",
    "capture.json",
    "presets.json",
    "appRules.json",
)

DEFAULT_CONFIG = {
    "language": "en",
    "ocrLanguages": "eng",
    "postSaveHook": "",
    "postCopyHook": "",
    "activePreset": "default",
    "presets": {
        "default":  {"name": "Default",  "offsetX": 0, "offsetY": 0, "inset": 0, "filter": "all"},
        "browser":  {"name": "Browser",  "offsetX": 0, "offsetY": 0, "inset": 0, "filter": "content"},
        "terminal": {"name": "Terminal", "offsetX": 0, "offsetY": 0, "inset": 1, "filter": "window"},
        "game":     {"name": "Game",     "offsetX": 0, "offsetY": 0, "inset": 0, "filter": "dense"},
    },
    "appRules": {
        "firefox": "browser",
        "librewolf": "browser",
        "google-chrome": "browser",
        "chromium": "browser",
        "brave-browser": "browser",
        "vivaldi": "browser",
        "floorp": "browser",
        "zen-browser": "browser",
        "discord": "browser",
        "vesktop": "browser",
        "webcord": "browser",
        "equibop": "browser",
        "obsidian": "browser",
        "com.mojang.minecraft": "game",
        "minecraft": "game",
        "steam_app": "game",
        "gamescope": "game",
        "lutris": "game",
        "prismlauncher": "game",
        "kitty": "terminal",
        "alacritty": "terminal",
        "foot": "terminal",
        "ghostty": "terminal",
        "wezterm": "terminal",
        "konsole": "terminal",
        "gnome-terminal": "terminal",
    },
    "theme": {
        "mode": "pywal",
        "pywalPath": "~/.cache/wal/colors.json",
        "liveWatch": True,
        "syncSatty": False,
        "syncPinWindow": True,
        "dimOpacity": 0.65,
        "borderRadius": 10,
        "outlineThickness": 2,
        "pinBorderWidth": 2,
        "fontFamily": "JetBrainsMono Nerd Font",
        "pywalMap": {
            "accent": "color1",
            "accentHover": "color9",
            "selectionBorder": "color2",
            "snapBorder": "color3",
            "aiAccent": "color5",
            "pinBorder": "color4",
            "danger": "color1",
            "barBorder": "color8",
            "textSubtle": "color7",
        },
        "overrides": {},
    },
    "detection": {
        "enableText": True,
        "enablePanels": True,
        "enableGrids": True,
        "enableWindowContent": True,
        "minArea": 64,
        "maxAreaRatio": 0.98,
        "tinyContrastMin": 4.5,
        "adaptiveTextThreshold": True,
        "filterIconsFromText": True,
        "multiColumnParagraphs": True,
        "maxHeaderHeight": 96,
    },
    "rating": {
        "enabled": True,
        "minConfidence": 0.30,
        "adaptiveLearning": True,
        "learningRate": 0.08,
        "profilePath": "",
        "weights": {
            "contrast": 0.24,
            "geometry": 0.18,
            "edge": 0.22,
            "interior": 0.14,
            "semantic": 0.12,
            "presetFit": 0.10,
        },
    },
    "ai": {
        "enabled": False,
        "trigger": "manual",
        "provider": "openai_compatible",
        "timeoutMs": 35000,
        "maxImageDim": 960,
        "defaultAction": "ocr",
        "prompt": (
            "Locate 5 to 12 distinct visual UI regions in this screenshot (windows, panels, sidebars, code/text blocks, terminal output, top bar, dialogs, buttons, inputs). "
            "You MUST return at least 4 bounding boxes. "
            "Coordinates are normalized 0..1000 where x1,x2 are horizontal (left=0, right=1000) and y1,y2 are vertical (top=0, bottom=1000). "
            "Output ONLY a JSON array: "
            "[{\"label\":\"...\",\"type\":\"panel|button|input|slot|text_block\","
            "\"x1\":10,\"y1\":20,\"x2\":500,\"y2\":400,\"confidence\":0.9}]"
        ),
        "providers": {
            "copilot": {
                "baseUrl": "http://127.0.0.1:4141/v1",
                "model": "gpt-4.1",
                "apiKeyEnv": "GITHUB_TOKEN",
                "apiKey": "",
            },
            "local_llm": {
                "baseUrl": "http://127.0.0.1:8080/v1",
                "model": "qwen3.6-35b-vision",
                "apiKeyEnv": "OPENAI_API_KEY",
                "apiKey": "",
            },
            "ollama": {
                "baseUrl": "http://127.0.0.1:11434/v1",
                "model": "qwen2.5vl:7b",
                "apiKeyEnv": "",
                "apiKey": "",
            },
            "ovhcloud": {
                "baseUrl": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
                "model": "Qwen2.5-VL-72B-Instruct",
                "apiKeyEnv": "OVH_API_KEY",
                "apiKey": "",
            },
            "kilo": {
                "baseUrl": "https://api.kilo.ai/api/gateway",
                "model": "nvidia/nemotron-3.5-super-vl:free",
                "apiKeyEnv": "KILO_API_KEY",
                "apiKey": "",
            },
            "gemini": {
                "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
                "model": "gemini-3.5-flash-lite",
                "apiKeyEnv": "GEMINI_API_KEY",
                "apiKey": "",
            },
            "openrouter": {
                "baseUrl": "https://openrouter.ai/api/v1",
                "model": "dots-studio/dots-3-note-preview:free",
                "apiKeyEnv": "OPENROUTER_API_KEY",
                "apiKey": "",
            },
            "groq": {
                "baseUrl": "https://api.groq.com/openai/v1",
                "model": "qwen/qwen3.8-27b",
                "apiKeyEnv": "GROQ_API_KEY",
                "apiKey": "",
            },
            "mistral": {
                "baseUrl": "https://api.mistral.ai/v1",
                "model": "mistral-medium-3-5",
                "apiKeyEnv": "MISTRAL_API_KEY",
                "apiKey": "",
            },
            "openai_compatible": {
                "baseUrl": "http://127.0.0.1:8080/v1",
                "model": "qwen3.6-35b-vision",
                "apiKeyEnv": "OPENAI_API_KEY",
                "apiKey": "",
            },
        },
    },
    "ui": {
        "showConfidenceBadge": True,
        "sortByRating": True,
        "showMagnifierByDefault": False,
        "magnifierZoom": 3.0,
        "magnifierSize": 180,
        "showHints": True,
        "animations": True,
    },
    "capture": {
        "imageFormat": "png",
        "pngCompression": 4,
        "defaultSaveDir": "",
        "copyAfterSave": True,
    },
}


def deep_merge(base, patch):
    """Recursively merges patch dict onto base dict without mutating inputs."""
    if not isinstance(base, dict):
        base = {}
    if not isinstance(patch, dict):
        return copy.deepcopy(base)
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve_repo_dir():
    env_dir = os.environ.get("SMARTSHOT_DIR", "").strip()
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def resolve_config_dir(config_path=None):
    if config_path:
        return os.path.dirname(os.path.abspath(os.path.expanduser(config_path)))
    xdg_cfg = os.environ.get("XDG_CONFIG_HOME", "").strip() or os.path.expanduser("~/.config")
    return os.path.join(xdg_cfg, "hyprsmartshot")


def resolve_config_path(config_path=None):
    explicit = config_path or os.environ.get("SMARTSHOT_CONFIG", "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.join(resolve_config_dir(), "config.json")


def resolve_state_dir():
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip() or os.path.expanduser("~/.local/state")
    return os.path.join(xdg_state, "hyprsmartshot")


def _read_json_if_valid(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _apply_module_files_and_dropins(cfg, directory):
    if not directory or not os.path.isdir(directory):
        return cfg

    for mod_name in MODULE_FILES:
        section_key = mod_name[:-5]
        mod_data = _read_json_if_valid(os.path.join(directory, mod_name))
        if mod_data is not None:
            if section_key in mod_data and len(mod_data) == 1 and isinstance(mod_data[section_key], dict):
                cfg = deep_merge(cfg, mod_data)
            elif section_key in DEFAULT_CONFIG and isinstance(DEFAULT_CONFIG[section_key], dict):
                cfg = deep_merge(cfg, {section_key: mod_data})
            else:
                cfg = deep_merge(cfg, mod_data)

    drop_dir = os.path.join(directory, "config.d")
    if os.path.isdir(drop_dir):
        for path in sorted(glob.glob(os.path.join(drop_dir, "*.json"))):
            patch = _read_json_if_valid(path)
            if patch is not None:
                cfg = deep_merge(cfg, patch)
    return cfg


def load_config(config_path=None, cli_overrides=None):
    """
    Loads modular configuration from:
      1. Built-in DEFAULT_CONFIG
      2. Bundled repo config/hyprsmartshot/config.json + bundled modules/config.d
      3. User config ($SMARTSHOT_CONFIG or ~/.config/hyprsmartshot/config.json) + user modules + user config.d/*.json
      4. Optional cli_overrides dict
    """
    cfg = copy.deepcopy(DEFAULT_CONFIG)

    repo_cfg_dir = os.path.join(resolve_repo_dir(), "config", "hyprsmartshot")
    repo_base = _read_json_if_valid(os.path.join(repo_cfg_dir, "config.json"))
    if repo_base:
        cfg = deep_merge(cfg, repo_base)
    cfg = _apply_module_files_and_dropins(cfg, repo_cfg_dir)

    user_cfg_path = resolve_config_path(config_path)
    user_cfg_dir = os.path.dirname(user_cfg_path)
    user_base = _read_json_if_valid(user_cfg_path)
    if user_base:
        cfg = deep_merge(cfg, user_base)
    cfg = _apply_module_files_and_dropins(cfg, user_cfg_dir)

    if isinstance(cli_overrides, dict):
        cfg = deep_merge(cfg, cli_overrides)

    return cfg


def save_user_config(data, config_path=None):
    """Atomically writes user configuration JSON without creating .bak files."""
    path = resolve_config_path(config_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, path)
    return path


def _hex_to_rgb(hex_str):
    s = str(hex_str or "").strip().lstrip("#")
    if len(s) < 6:
        return (24, 24, 30)
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return (24, 24, 30)


def _luminance(hex_str):
    r, g, b = _hex_to_rgb(hex_str)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _mix_hex(hex_a, hex_b, t):
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    r = int(round(ra + (rb - ra) * t))
    g = int(round(ga + (gb - ga) * t))
    b = int(round(ba + (bb - ba) * t))
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def resolve_pywal_palette(cfg=None):
    """Resolves unified color tokens from Pywal colors.json + theme overrides."""
    if cfg is None:
        cfg = load_config()
    theme_cfg = cfg.get("theme", {}) if isinstance(cfg, dict) else {}
    mode = str(theme_cfg.get("mode", "pywal")).lower()

    palette = {
        "source": "static",
        "isLight": False,
        "background": "#141419",
        "barBackground": "#1e1e26",
        "cardBackground": "#282833",
        "barBorder": "#45475a",
        "accent": "#eb6960",
        "accentHover": "#f2857d",
        "selectionBorder": "#68df93",
        "snapBorder": "#f3c568",
        "aiAccent": "#955eed",
        "pinBorder": "#6496ff",
        "danger": "#ff6b6b",
        "text": "#ffffff",
        "textSubtle": "#b8b8c4",
        "onAccent": "#ffffff",
        "sattyPalette": [],
    }

    pywal_path = os.path.expanduser(str(theme_cfg.get("pywalPath", "~/.cache/wal/colors.json")))
    wal = _read_json_if_valid(pywal_path) if mode in ("pywal", "auto") else None

    if wal and isinstance(wal.get("colors"), dict):
        colors = wal["colors"]
        special = wal.get("special", {}) if isinstance(wal.get("special"), dict) else {}
        bg = special.get("background") or colors.get("color0") or palette["background"]
        fg = special.get("foreground") or colors.get("color15") or palette["text"]
        is_light = _luminance(bg) > 0.55

        palette["source"] = "pywal"
        palette["isLight"] = is_light
        palette["background"] = bg
        palette["text"] = fg
        palette["barBackground"] = _mix_hex(bg, fg, 0.08)
        palette["cardBackground"] = _mix_hex(bg, fg, 0.14)

        wal_map = theme_cfg.get("pywalMap", {}) if isinstance(theme_cfg.get("pywalMap"), dict) else {}
        for token, fallback_role in (
            ("accent", "color1"),
            ("accentHover", "color9"),
            ("selectionBorder", "color2"),
            ("snapBorder", "color3"),
            ("aiAccent", "color5"),
            ("pinBorder", "color4"),
            ("danger", "color1"),
            ("barBorder", "color8"),
            ("textSubtle", "color7"),
        ):
            role = wal_map.get(token, fallback_role)
            if isinstance(role, str):
                if role.startswith("#"):
                    palette[token] = role
                elif role in colors and colors[role]:
                    palette[token] = colors[role]

        palette["onAccent"] = "#111116" if _luminance(palette["accent"]) > 0.58 else "#ffffff"
        palette["sattyPalette"] = [
            f"{colors[k].lstrip('#')}ff"
            for k in ("color1", "color3", "color2", "color4", "color5", "color6", "color7", "color0")
            if k in colors and isinstance(colors[k], str) and colors[k].startswith("#")
        ]

    overrides = theme_cfg.get("overrides", {})
    if isinstance(overrides, dict):
        for k, v in overrides.items():
            if k in palette and isinstance(v, str) and v.strip():
                palette[k] = v.strip()

    return palette


def export_satty_pywal_config(cfg=None, output_path=None):
    """Writes a non-destructive Satty palette fragment synced from Pywal colors."""
    if cfg is None:
        cfg = load_config()
    pal = resolve_pywal_palette(cfg)
    colors = pal.get("sattyPalette") or [
        "eb6960ff", "f3c568ff", "68df93ff", "6496ffff",
        "955eedff", "df5eedff", "ebeaebff", "18121aff",
    ]
    out_dir = os.path.join(
        os.environ.get("XDG_CACHE_HOME", "").strip() or os.path.expanduser("~/.cache"),
        "hyprsmartshot",
    )
    target = output_path or os.path.join(out_dir, "satty-pywal.toml")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    formatted = ",\n".join(f'    "#{c.lstrip("#")}"' for c in colors)
    content = (
        "# Generated by HyprSmartShot Pywal theme sync\n"
        "[color-palette]\n"
        "palette = [\n"
        f"{formatted}\n"
        "]\n"
    )
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return target


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="HyprSmartShot Modular Config Loader CLI")
    parser.add_argument("--config", default=None, help="Explicit user config path")
    parser.add_argument("--dump-merged", action="store_true", help="Print full merged config JSON")
    parser.add_argument("--palette", action="store_true", help="Print resolved Pywal/theme palette JSON")
    parser.add_argument("--sync-satty", action="store_true", help="Export satty-pywal.toml fragment")
    parser.add_argument("--patch-stdin", action="store_true", help="Deep-merge JSON patch from stdin into user config.json")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.patch_stdin:
        raw = sys.stdin.read().strip()
        patch = json.loads(raw) if raw else {}
        target = resolve_config_path(args.config)
        existing = _read_json_if_valid(target) or {}
        merged_user = deep_merge(existing, patch)
        saved_path = save_user_config(merged_user, args.config)
        print(json.dumps({"ok": True, "path": saved_path}))
        return 0
    if args.sync_satty:
        out_path = export_satty_pywal_config(cfg)
        print(json.dumps({"ok": True, "path": out_path}))
        return 0
    if args.palette:
        print(json.dumps(resolve_pywal_palette(cfg)))
        return 0
    if args.dump_merged:
        print(json.dumps(cfg))
        return 0

    print(json.dumps({"configPath": resolve_config_path(args.config), "themeMode": cfg.get("theme", {}).get("mode")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
