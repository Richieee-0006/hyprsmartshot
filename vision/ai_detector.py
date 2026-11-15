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
import shutil
import subprocess
import sys
import time

import cv2
import requests

_VISION_DIR = os.path.dirname(os.path.abspath(__file__))
if _VISION_DIR not in sys.path:
    sys.path.insert(0, _VISION_DIR)

from config_loader import load_config

DEFAULT_AI_PROMPT = (
    "Detect up to 12 key UI regions (windows, panels, sidebar, dialogs, buttons, inputs, dock, text blocks). "
    "Coordinates are normalized 0..1000 where x1,x2 are horizontal (left=0, right=1000) and y1,y2 are vertical (top=0, bottom=1000). "
    "Return strict JSON array: "
    "[{\"label\":\"...\",\"type\":\"panel|button|input|slot|text_block\","
    "\"x1\":0,\"y1\":0,\"x2\":500,\"y2\":900,\"confidence\":0.9}]"
)

_NON_VISION_MODELS = {
    "qwen3.6-35b-mtp",
    "coder-max-mtp",
    "mtp",
    "qwen3.6-mtp",
    "opus-mtp",
    "qwen2.5-7b-fast",
    "coder-pro",
}

_COPILOT_VISION_ALLOWLIST = (
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4o-2024-05-13",
    "gpt-4-o-preview",
)

_PROVIDER_DEFAULTS = {
    "copilot": {
        "baseUrl": "http://127.0.0.1:4141/v1",
        "apiKeyEnv": "GITHUB_TOKEN",
        "model": "gpt-4.1",
    },
    "local_llm": {
        "baseUrl": "http://127.0.0.1:8080/v1",
        "apiKeyEnv": "OPENAI_API_KEY",
        "model": "qwen3.6-35b-vision",
    },
    "ollama": {
        "baseUrl": "http://127.0.0.1:11434/v1",
        "apiKeyEnv": "",
        "model": "qwen2.5vl:7b",
    },
    "ovhcloud": {
        "baseUrl": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        "apiKeyEnv": "OVH_API_KEY",
        "model": "Qwen2.5-VL-72B-Instruct",
    },
    "kilo": {
        "baseUrl": "https://api.kilo.ai/api/gateway",
        "apiKeyEnv": "KILO_API_KEY",
        "model": "nvidia/nemotron-3.5-super-vl:free",
    },
    "gemini": {
        "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
        "apiKeyEnv": "GEMINI_API_KEY",
        "model": "gemini-3.8-flash",
    },
    "openrouter": {
        "baseUrl": "https://openrouter.ai/api/v1",
        "apiKeyEnv": "OPENROUTER_API_KEY",
        "model": "google/gemma-4-31b-it:free",
    },
    "groq": {
        "baseUrl": "https://api.groq.com/openai/v1",
        "apiKeyEnv": "GROQ_API_KEY",
        "model": "qwen/qwen3.8-27b",
    },
    "mistral": {
        "baseUrl": "https://api.mistral.ai/v1",
        "apiKeyEnv": "MISTRAL_API_KEY",
        "model": "mistral-medium-3-5",
    },
    "openai_compatible": {
        "baseUrl": "http://127.0.0.1:8080/v1",
        "apiKeyEnv": "OPENAI_API_KEY",
        "model": "qwen3.6-35b-vision",
    },
}


