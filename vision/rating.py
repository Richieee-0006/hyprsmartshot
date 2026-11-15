#!/usr/bin/env python3
"""
AI-like heuristic + adaptive box rating system for HyprSmartShot.
Computes normalized confidence [0.0, 1.0] and percentage score [0, 100],
ranks candidates per preset, filters noise, and learns from user feedback.
"""

import argparse
import json
import os
import sys

_VISION_DIR = os.path.dirname(os.path.abspath(__file__))
if _VISION_DIR not in sys.path:
    sys.path.insert(0, _VISION_DIR)

from config_loader import load_config, resolve_state_dir


DEFAULT_WEIGHTS = {
    "contrast": 0.24,
    "geometry": 0.18,
    "edge": 0.22,
    "interior": 0.14,
    "semantic": 0.12,
    "presetFit": 0.10,
}

BASE_TYPE_SCORE = {
    "floating_window": 0.96,
    "window": 0.94,
    "ai": 0.92,
    "grid_container": 0.88,
    "grid_row": 0.84,
    "panel": 0.84,
    "content": 0.84,
    "input": 0.82,
    "button": 0.78,
    "slot": 0.76,
    "item": 0.74,
    "text_block": 0.75,
    "text": 0.72,
    "detected": 0.62,
}

PRESET_TYPE_FIT = {
    "default": {
        "window": 0.92, "floating_window": 0.95, "panel": 0.90, "content": 0.88,
        "input": 0.86, "button": 0.82, "text_block": 0.82, "text": 0.78,
        "slot": 0.72, "item": 0.68, "grid_row": 0.76, "grid_container": 0.80,
        "detected": 0.60, "ai": 0.95,
    },
    "browser": {
        "panel": 0.95, "content": 0.96, "input": 0.92, "button": 0.88,
        "text_block": 0.88, "text": 0.82, "window": 0.86, "floating_window": 0.88,
        "detected": 0.74, "slot": 0.35, "item": 0.30, "grid_row": 0.35,
        "grid_container": 0.40, "ai": 0.95,
    },
    "terminal": {
        "window": 0.96, "floating_window": 0.95, "panel": 0.92, "content": 0.90,
        "text_block": 0.92, "text": 0.88, "input": 0.86, "detected": 0.45,
        "button": 0.35, "slot": 0.25, "item": 0.20, "grid_row": 0.25,
        "grid_container": 0.25, "ai": 0.94,
    },
    "game": {
        "slot": 0.96, "item": 0.92, "grid_row": 0.95, "grid_container": 0.96,
        "panel": 0.90, "button": 0.86, "input": 0.78, "detected": 0.76,
        "window": 0.84, "floating_window": 0.86, "text_block": 0.42, "text": 0.35,
        "ai": 0.96,
    },
}


