#!/usr/bin/env python3
"""
HyprSmartShot - High Performance UI & Game Interface Detector
Analyzes screenshots to detect UI panels, windows, inventory grids, slots, dialogue boxes,
and fantasy game ornate frames. Outputs structured hierarchical JSON for Quickshell QML overlay.
"""

import sys
import os
import json
import time
import cv2
import numpy as np

def compute_border_contrast(gray, x, y, w, h):
    """Measures edge contrast across the outer perimeter of a candidate bounding box."""
    h_img, w_img = gray.shape
    if x <= 1 or y <= 1 or x + w >= w_img - 2 or y + h >= h_img - 2:
        return 30.0  # Outer boundaries / screen panels are given full confidence
    
    top_out = gray[max(0, y-3):y, x:x+w].astype(np.float32)
    top_in = gray[y:min(h_img, y+3), x:x+w].astype(np.float32)
    diff_t = np.abs(np.mean(top_out) - np.mean(top_in)) if top_out.size and top_in.size else 0
    
    bot_in = gray[max(0, y+h-3):y+h, x:x+w].astype(np.float32)
    bot_out = gray[y+h:min(h_img, y+h+3), x:x+w].astype(np.float32)
    diff_b = np.abs(np.mean(bot_in) - np.mean(bot_out)) if bot_in.size and bot_out.size else 0
    
    left_out = gray[y:y+h, max(0, x-3):x].astype(np.float32)
    left_in = gray[y:y+h, x:min(w_img, x+3)].astype(np.float32)
    diff_l = np.abs(np.mean(left_out) - np.mean(left_in)) if left_out.size and left_in.size else 0
    
    right_in = gray[y:y+h, max(0, x+w-3):x+w].astype(np.float32)
    right_out = gray[y:y+h, x+w:min(w_img, x+w+3)].astype(np.float32)
    diff_r = np.abs(np.mean(right_in) - np.mean(right_out)) if right_in.size and right_out.size else 0
    
    return float((diff_t + diff_b + diff_l + diff_r) / 4.0)