def resolve_provider_config(config, provider_override=None):
    """Returns (provider_name, merged_provider_dict) with defaults filled in."""
    ai_cfg = (config or {}).get("ai", {}) if isinstance(config, dict) else {}
    provider = str(provider_override or ai_cfg.get("provider", "openai_compatible") or "openai_compatible").strip().lower()
    if provider not in _PROVIDER_DEFAULTS:
        provider = "openai_compatible"
    defaults = dict(_PROVIDER_DEFAULTS[provider])
    providers = ai_cfg.get("providers", {})
    user_prov = dict(providers.get(provider, {})) if isinstance(providers, dict) and isinstance(providers.get(provider), dict) else {}
    merged = {
        "baseUrl": str(user_prov.get("baseUrl") or defaults["baseUrl"]).strip(),
        "apiKey": str(user_prov.get("apiKey") or "").strip(),
        "apiKeyEnv": str(user_prov.get("apiKeyEnv") if "apiKeyEnv" in user_prov else defaults["apiKeyEnv"]).strip(),
        "model": str(user_prov.get("model") or defaults["model"]).strip(),
    }
    return provider, merged


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
    is_copilot = ":4141" in base_url
    is_llama_swap = ":8080" in base_url

    if is_copilot and model in ("", "gpt-4o", "gpt-4o-mini") or (is_copilot and model in _NON_VISION_MODELS):
        return "gpt-4.1"
    if is_llama_swap and model in _NON_VISION_MODELS:
        return "qwen3.6-35b-vision"
    if model and model not in _NON_VISION_MODELS:
        return model

    try:
        headers = {}
        key = _resolve_api_key(prov_cfg)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        resp = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=min(4.0, timeout_s))
        if resp.ok:
            data = resp.json().get("data", [])
            ids = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
            for preferred in ("gpt-4.1", "qwen3.6-35b-vision", "qwen3.8-27b-dense", "gemini-2.5-flash"):
                if preferred in ids:
                    return preferred
            for mid in ids:
                low = mid.lower()
                if mid not in _NON_VISION_MODELS and any(k in low for k in ("vision", "vl", "4.1", "pixtral", "llava", "minicpm")):
                    return mid
            for mid in ids:
                if mid not in _NON_VISION_MODELS:
                    return mid
            if ids:
                return ids[0]
    except Exception:
        pass
    if is_copilot:
        return "gpt-4.1"
    if is_llama_swap:
        return "qwen3.6-35b-vision"
    return ""


