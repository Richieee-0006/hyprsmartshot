#!/usr/bin/env python3
"""
Modular AI Vision provider client for HyprSmartShot.
Supports OpenAI-compatible local/cloud Vision endpoints (llama-swap, Ollama,
llama.cpp, OpenRouter, OpenAI) and Google Gemini REST Vision API.
Disabled by default for zero-dependency publishable setups.
"""

import argparse
import base64
import json
import os
import re
import sys

import cv2
import requests

_VISION_DIR = os.path.dirname(os.path.abspath(__file__))
if _VISION_DIR not in sys.path:
    sys.path.insert(0, _VISION_DIR)

from config_loader import load_config


def _encode_image_jpeg(image_path, roi=None, max_dim=1280):
    """Loads screenshot (optionally cropped to roi), resizes within max_dim, returns (b64, crop_w, crop_h, offset_x, offset_y)."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Failed to read image: {image_path}")

    orig_h, orig_w = img.shape[:2]
    off_x, off_y = 0, 0

    if roi and len(roi) == 4:
        rx, ry, rw, rh = [int(v) for v in roi]
        x1 = max(0, min(orig_w - 1, rx))
        y1 = max(0, min(orig_h - 1, ry))
        x2 = max(x1 + 1, min(orig_w, rx + rw))
        y2 = max(y1 + 1, min(orig_h, ry + rh))
        img = img[y1:y2, x1:x2]
        off_x, off_y = x1, y1

    crop_h, crop_w = img.shape[:2]
    longest = max(crop_w, crop_h)
    if max_dim and longest > max_dim:
        scale = float(max_dim) / longest
        send_img = cv2.resize(img, (max(1, int(round(crop_w * scale))), max(1, int(round(crop_h * scale)))), interpolation=cv2.INTER_AREA)
    else:
        send_img = img

    ok, buf = cv2.imencode(".jpg", send_img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return base64.b64encode(buf.tobytes()).decode("ascii"), crop_w, crop_h, off_x, off_y


def _resolve_api_key(prov_cfg):
    direct = str(prov_cfg.get("apiKey", "") or "").strip()
    if direct:
        return direct
    env_name = str(prov_cfg.get("apiKeyEnv", "") or "").strip()
    if env_name:
        return os.environ.get(env_name, "").strip()
    return ""


def _resolve_openai_model(base_url, prov_cfg, timeout_s):
    model = str(prov_cfg.get("model", "") or "").strip()
    if model:
        return model
    try:
        headers = {}
        key = _resolve_api_key(prov_cfg)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        resp = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=min(4.0, timeout_s))
        if resp.ok:
            data = resp.json().get("data", [])
            if data and isinstance(data[0], dict) and data[0].get("id"):
                return str(data[0]["id"])
    except Exception:
        pass
    return ""


def _call_openai_compatible(b64_img, prompt_text, prov_cfg, timeout_s=15.0):
    base_url = str(prov_cfg.get("baseUrl", "http://127.0.0.1:8080/v1")).rstrip("/")
    model = _resolve_openai_model(base_url, prov_cfg, timeout_s)
    if not model:
        raise RuntimeError("No AI model configured (set ai.providers.openai_compatible.model)")

    headers = {"Content-Type": "application/json"}
    api_key = _resolve_api_key(prov_cfg)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 1200,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                ],
            }
        ],
    }
    resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return ""
    msg = choices[0].get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):
        return "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return str(content or "")


def _call_gemini(b64_img, prompt_text, prov_cfg, timeout_s=15.0):
    api_key = _resolve_api_key(prov_cfg)
    if not api_key:
        raise RuntimeError("Missing Gemini API key (set GEMINI_API_KEY or ai.providers.gemini.apiKey)")

    base_url = str(prov_cfg.get("baseUrl", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/")
    model = str(prov_cfg.get("model", "gemini-2.5-flash") or "gemini-2.5-flash").strip()
    url = f"{base_url}/models/{model}:generateContent"

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}},
            ]
        }],
        "generationConfig": {"temperature": 0.1},
    }
    resp = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    cands = data.get("candidates", [])
    if not cands:
        return ""
    parts = cands[0].get("content", {}).get("parts", [])
    return "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict) and "text" in p)


def extract_ai_boxes(raw_text, crop_w, crop_h, offset_x=0, offset_y=0):
    """Parses normalized [ymin, xmin, ymax, xmax] JSON boxes from VLM output into pixel boxes."""
    cleaned = re.sub(r"<think>.*?</think>", "", str(raw_text or ""), flags=re.DOTALL).strip()
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if not match:
        return []

    try:
        items = json.loads(match.group(0))
    except Exception:
        return []
    if not isinstance(items, list):
        return []

    valid_types = {"panel", "button", "input", "slot", "text_block", "text", "detected", "ai"}
    boxes = []
    for item in items:
        if not isinstance(item, dict):
            continue
        coords = item.get("bbox_2d") or item.get("box_2d") or item.get("bbox")
        if not (isinstance(coords, list) and len(coords) == 4):
            continue
        try:
            y1n, x1n, y2n, x2n = [float(v) for v in coords]
        except (TypeError, ValueError):
            continue

        # Normalize either 0..1 floats or 0..1000 ints
        scale_x = crop_w if max(abs(x1n), abs(x2n)) <= 1.0 else (crop_w / 1000.0)
        scale_y = crop_h if max(abs(y1n), abs(y2n)) <= 1.0 else (crop_h / 1000.0)

        px1 = int(round(min(x1n, x2n) * scale_x)) + offset_x
        py1 = int(round(min(y1n, y2n) * scale_y)) + offset_y
        px2 = int(round(max(x1n, x2n) * scale_x)) + offset_x
        py2 = int(round(max(y1n, y2n) * scale_y)) + offset_y

        bw = max(0, px2 - px1)
        bh = max(0, py2 - py1)
        if bw < 8 or bh < 8:
            continue

        raw_type = str(item.get("type", "ai")).strip().lower()
        b_type = raw_type if raw_type in valid_types else "ai"
        try:
            conf = float(item.get("confidence", 0.88))
        except (TypeError, ValueError):
            conf = 0.88
        conf = round(max(0.05, min(0.99, conf)), 3)

        boxes.append({
            "x": px1,
            "y": py1,
            "w": bw,
            "h": bh,
            "area": bw * bh,
            "extent": 1.0,
            "contrast": 50.0,
            "type": b_type,
            "label": str(item.get("label", "") or "").strip()[:48],
            "source": "ai",
            "ai_confidence": conf,
            "confidence": conf,
            "score": int(round(conf * 100)),
        })

    return boxes


def _dispatch_vlm(b64_img, prompt_text, config):
    ai_cfg = config.get("ai", {})
    provider = str(ai_cfg.get("provider", "openai_compatible")).strip().lower()
    providers = ai_cfg.get("providers", {})
    prov_cfg = providers.get(provider, {}) if isinstance(providers, dict) else {}
    timeout_s = max(2.0, float(ai_cfg.get("timeoutMs", 15000) or 15000) / 1000.0)

    if provider == "gemini":
        return _call_gemini(b64_img, prompt_text, prov_cfg, timeout_s=timeout_s)
    return _call_openai_compatible(b64_img, prompt_text, prov_cfg, timeout_s=timeout_s)


def detect_ai_boxes(image_path, config=None, custom_prompt=None, roi=None):
    """Runs VLM bounding-box detection on image_path using the configured provider."""
    cfg = config if isinstance(config, dict) else load_config()
    ai_cfg = cfg.get("ai", {})
    max_dim = int(ai_cfg.get("maxImageDim", 1280) or 1280)
    b64_img, crop_w, crop_h, off_x, off_y = _encode_image_jpeg(image_path, roi=roi, max_dim=max_dim)

    prompt = str(custom_prompt or "").strip()
    base_prompt = str(ai_cfg.get("prompt", "")).strip()
    if prompt:
        full_prompt = (
            f"Find regions matching: '{prompt}'. Return strict JSON array of "
            "[{\"label\":\"...\",\"type\":\"panel|button|input|slot|text_block|text|detected\","
            "\"bbox_2d\":[ymin,xmin,ymax,xmax],\"confidence\":0.9}] with 0..1000 coords."
        )
    else:
        full_prompt = base_prompt

    raw_text = _dispatch_vlm(b64_img, full_prompt, cfg)
    boxes = extract_ai_boxes(raw_text, crop_w, crop_h, offset_x=off_x, offset_y=off_y)
    return {"ok": True, "count": len(boxes), "boxes": boxes}


def run_ai_vision_action(image_path, action="ocr", config=None):
    """Runs AI Vision OCR or concise description on a cropped selection."""
    cfg = config if isinstance(config, dict) else load_config()
    ai_cfg = cfg.get("ai", {})
    max_dim = int(ai_cfg.get("maxImageDim", 1280) or 1280)
    b64_img, _, _, _, _ = _encode_image_jpeg(image_path, max_dim=max_dim)

    if action == "describe":
        prompt = "Concisely describe what is shown in this UI screenshot in 1-3 clear sentences."
    else:
        prompt = "Extract all readable text verbatim, preserving line breaks and table layout. Output text only."

    raw_text = _dispatch_vlm(b64_img, prompt, cfg)
    clean = re.sub(r"<think>.*?</think>", "", str(raw_text or ""), flags=re.DOTALL).strip()
    return clean


def check_ai_status(config=None):
    """Checks AI configuration validity and reachability without running inference."""
    cfg = config if isinstance(config, dict) else load_config()
    ai_cfg = cfg.get("ai", {})
    provider = str(ai_cfg.get("provider", "openai_compatible")).strip().lower()
    prov_cfg = (ai_cfg.get("providers", {}) or {}).get(provider, {})
    enabled = bool(ai_cfg.get("enabled", False))

    info = {
        "enabled": enabled,
        "trigger": ai_cfg.get("trigger", "manual"),
        "provider": provider,
        "reachable": False,
        "detail": "",
    }
    if provider == "gemini":
        has_key = bool(_resolve_api_key(prov_cfg))
        info["reachable"] = has_key
        info["detail"] = f"model={prov_cfg.get('model', 'gemini-2.5-flash')} key={'set' if has_key else 'missing'}"
        return info

    base_url = str(prov_cfg.get("baseUrl", "http://127.0.0.1:8080/v1")).rstrip("/")
    try:
        resp = requests.get(f"{base_url}/models", timeout=1.5)
        info["reachable"] = resp.ok
        if resp.ok:
            models = [m.get("id") for m in resp.json().get("data", []) if isinstance(m, dict)]
            info["detail"] = f"url={base_url} models={models[:3]}"
        else:
            info["detail"] = f"url={base_url} http={resp.status_code}"
    except Exception as exc:
        info["detail"] = f"url={base_url} offline ({exc.__class__.__name__})"
    return info


def main():
    parser = argparse.ArgumentParser(description="HyprSmartShot AI Vision CLI")
    parser.add_argument("--detect", metavar="IMAGE", help="Run AI bbox detection on image")
    parser.add_argument("--action", choices=("ocr", "describe"), help="Run AI OCR/describe on cropped image")
    parser.add_argument("target_image", nargs="?", help="Image path for --action")
    parser.add_argument("--prompt", default="", help="Optional target description")
    parser.add_argument("--roi", default="", help="Optional x,y,w,h crop ROI")
    parser.add_argument("--out", default="", help="Write JSON result atomically to path")
    parser.add_argument("--config", default=None, help="Explicit config JSON path")
    parser.add_argument("--check", action="store_true", help="Inspect provider status")
    args = parser.parse_args()

    cfg = load_config(args.config)
    try:
        if args.check:
            print(json.dumps(check_ai_status(cfg)))
            return 0
        if args.detect:
            roi = [int(v) for v in args.roi.split(",")] if args.roi and len(args.roi.split(",")) == 4 else None
            res = detect_ai_boxes(args.detect, config=cfg, custom_prompt=args.prompt, roi=roi)
            payload = json.dumps(res)
            if args.out:
                tmp = f"{args.out}.tmp.{os.getpid()}"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp, args.out)
            else:
                print(payload)
            return 0
        if args.action and args.target_image:
            text = run_ai_vision_action(args.target_image, action=args.action, config=cfg)
            print(text)
            return 0 if text else 1
    except Exception as exc:
        err = json.dumps({"ok": False, "error": str(exc), "boxes": []})
        if args.out:
            tmp = f"{args.out}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(err)
            os.replace(tmp, args.out)
        print(err, file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