def resolve_profile_path(rating_cfg=None):
    explicit = ""
    if isinstance(rating_cfg, dict):
        explicit = str(rating_cfg.get("profilePath", "") or "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.join(resolve_state_dir(), "rating_profile.json")


def load_rating_profile(profile_path=None):
    path = profile_path or resolve_profile_path()
    if not os.path.isfile(path):
        return {"version": 1, "biases": {}, "samples": 0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("biases"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "biases": {}, "samples": 0}


def save_rating_profile(profile, profile_path=None):
    path = profile_path or resolve_profile_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)
    return path


def _size_bucket(w, h):
    area = max(1, int(w) * int(h))
    if area < 1200:
        return "xs"
    if area < 12000:
        return "sm"
    if area < 90000:
        return "md"
    if area < 450000:
        return "lg"
    return "xl"


def _profile_key(box_type, w, h, preset_key):
    return f"{preset_key or 'default'}:{box_type or 'detected'}:{_size_bucket(w, h)}"


def record_feedback(box_type, w, h, liked=True, preset_key="default", config=None, profile_path=None):
    """Updates adaptive rating bias for similar UI boxes using bounded EMA."""
    cfg = config if isinstance(config, dict) else load_config()
    rating_cfg = cfg.get("rating", {})
    if not rating_cfg.get("adaptiveLearning", True):
        return load_rating_profile(profile_path)

    path = profile_path or resolve_profile_path(rating_cfg)
    profile = load_rating_profile(path)
    lr = float(rating_cfg.get("learningRate", 0.08) or 0.08)
    target = 0.25 if liked else -0.25

    key = _profile_key(box_type, w, h, preset_key)
    cur = float(profile["biases"].get(key, 0.0))
    updated = cur + lr * (target - cur)
    profile["biases"][key] = round(max(-0.25, min(0.25, updated)), 4)
    profile["samples"] = int(profile.get("samples", 0)) + 1
    save_rating_profile(profile, path)
    return profile


def score_box(box, active_preset="default", rating_cfg=None, profile=None):
    """Computes normalized confidence [0.0, 1.0] for one detected UI box."""
    cfg = rating_cfg if isinstance(rating_cfg, dict) else {}
    raw_weights = cfg.get("weights", {})
    weights = {k: float(raw_weights.get(k, v)) for k, v in DEFAULT_WEIGHTS.items()}
    w_sum = sum(max(0.0, v) for v in weights.values()) or 1.0

    b_type = str(box.get("type", "detected"))
    w = max(1, int(box.get("w", 1)))
    h = max(1, int(box.get("h", 1)))

    if box.get("source") == "ai" or b_type == "ai":
        ai_conf = float(box.get("ai_confidence", box.get("confidence", 0.88)) or 0.88)
        base = max(0.05, min(0.99, ai_conf))
        bias = 0.0
        if profile and cfg.get("adaptiveLearning", True):
            bias = float(profile.get("biases", {}).get(_profile_key(b_type, w, h, active_preset), 0.0))
        conf = round(max(0.0, min(1.0, base + bias)), 3)
        return conf, int(round(conf * 100))

    if box.get("is_client") or b_type in ("window", "floating_window"):
        conf = 0.98 if b_type == "floating_window" else 0.96
        return conf, int(round(conf * 100))

    contrast = float(box.get("contrast", 20.0) or 0.0)
    extent = float(box.get("extent", 0.75) or 0.5)

    contrast_s = min(1.0, max(0.0, contrast / 32.0))
    aspect = max(w, h) / float(min(w, h))
    aspect_penalty = 0.0 if aspect <= 18.0 else min(0.45, (aspect - 18.0) * 0.02)
    geometry_s = max(0.0, min(1.0, (extent * 0.9 + 0.15) - aspect_penalty))

    if "edge_score" in box:
        edge_s = max(0.0, min(1.0, float(box["edge_score"])))
    elif b_type in ("text", "text_block", "grid_row", "grid_container", "content"):
        edge_s = 0.84
    else:
        edge_s = min(1.0, 0.55 + contrast_s * 0.40)

    if "interior_edge" in box:
        interior_s = max(0.0, min(1.0, 1.0 - max(0.0, float(box["interior_edge"]) - 0.18) * 1.15))
    else:
        interior_s = 0.82

    semantic_s = BASE_TYPE_SCORE.get(b_type, 0.62)
    fit_table = PRESET_TYPE_FIT.get(active_preset or "default", PRESET_TYPE_FIT["default"])
    preset_s = fit_table.get(b_type, 0.62)

    raw_score = (
        contrast_s * weights["contrast"]
        + geometry_s * weights["geometry"]
        + edge_s * weights["edge"]
        + interior_s * weights["interior"]
        + semantic_s * weights["semantic"]
        + preset_s * weights["presetFit"]
    ) / w_sum

    bias = 0.0
    if profile and cfg.get("adaptiveLearning", True):
        key = _profile_key(b_type, w, h, active_preset)
        bias = float(profile.get("biases", {}).get(key, 0.0))

    conf = round(max(0.0, min(1.0, raw_score + bias)), 3)
    return conf, int(round(conf * 100))


def rate_and_filter_boxes(boxes, active_preset="default", config=None, profile_path=None):
    """Attaches confidence/score to boxes and drops weak noise below minConfidence."""
    cfg = config if isinstance(config, dict) else load_config()
    rating_cfg = cfg.get("rating", {})
    enabled = bool(rating_cfg.get("enabled", True))
    min_conf = float(rating_cfg.get("minConfidence", 0.30) or 0.0)
    profile = load_rating_profile(profile_path or resolve_profile_path(rating_cfg)) if enabled else None

    out = []
    for box in boxes:
        item = dict(box)
        if not enabled:
            conf = float(item.get("confidence", 0.80))
            item["confidence"] = round(conf, 3)
            item["score"] = int(round(conf * 100))
            out.append(item)
            continue

        conf, score_pct = score_box(item, active_preset=active_preset, rating_cfg=rating_cfg, profile=profile)
        item["confidence"] = conf
        item["score"] = score_pct
        item["rating_source"] = "ai" if item.get("source") == "ai" else (
            "adaptive" if (profile and profile.get("samples", 0) > 0) else "heuristic"
        )

        # Always retain desktop windows and explicit AI detections even at aggressive thresholds
        b_type = item.get("type")
        if b_type in ("window", "floating_window", "ai") or item.get("is_client") or conf >= min_conf:
            out.append(item)

    return out


def main():
    parser = argparse.ArgumentParser(description="HyprSmartShot Rating System CLI")
    parser.add_argument("--feedback", action="store_true", help="Record user like/dislike for adaptive weights")
    parser.add_argument("--type", default="detected", help="Box type")
    parser.add_argument("--w", type=int, default=100, help="Box width")
    parser.add_argument("--h", type=int, default=40, help="Box height")
    parser.add_argument("--preset", default="default", help="Active preset name")
    parser.add_argument("--dislike", action="store_true", help="Record negative feedback instead of positive")
    parser.add_argument("--profile", default=None, help="Explicit rating profile path")
    args = parser.parse_args()

    if args.feedback:
        profile = record_feedback(
            args.type,
            args.w,
            args.h,
            liked=not args.dislike,
            preset_key=args.preset,
            profile_path=args.profile,
        )
        print(json.dumps({"ok": True, "samples": profile.get("samples", 0)}))
        return 0

    print(json.dumps(load_rating_profile(args.profile), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