def _try_start_copilot_proxy():
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    token_file = os.path.expanduser("~/.local/share/copilot-api/github_token")
    if not (shutil.which("copilot-api") and os.path.isfile(token_file)):
        return False
    try:
        r = requests.get("http://127.0.0.1:4141/v1/models", timeout=1.0)
        if r.ok:
            return True
    except Exception:
        pass
    try:
        log_path = os.path.expanduser("~/.local/state/copilot-api.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            subprocess.Popen(["copilot-api", "start"], stdout=lf, stderr=lf, stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(16):
            time.sleep(0.3)
            try:
                if requests.get("http://127.0.0.1:4141/v1/models", timeout=1.0).ok:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _try_start_llama_swap_proxy():
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    cfg_file = os.path.expanduser("~/.config/llama-swap/config.yaml")
    if not (shutil.which("llama-swap") and os.path.isfile(cfg_file)):
        return False
    try:
        r = requests.get("http://127.0.0.1:8080/v1/models", timeout=1.0)
        if r.ok:
            return True
    except Exception:
        pass
    try:
        log_path = os.path.expanduser("~/.local/state/llama-swap.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            subprocess.Popen(
                ["llama-swap", "--config", cfg_file, "--listen", "127.0.0.1:8080"],
                stdout=lf, stderr=lf, stdin=subprocess.DEVNULL, start_new_session=True,
            )
        for _ in range(10):
            time.sleep(0.25)
            try:
                if requests.get("http://127.0.0.1:8080/v1/models", timeout=1.0).ok:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _call_openai_compatible(b64_img, prompt_text, prov_cfg, timeout_s=35.0):
    base_url = str(prov_cfg.get("baseUrl", "http://127.0.0.1:8080/v1")).rstrip("/")
    model = _resolve_openai_model(base_url, prov_cfg, timeout_s)
    if not model:
        raise RuntimeError("No AI model configured (set ai.providers.<provider>.model)")

    def _build_and_post(target_url, target_model):
        headers = {"Content-Type": "application/json"}
        if ":4141" in target_url:
            headers["Copilot-Vision-Request"] = "true"
        api_key = _resolve_api_key(prov_cfg)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif "kilo.ai" in target_url:
            headers["Authorization"] = "Bearer anonymous"
        img_obj = {"url": f"data:image/jpeg;base64,{b64_img}"}
        if ":4141" in target_url:
            img_obj["detail"] = "low"
        payload = {
            "model": target_model,
            "temperature": 0.1,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": img_obj},
                    ],
                }
            ],
        }
        resp = requests.post(f"{target_url}/chat/completions", headers=headers, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        return resp.json()

    try:
        data = _build_and_post(base_url, model)
    except requests.ConnectionError:
        if ("127.0.0.1:4141" in base_url or "localhost:4141" in base_url) and _try_start_copilot_proxy():
            data = _build_and_post(base_url, model if model in _COPILOT_VISION_ALLOWLIST else "gpt-4.1")
        elif ("127.0.0.1:8080" in base_url or "localhost:8080" in base_url) and _try_start_llama_swap_proxy():
            data = _build_and_post(base_url, model if model not in _NON_VISION_MODELS else "qwen3.6-35b-vision")
        elif ("127.0.0.1:8080" in base_url or "localhost:8080" in base_url) and _try_start_copilot_proxy():
            data = _build_and_post("http://127.0.0.1:4141/v1", "gpt-4.1")
        elif ("127.0.0.1:4141" in base_url or "localhost:4141" in base_url) and _try_start_llama_swap_proxy():
            data = _build_and_post("http://127.0.0.1:8080/v1", "qwen3.6-35b-vision")
        else:
            raise
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
    model = str(prov_cfg.get("model", "gemini-3.8-flash") or "gemini-3.8-flash").strip()
    if base_url.endswith("/openai"):
        return _call_openai_compatible(b64_img, prompt_text, prov_cfg, timeout_s=timeout_s)
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
    """Parses normalized x1/y1/x2/y2 or [ymin, xmin, ymax, xmax] JSON boxes from VLM output into pixel boxes."""
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
    type_aliases = {
        "sidebar": "panel",
        "dialog": "panel",
        "toolbar": "panel",
        "header": "panel",
        "dock": "panel",
        "card": "panel",
        "window": "panel",
        "search": "input",
    }
    boxes = []
    for item in items:
        if not isinstance(item, dict):
            continue

        if all(k in item for k in ("x1", "y1", "x2", "y2")):
            try:
                x1n, y1n, x2n, y2n = float(item["x1"]), float(item["y1"]), float(item["x2"]), float(item["y2"])
            except (TypeError, ValueError):
                continue
        elif isinstance(item.get("box"), list) and len(item["box"]) == 4:
            try:
                x1n, y1n, x2n, y2n = [float(v) for v in item["box"]]
            except (TypeError, ValueError):
                continue
        else:
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

        px1 = max(0, min(crop_w, int(round(min(x1n, x2n) * scale_x)))) + offset_x
        py1 = max(0, min(crop_h, int(round(min(y1n, y2n) * scale_y)))) + offset_y
        px2 = max(0, min(crop_w, int(round(max(x1n, x2n) * scale_x)))) + offset_x
        py2 = max(0, min(crop_h, int(round(max(y1n, y2n) * scale_y)))) + offset_y

        bw = max(0, px2 - px1)
        bh = max(0, py2 - py1)
        if bw < 8 or bh < 8:
            continue

        raw_type = str(item.get("type", "ai")).strip().lower()
        raw_type = type_aliases.get(raw_type, raw_type)
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


def _snap_ai_boxes_to_cv(ai_boxes, cv_boxes_path="/tmp/hyprsmartshot_boxes.json", tol=24):
    """Refines coarse VLM box edges to pixel-exact OpenCV boundaries when closely aligned."""
    if not ai_boxes or not cv_boxes_path or not os.path.isfile(cv_boxes_path):
        return ai_boxes
    try:
        with open(cv_boxes_path, "r", encoding="utf-8") as f:
            cv_data = json.load(f)
        cv_boxes = cv_data.get("boxes", []) if isinstance(cv_data, dict) else []
    except Exception:
        return ai_boxes
    if not cv_boxes:
        return ai_boxes

    for ab in ai_boxes:
        ax1, ay1 = ab["x"], ab["y"]
        ax2, ay2 = ax1 + ab["w"], ay1 + ab["h"]
        best_cv = None
        best_dist = tol * 4 + 1
        for cb in cv_boxes:
            cx1, cy1 = int(cb.get("x", 0)), int(cb.get("y", 0))
            cw, ch = int(cb.get("w", 0)), int(cb.get("h", 0))
            cx2, cy2 = cx1 + cw, cy1 + ch
            dx1, dy1 = abs(ax1 - cx1), abs(ay1 - cy1)
            dx2, dy2 = abs(ax2 - cx2), abs(ay2 - cy2)
            if dx1 <= tol and dy1 <= tol and dx2 <= tol and dy2 <= tol:
                dist = dx1 + dy1 + dx2 + dy2
                if dist < best_dist:
                    best_dist = dist
                    best_cv = (cx1, cy1, cw, ch)
        if best_cv:
            ab["x"], ab["y"], ab["w"], ab["h"] = best_cv
            ab["area"] = best_cv[2] * best_cv[3]
    return ai_boxes


def _dispatch_vlm(b64_img, prompt_text, config):
    ai_cfg = config.get("ai", {}) if isinstance(config, dict) else {}
    provider, prov_cfg = resolve_provider_config(config)
    timeout_s = max(2.0, float(ai_cfg.get("timeoutMs", 35000) or 35000) / 1000.0)

    if provider == "gemini":
        return _call_gemini(b64_img, prompt_text, prov_cfg, timeout_s=timeout_s)
    return _call_openai_compatible(b64_img, prompt_text, prov_cfg, timeout_s=timeout_s)


def detect_ai_boxes(image_path, config=None, custom_prompt=None, roi=None):
    """Runs VLM bounding-box detection on image_path using the configured provider."""
    cfg = config if isinstance(config, dict) else load_config()
    ai_cfg = cfg.get("ai", {})
    max_dim = int(ai_cfg.get("maxImageDim", 960) or 960)
    b64_img, crop_w, crop_h, off_x, off_y = _encode_image_jpeg(image_path, roi=roi, max_dim=max_dim)

    prompt = str(custom_prompt or "").strip()
    base_prompt = str(ai_cfg.get("prompt", "")).strip()
    if not base_prompt or '"bbox_2d":[ymin,xmin,ymax,xmax]' in base_prompt:
        base_prompt = DEFAULT_AI_PROMPT
    if prompt:
        full_prompt = (
            f"Find regions matching: '{prompt}'. "
            "Coordinates are normalized 0..1000 where x1,x2 are horizontal and y1,y2 are vertical. "
            "Return strict JSON array: "
            "[{\"label\":\"...\",\"type\":\"panel|button|input|slot|text_block\","
            "\"x1\":0,\"y1\":0,\"x2\":500,\"y2\":900,\"confidence\":0.9}]"
        )
    else:
        full_prompt = base_prompt

    raw_text = _dispatch_vlm(b64_img, full_prompt, cfg)
    boxes = extract_ai_boxes(raw_text, crop_w, crop_h, offset_x=off_x, offset_y=off_y)
    if roi is None:
        boxes = _snap_ai_boxes_to_cv(boxes)
    return {"ok": True, "count": len(boxes), "boxes": boxes}


def run_ai_vision_action(image_path, action="ocr", config=None):
    """Runs AI Vision OCR or concise description on a cropped selection."""
    cfg = config if isinstance(config, dict) else load_config()
    ai_cfg = cfg.get("ai", {})
    max_dim = int(ai_cfg.get("maxImageDim", 960) or 960)
    b64_img, _, _, _, _ = _encode_image_jpeg(image_path, max_dim=max_dim)

    if action == "describe":
        prompt = "Concisely describe what is shown in this UI screenshot in 1-3 clear sentences."
    else:
        prompt = "Extract all readable text verbatim, preserving line breaks and table layout. Output text only."

    raw_text = _dispatch_vlm(b64_img, prompt, cfg)
    clean = re.sub(r"<think>.*?</think>", "", str(raw_text or ""), flags=re.DOTALL).strip()
    return clean


def _parse_llama_swap_vision_models():
    """Reads ~/.config/llama-swap/config.yaml and returns model keys that do not disable mmproj."""
    cfg_file = os.path.expanduser("~/.config/llama-swap/config.yaml")
    if not os.path.isfile(cfg_file):
        return []
    models = []
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            text = f.read()
        in_models = False
        cur_model = None
        cur_block = []
        for line in text.splitlines():
            if re.match(r"^models:\s*$", line):
                in_models = True
                continue
            if in_models and re.match(r"^[a-zA-Z0-9_-]+:\s*$", line):
                break
            if not in_models:
                continue
            m = re.match(r'^  ["\']?([a-zA-Z0-9_.-]+)["\']?:\s*(?:#.*)?$', line)
            if m:
                if cur_model and not re.search(r"--no-mmproj(?![-a-zA-Z])", "\n".join(cur_block)) and cur_model not in _NON_VISION_MODELS:
                    models.append(cur_model)
                cur_model = m.group(1)
                cur_block = []
            elif cur_model:
                cur_block.append(line)
        if cur_model and not re.search(r"--no-mmproj(?![-a-zA-Z])", "\n".join(cur_block)) and cur_model not in _NON_VISION_MODELS:
            models.append(cur_model)
    except Exception:
        pass
    return models


def _get_models_cache_path():
    cache_home = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache_home, "hyprsmartshot", "models_cache.json")