def cluster_slots_and_grids(boxes):
    """
    Detects inventory slot patterns (e.g. Minecraft, WoW, Diablo, Terraria)
    and synthesizes aggregate bounding boxes for rows and entire inventory grids.
    Partitions adjacent slots into contiguous chains to support split hotbars/windows.
    """
    slots = [b for b in boxes if 18 <= b['w'] <= 140 and 18 <= b['h'] <= 140 and 0.70 <= (b['w'] / b['h']) <= 1.42]
    if len(slots) < 2:
        return []

    # Tag initial slots
    for s in slots:
        if s.get('type') == 'detected':
            s['type'] = 'slot'

    slots_sorted = sorted(slots, key=lambda s: (s['y'], s['x']))
    used = set()
    rows = []

    for i, s1 in enumerate(slots_sorted):
        if i in used:
            continue
        band = [s1]
        for j, s2 in enumerate(slots_sorted):
            if j == i or j in used:
                continue
            if abs(s1['y'] - s2['y']) <= max(6, s1['h'] * 0.20) and abs(s1['h'] - s2['h']) <= max(6, s1['h'] * 0.20):
                band.append(s2)

        band.sort(key=lambda s: s['x'])
        current_chain = [band[0]]
        for k in range(1, len(band)):
            prev = current_chain[-1]
            curr = band[k]
            gap = curr['x'] - (prev['x'] + prev['w'])
            avg_w = (prev['w'] + curr['w']) / 2.0
            if -4 <= gap <= max(16, avg_w * 0.55):
                current_chain.append(curr)
            else:
                if len(current_chain) >= 2:
                    rx = current_chain[0]['x']
                    ry = min(s['y'] for s in current_chain)
                    rw = (current_chain[-1]['x'] + current_chain[-1]['w']) - rx
                    rh = max(s['y'] + s['h'] for s in current_chain) - ry
                    rows.append({'x': rx, 'y': ry, 'w': rw, 'h': rh, 'area': rw * rh, 'extent': 0.96, 'type': 'grid_row', 'slots': list(current_chain)})
                    for s in current_chain:
                        used.add(slots_sorted.index(s))
                current_chain = [curr]
                
        if len(current_chain) >= 2:
            rx = current_chain[0]['x']
            ry = min(s['y'] for s in current_chain)
            rw = (current_chain[-1]['x'] + current_chain[-1]['w']) - rx
            rh = max(s['y'] + s['h'] for s in current_chain) - ry
            rows.append({'x': rx, 'y': ry, 'w': rw, 'h': rh, 'area': rw * rh, 'extent': 0.96, 'type': 'grid_row', 'slots': list(current_chain)})
            for s in current_chain:
                used.add(slots_sorted.index(s))

    # Cluster rows into stacked grids
    grids = []
    used_rows = set()
    rows_sorted = sorted(rows, key=lambda r: (r['x'], r['y']))
    for i, r1 in enumerate(rows_sorted):
        if i in used_rows:
            continue
        grid_rows = [r1]
        for j, r2 in enumerate(rows_sorted):
            if j == i or j in used_rows:
                continue
            prev_r = grid_rows[-1]
            if abs(prev_r['x'] - r2['x']) <= 12 and abs(prev_r['w'] - r2['w']) <= 16:
                v_gap = r2['y'] - (prev_r['y'] + prev_r['h'])
                if -6 <= v_gap <= max(16, prev_r['h'] * 0.55):
                    grid_rows.append(r2)
        if len(grid_rows) >= 2:
            for r in grid_rows:
                used_rows.add(rows_sorted.index(r))
            gx = min(r['x'] for r in grid_rows)
            gy = min(r['y'] for r in grid_rows)
            gw = max(r['x'] + r['w'] for r in grid_rows) - gx
            gh = max(r['y'] + r['h'] for r in grid_rows) - gy
            grids.append({'x': gx, 'y': gy, 'w': gw, 'h': gh, 'area': gw * gh, 'extent': 0.98, 'type': 'grid_container'})

    clean_rows = []
    for r in rows:
        clean_rows.append({'x': r['x'], 'y': r['y'], 'w': r['w'], 'h': r['h'], 'area': r['area'], 'extent': r['extent'], 'type': 'grid_row'})

    return clean_rows + grids

def is_duplicate(a, b, tol=5):
    """Checks whether box a and box b are virtually identical."""
    return (abs(a['x'] - b['x']) <= tol and
            abs(a['y'] - b['y']) <= tol and
            abs(a['w'] - b['w']) <= tol * 1.5 and
            abs(a['h'] - b['h']) <= tol * 1.5)

