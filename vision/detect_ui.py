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

def cluster_slots_and_grids(boxes):
    """
    Detects inventory slot patterns (e.g. Minecraft, WoW, Diablo, Terraria)
    and synthesizes aggregate bounding boxes for rows and entire inventory grids.
    """
    slots = [b for b in boxes if 18 <= b['w'] <= 140 and 18 <= b['h'] <= 140 and 0.70 <= (b['w'] / b['h']) <= 1.42]
    if len(slots) < 2:
        return []

    # Sort slots by y, then x
    slots_sorted = sorted(slots, key=lambda s: (s['y'], s['x']))
    rows = []
    used = set()

    for i, s1 in enumerate(slots_sorted):
        if i in used:
            continue
        row_slots = [s1]
        for j, s2 in enumerate(slots_sorted):
            if j == i or j in used:
                continue
            # Check vertical alignment and similar height
            if abs(s1['y'] - s2['y']) <= 8 and abs(s1['h'] - s2['h']) <= 8:
                row_slots.append(s2)

        if len(row_slots) >= 2:
            row_slots.sort(key=lambda s: s['x'])
            # Verify consecutive spacing
            is_valid_row = True
            for k in range(len(row_slots) - 1):
                gap = row_slots[k+1]['x'] - (row_slots[k]['x'] + row_slots[k]['w'])
                avg_w = (row_slots[k]['w'] + row_slots[k+1]['w']) / 2.0
                if gap > avg_w * 2.2 or gap < -6:
                    is_valid_row = False
                    break
            if is_valid_row:
                for s in row_slots:
                    used.add(slots_sorted.index(s))
                rx = row_slots[0]['x']
                ry = min(s['y'] for s in row_slots)
                rw = (row_slots[-1]['x'] + row_slots[-1]['w']) - rx
                rh = max(s['y'] + s['h'] for s in row_slots) - ry
                rows.append({
                    'x': rx, 'y': ry, 'w': rw, 'h': rh,
                    'area': rw * rh, 'extent': 0.96,
                    'type': 'grid_row'
                })

    # Find full grid containers by grouping stacked rows
    grids = []
    if len(rows) >= 2:
        rows_sorted = sorted(rows, key=lambda r: r['y'])
        grid_rows = [rows_sorted[0]]
        for r2 in rows_sorted[1:]:
            r1 = grid_rows[-1]
            # Check horizontal alignment and width similarity
            if abs(r1['x'] - r2['x']) <= 14 and abs(r1['w'] - r2['w']) <= 18:
                gap = r2['y'] - (r1['y'] + r1['h'])
                if gap <= r1['h'] * 2.2 and gap >= -6:
                    grid_rows.append(r2)
            else:
                if len(grid_rows) >= 2:
                    gx = min(r['x'] for r in grid_rows)
                    gy = min(r['y'] for r in grid_rows)
                    gw = max(r['x'] + r['w'] for r in grid_rows) - gx
                    gh = max(r['y'] + r['h'] for r in grid_rows) - gy
                    grids.append({'x': gx, 'y': gy, 'w': gw, 'h': gh, 'area': gw * gh, 'extent': 0.98, 'type': 'grid_container'})
                grid_rows = [r2]

        if len(grid_rows) >= 2:
            gx = min(r['x'] for r in grid_rows)
            gy = min(r['y'] for r in grid_rows)
            gw = max(r['x'] + r['w'] for r in grid_rows) - gx
            gh = max(r['y'] + r['h'] for r in grid_rows) - gy
            grids.append({'x': gx, 'y': gy, 'w': gw, 'h': gh, 'area': gw * gh, 'extent': 0.98, 'type': 'grid_container'})

    return rows + grids

def is_concentric(a, b, tol=12):
    """Checks whether box a and box b are near-identical concentric frames (double borders)."""
    d_left = abs(a['x'] - b['x'])
    d_top = abs(a['y'] - b['y'])
    d_right = abs((a['x'] + a['w']) - (b['x'] + b['w']))
    d_bottom = abs((a['y'] + a['h']) - (b['y'] + b['h']))
    return (d_left <= tol and d_top <= tol and d_right <= tol and d_bottom <= tol)

def detect_ui_elements(image_path, min_area=360, max_area_ratio=0.98):
    start_time = time.time()

    img = cv2.imread(image_path)
    if img is None:
        return {"error": f"Failed to load image: {image_path}", "boxes": []}

    orig_h, orig_w = img.shape[:2]
    total_area = orig_w * orig_h
    max_area = total_area * max_area_ratio

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. Bilateral filter: flattens 3D game background textures while preserving sharp UI edges and pixel art
    filtered = cv2.bilateralFilter(gray, 5, 35, 35)

    # 2. Multi-threshold Canny edge detection
    edges = cv2.Canny(filtered, 35, 105)

    # 3. Morphological rectangular kernels for horizontal and vertical UI borders
    # Essential for fantasy frames with filigree, ornate corners, and grid dividers
    kernel3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel3, iterations=1)

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (14, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 14))
    h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, v_kernel)
    lines = cv2.bitwise_or(h_lines, v_lines)

    # 4. Dark semi-transparent panels & HUD detection (RPG dialogues, chat windows, quest logs)
    blurred_lum = cv2.GaussianBlur(filtered, (9, 9), 0)
    thresh_adapt = cv2.adaptiveThreshold(blurred_lum, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 4)
    clean_thresh = cv2.morphologyEx(thresh_adapt, cv2.MORPH_OPEN, kernel3)

    # Combine edge features and panel regions
    combined = cv2.bitwise_or(closed_edges, cv2.bitwise_or(lines, clean_thresh))

    # Find contours
    contours, _ = cv2.findContours(combined, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    raw_boxes = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        if w < 16 or h < 16:
            continue

        box_area = w * h
        if box_area < min_area or box_area > max_area:
            continue

        # Rectangularity check
        extent = float(area) / box_area
        if extent < 0.40:
            continue

        raw_boxes.append({
            "x": int(x),
            "y": int(y),
            "w": int(w),
            "h": int(h),
            "area": int(box_area),
            "extent": round(extent, 2),
            "type": "detected"
        })

    # Synthesize inventory rows and grid containers
    synthesized = cluster_slots_and_grids(raw_boxes)
    raw_boxes.extend(synthesized)

    # Deduplicate overlapping or near-identical concentric frames
    raw_boxes.sort(key=lambda b: b["area"], reverse=True)
    deduped = []

    for b in raw_boxes:
        is_dup = False
        for existing in deduped:
            if is_concentric(b, existing, tol=12):
                is_dup = True
                break
        if not is_dup:
            deduped.append(b)

    # Hierarchy depth calculation
    boxes_asc = sorted(deduped, key=lambda b: b["area"])
    for i, box in enumerate(boxes_asc):
        box["id"] = i
        parents = []
        for other in boxes_asc:
            if other["area"] > box["area"]:
                if (box["x"] >= other["x"] - 5 and
                    box["y"] >= other["y"] - 5 and
                    box["x"] + box["w"] <= other["x"] + other["w"] + 5 and
                    box["y"] + box["h"] <= other["y"] + other["h"] + 5):
                    parents.append(other["area"])
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