def _load_models_cache():
    path = _get_models_cache_path()
    if not os.path.isfile(path):
        return {"providers": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("providers"), dict):
            return data
    except Exception:
        pass
    return {"providers": {}}


def _save_models_cache(cache_data):
    path = _get_models_cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def _parse_free_llm_skill_models(provider):
    """Dynamically extracts multimodal models from local free-llm-apis skill reference tables if installed."""
    section_map = {
        "gemini": ("provider-apis.md", "## Google Gemini"),
        "mistral": ("provider-apis.md", "## Mistral AI"),
        "groq": ("inference-providers.md", "## Groq"),
        "openrouter": ("inference-providers.md", "## OpenRouter"),
        "ovhcloud": ("inference-providers.md", "## OVHcloud"),
        "kilo": ("inference-providers.md", "## Kilo Code"),
    }
    target = section_map.get(provider)
    if not target:
        return []
    fname, header = target
    ref_path = os.path.expanduser(f"~/.gemini/config/skills/free-llm-apis/references/{fname}")
    if not os.path.isfile(ref_path):
        return []
    found = []
    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        in_sec = False
        for line in lines:
            if line.startswith("## "):
                if line.startswith(header):
                    in_sec = True
                    continue
                elif in_sec:
                    break
            if not in_sec or not line.startswith("| `"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 3:
                mid = cols[0].strip("` ").strip()
                modality = cols[2].lower()
                if mid and any(k in modality for k in ("image", "vision", "multimodal")):
                    found.append(mid)
    except Exception:
        pass
    return found


def _fetch_live_provider_models(provider, prov_cfg):
    """Queries live provider /models API and returns discovered vision-capable model IDs."""
    base_url = prov_cfg["baseUrl"].rstrip("/")
    discovered = []
    key = _resolve_api_key(prov_cfg)

    if provider == "gemini" and not base_url.endswith("/openai"):
        if key:
            try:
                resp = requests.get(f"{base_url}/models", params={"key": key}, timeout=3.5)
                if resp.ok:
                    for item in resp.json().get("models", []):
                        if not isinstance(item, dict):
                            continue
                        methods = item.get("supportedGenerationMethods") or []
                        name = str(item.get("name", "")).replace("models/", "").strip()
                        low = name.lower()
                        if (
                            name
                            and "generateContent" in methods
                            and not any(x in low for x in ("embedding", "aqa", "imagen", "veo", "tts", " attributed"))
                        ):
                            discovered.append(name)
            except Exception:
                pass
        for sm in _parse_free_llm_skill_models("gemini"):
            if sm not in discovered:
                discovered.append(sm)
        return discovered

    try:
        headers = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        elif "kilo.ai" in base_url:
            headers["Authorization"] = "Bearer anonymous"
        resp = requests.get(f"{base_url}/models", headers=headers, timeout=3.5)
        if resp.ok:
            data = resp.json().get("data", [])
            if ":4141" in base_url or provider == "copilot":
                ids = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
                allow = [m for m in ids if m in _COPILOT_VISION_ALLOWLIST]
                other = [
                    m for m in ids
                    if m not in allow
                    and m not in _NON_VISION_MODELS
                    and not m.startswith(("text-embedding", "copilot-search"))
                ]
                discovered = allow + other
            elif ":8080" in base_url or provider == "local_llm":
                ids = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
                yaml_vision = _parse_llama_swap_vision_models()
                if yaml_vision:
                    discovered = [m for m in ids if m in yaml_vision]
                    for ym in yaml_vision:
                        if ym not in discovered:
                            discovered.append(ym)
                else:
                    discovered = [m for m in ids if m not in _NON_VISION_MODELS]
            elif "openrouter.ai" in base_url or "kilo.ai" in base_url or provider in ("openrouter", "kilo"):
                free_vis = []
                paid_vis = []
                for m in data:
                    if not isinstance(m, dict) or not m.get("id"):
                        continue
                    mid = str(m["id"])
                    arch = m.get("architecture") or {}
                    in_mod = arch.get("input_modalities") or []
                    out_mod = arch.get("output_modalities") or []
                    mod_str = str(arch.get("modality") or "").lower()
                    has_image = ("image" in in_mod) or ("image" in mod_str)
                    has_text_out = (not out_mod) or ("text" in out_mod)
                    if not (has_image and has_text_out):
                        continue
                    if any(x in mid.lower() for x in ("lyria", "whisper", "tts", "embedding")):
                        continue
                    pricing = m.get("pricing") or {}
                    is_free = (
                        m.get("isFree") is True
                        or str(pricing.get("prompt", "")) == "0"
                        or mid.endswith(":free")
                    )
                    if is_free:
                        free_vis.append(mid)
                    else:
                        paid_vis.append(mid)
                discovered = free_vis + paid_vis
            elif "ovh.net" in base_url or provider == "ovhcloud":
                ids = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
                non_vis_prefixes = ("whisper", "nvr-tts", "bge-", "stable-diffusion", "gpt-oss", "Meta-Llama-3_3")
                discovered = [
                    m for m in ids
                    if not m.startswith(non_vis_prefixes)
                    and "Embedding" not in m
                    and "Guard" not in m
                ]
            else:
                ids = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
                discovered = [
                    m for m in ids
                    if m not in _NON_VISION_MODELS
                    and not m.startswith(("text-embedding", "whisper", "tts", "dall-e"))
                ]
    except Exception:
        if ":8080" in base_url or provider == "local_llm":
            discovered = _parse_llama_swap_vision_models()

    if not discovered:
        discovered = _parse_free_llm_skill_models(provider)

    return discovered


def list_provider_models(config=None, provider_override=None, search_query="", force_refresh=False):
    """Returns cached or live-discovered vision models for the specified provider, optionally filtered by search_query."""
    cfg = config if isinstance(config, dict) else load_config()
    provider, prov_cfg = resolve_provider_config(cfg, provider_override=provider_override)
    base_url = prov_cfg["baseUrl"].rstrip("/")
    is_local = ("127.0.0.1" in base_url) or ("localhost" in base_url)
    ttl = 300 if is_local else 86400

    cache = _load_models_cache()
    prov_entry = cache.get("providers", {}).get(provider, {})
    now = int(time.time())
    cached_models = prov_entry.get("models", []) if isinstance(prov_entry, dict) else []
    cached_url = prov_entry.get("baseUrl", "") if isinstance(prov_entry, dict) else ""
    cached_at = int(prov_entry.get("updatedAt", 0) or 0) if isinstance(prov_entry, dict) else 0

    from_cache = False
    if (
        not force_refresh
        and cached_models
        and cached_url == base_url
        and (now - cached_at) < ttl
    ):
        models = list(cached_models)
        from_cache = True
    else:
        live = _fetch_live_provider_models(provider, prov_cfg)
        models = live if live else list(cached_models)
        if models:
            cache.setdefault("providers", {})[provider] = {
                "baseUrl": base_url,
                "updatedAt": now,
                "models": models[:120],
            }
            _save_models_cache(cache)

    active_model = prov_cfg["model"]
    if active_model and active_model not in models:
        models.insert(0, active_model)

    q = str(search_query or "").strip().lower()
    if q:
        tokens = [t for t in q.split() if t]
        filtered = [m for m in models if all(tok in m.lower() for tok in tokens)]
    else:
        filtered = models

    return {
        "ok": True,
        "provider": provider,
        "baseUrl": base_url,
        "activeModel": active_model,
        "cached": from_cache,
        "totalCached": len(models),
        "models": filtered[:24],
    }


def check_ai_status(config=None):
    """Checks AI configuration validity and reachability without running inference."""
    cfg = config if isinstance(config, dict) else load_config()
    ai_cfg = cfg.get("ai", {})
    provider, prov_cfg = resolve_provider_config(cfg)
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
    eff_model = _resolve_openai_model(base_url, prov_cfg, 1.5)
    try:
        headers = {}
        key = _resolve_api_key(prov_cfg)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        resp = requests.get(f"{base_url}/models", headers=headers, timeout=1.5)
        info["reachable"] = resp.ok
        if resp.ok:
            info["detail"] = f"url={base_url} model={eff_model}"
            return info
        info["detail"] = f"url={base_url} http={resp.status_code}"
    except Exception as exc:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            if ("127.0.0.1:8080" in base_url or provider == "local_llm") and os.path.isfile(os.path.expanduser("~/.config/llama-swap/config.yaml")) and shutil.which("llama-swap"):
                info["reachable"] = True
                info["detail"] = f"url={base_url} model={eff_model or 'qwen3.6-35b-vision'} (llama-swap auto-start ready)"
                return info
            if ("127.0.0.1:4141" in base_url or provider == "copilot") and os.path.isfile(os.path.expanduser("~/.local/share/copilot-api/github_token")) and shutil.which("copilot-api"):
                info["reachable"] = True
                info["detail"] = "url=http://127.0.0.1:4141/v1 model=gpt-4.1 (copilot auto-start ready)"
                return info
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
    parser.add_argument("--list-models", action="store_true", help="List available vision models for provider")
    parser.add_argument("--refresh-all-models", action="store_true", help="Refresh cached models for all providers")
    parser.add_argument("--provider", default=None, help="Optional provider override for --list-models / --check")
    parser.add_argument("--search", default="", help="Optional search query for --list-models")
    parser.add_argument("--refresh", action="store_true", help="Force live refresh of model cache")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.provider and isinstance(cfg.get("ai"), dict):
        cfg["ai"]["provider"] = args.provider
    try:
        if args.refresh_all_models:
            summary = {}
            for p in _PROVIDER_DEFAULTS:
                res = list_provider_models(cfg, provider_override=p, force_refresh=True)
                summary[p] = len(res.get("models", []))
            print(json.dumps({"ok": True, "cachePath": _get_models_cache_path(), "counts": summary}))
            return 0
        if args.list_models:
            print(json.dumps(list_provider_models(cfg, provider_override=args.provider, search_query=args.search, force_refresh=args.refresh)))
            return 0
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