def detect_ui_elements(image_path, min_area=320, max_area_ratio=0.98):
    start_time = time.time()

    img = cv2.imread(image_path)
    if img is None:
        return {"error": f"Failed to load image: {image_path}", "boxes": []}

    orig_h, orig_w = img.shape[:2]
    total_area = orig_w * orig_h
    max_area = total_area * max_area_ratio

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. CLAHE enhancement (reveals low-contrast frames, dark fantasy filigree, dark mode borders)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    cl = clahe.apply(gray)

    # 2. Bilateral filter: smooths textured 3D backgrounds while keeping pixel-sharp UI borders
    filtered = cv2.bilateralFilter(cl, 5, 25, 25)

    # 3. Multi-threshold Canny edge detection
    edges_sharp = cv2.Canny(filtered, 30, 90)
    edges_dark = cv2.Canny(filtered, 14, 50)
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (4, 4))
    closed_edges = cv2.morphologyEx(cv2.bitwise_or(edges_sharp, edges_dark), cv2.MORPH_CLOSE, k_close)

    # 4. Large-scale morphological closing for dark/translucent panels (dialogue, chat, HUD)
    k_panel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
    closed_gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, k_panel)
    panel_grad = cv2.morphologyEx(closed_gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    _, panel_edges = cv2.threshold(panel_grad, 14, 255, cv2.THRESH_BINARY)

    combined = cv2.bitwise_or(closed_edges, panel_edges)

    # 5. Find contours using two-level hierarchy
    contours, _ = cv2.findContours(combined, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    raw_boxes = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 16 or h < 16:
            continue

        box_area = w * h
        if box_area < min_area or box_area > max_area:
            continue

        # Filter out extreme text slivers (single line of text inside dialogues)
        if (w / h > 10 or h / w > 10) and (h < 26 or w < 26):
            continue

        area = cv2.contourArea(cnt)
        extent = float(area) / box_area
        if extent < 0.58:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        # UI rectangles and rounded rectangles have 4-8 vertices
        if len(approx) > 8:
            continue

        contrast = compute_border_contrast(gray, x, y, w, h)
        if contrast < 12.0:
            continue

        # Classify basic type
        elem_type = "detected"
        if w >= 250 and h >= 160:
            elem_type = "panel"
        elif 18 <= w <= 140 and 18 <= h <= 140 and 0.72 <= (w / h) <= 1.38:
            elem_type = "slot"
        elif 30 <= w <= 220 and 18 <= h <= 60:
            elem_type = "button"

        raw_boxes.append({
            "x": int(x),
            "y": int(y),
            "w": int(w),
            "h": int(h),
            "area": int(box_area),
            "extent": round(extent, 2),
            "contrast": round(contrast, 1),
            "type": elem_type
        })

    # Suppress periodic mesh / background texture tiling (e.g. 10+ identical tiles with low contrast)
    size_bins = {}
    for b in raw_boxes:
        key = (b["w"] // 4, b["h"] // 4)
        size_bins[key] = size_bins.get(key, 0) + 1

    filtered_boxes = []
    for b in raw_boxes:
        key = (b["w"] // 4, b["h"] // 4)
        if size_bins[key] > 10 and b.get("contrast", 0) < 28.0:
            continue
        filtered_boxes.append(b)

    # Synthesize inventory rows and grid containers
    synthesized = cluster_slots_and_grids(filtered_boxes)
    filtered_boxes.extend(synthesized)

    # Deduplicate overlapping or near-identical boxes
    filtered_boxes.sort(key=lambda b: b["area"], reverse=True)
    deduped = []
    for b in filtered_boxes:
        dup = False
        for existing in deduped:
            if is_duplicate(b, existing, tol=5):
                dup = True
                # If new box has more specific semantic type, upgrade the existing box
                if b.get("type") in ("grid_container", "grid_row") and existing.get("type") not in ("grid_container", "grid_row"):
                    existing["type"] = b["type"]
                break
        if not dup:
            deduped.append(b)

    # Semantic hierarchy depth calculation
    boxes_asc = sorted(deduped, key=lambda b: b["area"])
    for i, box in enumerate(boxes_asc):
        box["id"] = i
        parents = [p for p in boxes_asc if p["area"] > box["area"] * 1.05 and
                   box["x"] >= p["x"] - 4 and box["y"] >= p["y"] - 4 and
                   box["x"] + box["w"] <= p["x"] + p["w"] + 4 and
                   box["y"] + box["h"] <= p["y"] + p["h"] + 4]
        box["depth"] = len(parents)

    final_boxes = sorted(boxes_asc, key=lambda b: b["area"], reverse=True)
    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    return {
        "screen_width": orig_w,
        "screen_height": orig_h,
        "count": len(final_boxes),
        "elapsed_ms": elapsed_ms,
        "boxes": final_boxes
    }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: detect_ui.py <image_path> [output_json_path]"}))
        sys.exit(1)

    image_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    result = detect_ui_elements(image_path)
    output_json = json.dumps(result, indent=None)

    if output_path:
        with open(output_path, "w") as f:
            f.write(output_json)
    else:
        print(output_json)

if __name__ == "__main__":
    main()
