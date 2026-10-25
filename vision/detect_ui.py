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

def compute_iou(b1, b2):
    """Computes Intersection over Union (IoU) between two bounding boxes."""
    x1 = max(b1['x'], b2['x'])
    y1 = max(b1['y'], b2['y'])
    x2 = min(b1['x'] + b1['w'], b2['x'] + b2['w'])
    y2 = min(b1['y'] + b1['h'], b2['y'] + b2['h'])

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h
    if inter_area == 0:
        return 0.0

    area1 = b1['w'] * b1['h']
    area2 = b2['w'] * b2['h']
    union_area = area1 + area2 - inter_area
    return float(inter_area) / union_area if union_area > 0 else 0.0

def compute_containment(b1, b2):
    """Computes fraction of the smaller box that is inside the larger box."""
    x1 = max(b1['x'], b2['x'])
    y1 = max(b1['y'], b2['y'])
    x2 = min(b1['x'] + b1['w'], b2['x'] + b2['w'])
    y2 = min(b1['y'] + b1['h'], b2['y'] + b2['h'])

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h
    if inter_area == 0:
        return 0.0

    min_area = min(b1['w'] * b1['h'], b2['w'] * b2['h'])
    return float(inter_area) / min_area if min_area > 0 else 0.0

def deduplicate_boxes(boxes, iou_thresh=0.72, contain_thresh=0.88):
    """
    Eliminates concentric inner/outer border artifacts created by multi-pixel frames,
    merging them into the unified outer bounding box and preserving specific types.
    Adapts size tolerance dynamically to ensure small elements are not falsely merged.
    """
    sorted_boxes = sorted(boxes, key=lambda b: b['area'], reverse=True)
    deduped = []

    for b in sorted_boxes:
        merged = False
        for existing in deduped:
            # Prevent client window from swallowing internal content viewport/panels
            if bool(existing.get("is_client")) != bool(b.get("is_client")):
                continue

            iou = compute_iou(b, existing)
            contain = compute_containment(b, existing)
            size_diff = abs(b['w'] - existing['w']) + abs(b['h'] - existing['h'])
            min_dim = min(b['w'], b['h'], existing['w'], existing['h'])
            max_size_diff = min(28, max(5, int(min_dim * 0.42)))

            # Measure edge distance between candidate and existing box
            edge_x1 = abs(b['x'] - existing['x'])
            edge_y1 = abs(b['y'] - existing['y'])
            edge_x2 = abs((b['x'] + b['w']) - (existing['x'] + existing['w']))
            edge_y2 = abs((b['y'] + b['h']) - (existing['y'] + existing['h']))
            max_edge_diff = max(edge_x1, edge_y1, edge_x2, edge_y2)

            # Never merge distinct structural regions (such as full window vs browser body below toolbar).
            # A genuine multi-pixel border artifact has edge differences <= 25px.
            if max_edge_diff > 25:
                continue

            # If two boxes have high IoU or one almost entirely contains the other with minor size difference
            if iou >= iou_thresh or (contain >= contain_thresh and size_diff <= max_size_diff):
                merged = True
                # Merge coordinates to outer extent
                nx = min(existing['x'], b['x'])
                ny = min(existing['y'], b['y'])
                nw = max(existing['x'] + existing['w'], b['x'] + b['w']) - nx
                nh = max(existing['y'] + existing['h'], b['y'] + b['h']) - ny
                existing['x'] = int(nx)
                existing['y'] = int(ny)
                existing['w'] = int(nw)
                existing['h'] = int(nh)
                existing['area'] = int(nw * nh)

                # Upgrade semantic type if new box is more specific
                type_priority = {
                    "grid_container": 7,
                    "grid_row": 6,
                    "slot": 5,
                    "item": 4,
                    "button": 4,
                    "input": 4,
                    "text_block": 3,
                    "text": 3,
                    "panel": 2,
                    "detected": 1
                }
                p_new = type_priority.get(b.get("type"), 1)
                p_old = type_priority.get(existing.get("type"), 1)
                if p_new > p_old:
                    existing['type'] = b['type']
                break
        if not merged:
            deduped.append(dict(b))

    return deduped

def compute_border_contrast(gray, x, y, w, h):
    """
    Measures edge contrast across the outer perimeter of a candidate bounding box.
    Uses adaptive probe depth (1px for small shapes <24px, 2px for <44px, 3px for large)
    to prevent sampling interference from adjacent items or grid slots.
    """
    h_img, w_img = gray.shape
    if x <= 1 or y <= 1 or x + w >= w_img - 2 or y + h >= h_img - 2:
        return 30.0  # Outer boundaries / screen panels are given full confidence

    d = 1 if (w < 24 or h < 24) else (2 if (w < 44 or h < 44) else 3)

    top_out = gray[max(0, y-d):y, x:x+w]
    top_in = gray[y:min(h_img, y+d), x:x+w]
    diff_t = abs(float(top_out.mean()) - float(top_in.mean())) if top_out.size and top_in.size else 0.0

    bot_in = gray[max(0, y+h-d):y+h, x:x+w]
    bot_out = gray[y+h:min(h_img, y+h+d), x:x+w]
    diff_b = abs(float(bot_in.mean()) - float(bot_out.mean())) if bot_in.size and bot_out.size else 0.0

    left_out = gray[y:y+h, max(0, x-d):x]
    left_in = gray[y:y+h, x:min(w_img, x+d)]
    diff_l = abs(float(left_out.mean()) - float(left_in.mean())) if left_out.size and left_in.size else 0.0

    right_in = gray[y:y+h, max(0, x+w-d):x+w]
    right_out = gray[y:y+h, x+w:min(w_img, x+w+d)]
    diff_r = abs(float(right_in.mean()) - float(right_out.mean())) if right_in.size and right_out.size else 0.0

    return float((diff_t + diff_b + diff_l + diff_r) / 4.0)

def is_valid_border(gray, x, y, w, h):
    """
    Checks if a candidate bounding box has a genuine UI border.
    In dark scenes (mean < 55, typical dark fantasy UI / RPG frames),
    a contrast of 2.2 is clearly visible and accepted.
    In brighter scenes, a contrast of 5.5 is required.
    """
    h_img, w_img = gray.shape
    if x <= 1 or y <= 1 or x + w >= w_img - 2 or y + h >= h_img - 2:
        return True, 30.0

    # Sample local element brightness
    roi = gray[max(0, y):min(h_img, y+h), max(0, x):min(w_img, x+w)]
    local_mean = float(roi.mean()) if roi.size else 128.0

    contrast = compute_border_contrast(gray, x, y, w, h)

    # Adaptive contrast threshold based on human contrast sensitivity (Weber-Fechner law)
    if local_mean < 45.0:
        req_contrast = 2.2
    elif local_mean < 80.0:
        req_contrast = 3.6
    else:
        req_contrast = 5.5

    # Small shapes (<28px) have concentrated borders; allow slight tolerance
    if w < 28 or h < 28:
        req_contrast = max(2.0, req_contrast * 0.85)

    return (contrast >= req_contrast), contrast

def cluster_slots_and_grids(boxes):
    """
    Detects inventory slot patterns (e.g. Minecraft, WoW, Diablo, Terraria)
    and synthesizes aggregate bounding boxes for rows and entire inventory grids.
    Partitions adjacent slots into contiguous chains to support split hotbars/windows.
    Supports small slots down to 10px.
    """
    # Candidate slots: square-like UI elements
    slots = [b for b in boxes if b.get('type') == 'slot' or
             (10 <= b['w'] <= 180 and 10 <= b['h'] <= 180 and 0.65 <= (b['w'] / b['h']) <= 1.54 and b.get('type') != 'item')]
    if len(slots) < 2:
        return []

    for s in slots:
        if s.get('type') in ('detected', None):
            s['type'] = 'slot'

    slots_sorted = sorted(slots, key=lambda s: (s['y'], s['x']))
    used_slot_indices = set()
    rows = []

    for i, s1 in enumerate(slots_sorted):
        if i in used_slot_indices:
            continue
        band = [s1]
        band_indices = [i]
        for j, s2 in enumerate(slots_sorted):
            if j == i or j in used_slot_indices:
                continue
            if abs(s1['y'] - s2['y']) <= max(4, s1['h'] * 0.25) and abs(s1['h'] - s2['h']) <= max(4, s1['h'] * 0.25):
                band.append(s2)
                band_indices.append(j)

        # Sort band along X
        band_with_idx = sorted(zip(band, band_indices), key=lambda pair: pair[0]['x'])
        current_chain = [band_with_idx[0][0]]
        current_chain_indices = [band_with_idx[0][1]]

        for k in range(1, len(band_with_idx)):
            curr, curr_idx = band_with_idx[k]
            prev = current_chain[-1]
            gap = curr['x'] - (prev['x'] + prev['w'])
            avg_w = (prev['w'] + curr['w']) / 2.0

            if -4 <= gap <= max(14, avg_w * 0.65):
                current_chain.append(curr)
                current_chain_indices.append(curr_idx)
            else:
                if len(current_chain) >= 2:
                    rx = current_chain[0]['x']
                    ry = min(s['y'] for s in current_chain)
                    rw = (current_chain[-1]['x'] + current_chain[-1]['w']) - rx
                    rh = max(s['y'] + s['h'] for s in current_chain) - ry
                    rows.append({
                        'x': int(rx), 'y': int(ry), 'w': int(rw), 'h': int(rh),
                        'area': int(rw * rh), 'extent': 0.96, 'type': 'grid_row',
                        'slots': list(current_chain)
                    })
                    for idx in current_chain_indices:
                        used_slot_indices.add(idx)
                current_chain = [curr]
                current_chain_indices = [curr_idx]

        if len(current_chain) >= 2:
            rx = current_chain[0]['x']
            ry = min(s['y'] for s in current_chain)
            rw = (current_chain[-1]['x'] + current_chain[-1]['w']) - rx
            rh = max(s['y'] + s['h'] for s in current_chain) - ry
            rows.append({
                'x': int(rx), 'y': int(ry), 'w': int(rw), 'h': int(rh),
                'area': int(rw * rh), 'extent': 0.96, 'type': 'grid_row',
                'slots': list(current_chain)
            })
            for idx in current_chain_indices:
                used_slot_indices.add(idx)

    # Cluster stacked rows into grid containers
    grids = []
    used_row_indices = set()
    rows_sorted = sorted(rows, key=lambda r: (r['x'], r['y']))

    for i, r1 in enumerate(rows_sorted):
        if i in used_row_indices:
            continue
        grid_rows = [r1]
        grid_row_indices = [i]
        for j, r2 in enumerate(rows_sorted):
            if j == i or j in used_row_indices:
                continue
            prev_r = grid_rows[-1]
            if abs(prev_r['x'] - r2['x']) <= max(14, prev_r['w'] * 0.08) and abs(prev_r['w'] - r2['w']) <= max(16, prev_r['w'] * 0.08):
                v_gap = r2['y'] - (prev_r['y'] + prev_r['h'])
                if -6 <= v_gap <= max(16, prev_r['h'] * 0.60):
                    grid_rows.append(r2)
                    grid_row_indices.append(j)

        if len(grid_rows) >= 2:
            for idx in grid_row_indices:
                used_row_indices.add(idx)
            gx = min(r['x'] for r in grid_rows)
            gy = min(r['y'] for r in grid_rows)
            gw = max(r['x'] + r['w'] for r in grid_rows) - gx
            gh = max(r['y'] + r['h'] for r in grid_rows) - gy
            grids.append({
                'x': int(gx), 'y': int(gy), 'w': int(gw), 'h': int(gh),
                'area': int(gw * gh), 'extent': 0.98, 'type': 'grid_container'
            })

    clean_rows = []
    for r in rows:
        clean_rows.append({
            'x': int(r['x']), 'y': int(r['y']), 'w': int(r['w']), 'h': int(r['h']),
            'area': int(r['area']), 'extent': r['extent'], 'type': 'grid_row'
        })

    return clean_rows + grids

def cluster_adjacent_columns(boxes):
    """
    Detects adjacent columns or split panels (e.g. left and right halves of a web page
    or multi-column layout) and synthesizes their union into a combined parent container.
    """
    panels = [b for b in boxes if b.get('w', 0) >= 80 and b.get('h', 0) >= 100 and b.get('type') in ('panel', 'detected', 'grid_container')]
    if len(panels) < 2:
        return []

    panels_sorted = sorted(panels, key=lambda p: (p['y'], p['x']))
    unions = []

    for i, p1 in enumerate(panels_sorted):
        for j in range(i + 1, len(panels_sorted)):
            p2 = panels_sorted[j]
            y_diff = abs(p1['y'] - p2['y'])
            h_diff = abs(p1['h'] - p2['h'])
            min_h = min(p1['h'], p2['h'])

            # Must share similar vertical span (within 10% height tolerance or 16px)
            if y_diff <= max(12, int(min_h * 0.10)) and h_diff <= max(16, int(min_h * 0.10)):
                p_left, p_right = (p1, p2) if p1['x'] <= p2['x'] else (p2, p1)
                gap = p_right['x'] - (p_left['x'] + p_left['w'])

                # Gap between adjacent columns can be 0 (divider line) or a small margin (up to 40px)
                if -6 <= gap <= 40:
                    ux = p_left['x']
                    uy = min(p_left['y'], p_right['y'])
                    uw = (p_right['x'] + p_right['w']) - ux
                    uh = max(p_left['y'] + p_left['h'], p_right['y'] + p_right['h']) - uy
                    u_area = uw * uh

                    if u_area > max(p1['area'], p2['area']) * 1.25:
                        unions.append({
                            'x': int(ux),
                            'y': int(uy),
                            'w': int(uw),
                            'h': int(uh),
                            'area': int(u_area),
                            'extent': 0.98,
                            'contrast': max(p1.get('contrast', 25.0), p2.get('contrast', 25.0)),
                            'type': 'panel'
                        })

    return unions

def detect_window_content_areas(gray, client_boxes):
    """
    Detects the main content viewport below the header/URL bar in application windows
    (e.g., browsers, editors) so users can select the full page body without tabs and URL bar.
    """
    content_boxes = []
    h_img, w_img = gray.shape

    for win in client_boxes:
        wx = max(0, int(win.get('x', 0)))
        wy = max(0, int(win.get('y', 0)))
        ww = min(w_img - wx, int(win.get('w', 0)))
        wh = min(h_img - wy, int(win.get('h', 0)))

        if ww < 300 or wh < 200:
            continue

        header_min_y = wy + 40
        header_max_y = wy + min(160, int(wh * 0.35))
        if header_max_y <= header_min_y or header_max_y >= h_img:
            continue

        sub_gray = gray[header_min_y:header_max_y, wx:wx + ww]
        if sub_gray.shape[0] < 5 or sub_gray.shape[1] < 100:
            continue

        # Horizontal gradient across the full window width
        row_diffs = np.mean(np.abs(np.diff(sub_gray.astype(np.float32), axis=0)), axis=1)
        if len(row_diffs) == 0:
            continue

        best_row_idx = int(np.argmax(row_diffs))
        max_diff = float(row_diffs[best_row_idx])

        if max_diff >= 3.5:
            sep_y = header_min_y + best_row_idx + 1
            body_h = (wy + wh) - sep_y
            if body_h >= 100:
                content_boxes.append({
                    "x": int(wx),
                    "y": int(sep_y),
                    "w": int(ww),
                    "h": int(body_h),
                    "area": int(ww * body_h),
                    "extent": 1.0,
                    "contrast": 35.0,
                    "type": "panel",
                    "title": win.get("title", ""),
                    "class": win.get("class", "")
                })

    return content_boxes

def detect_text_regions(gray, orig_w, orig_h):
    """
    Detects text lines, code blocks, labels, and paragraph blocks.
    Uses horizontal morphological gradient to capture character strokes,
    and directional morphology to bridge letters into lines and lines into paragraphs.
    """
    # 1. Sobel-x gradient captures vertical character strokes (letters)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_x = cv2.convertScaleAbs(grad_x)

    # 2. Horizontal closing connects letters into words and words into lines
    k_line = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
    closed_line = cv2.morphologyEx(grad_x, cv2.MORPH_CLOSE, k_line)
    _, thresh_line = cv2.threshold(closed_line, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours_line, _ = cv2.findContours(thresh_line, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    text_boxes = []

    for cnt in contours_line:
        x, y, w, h = cv2.boundingRect(cnt)
        if w >= 20 and 8 <= h <= 54:
            # Check internal pixel standard deviation to ensure it contains texture/glyphs
            roi = gray[y:y+h, x:x+w]
            if roi.size and float(np.std(roi)) >= 6.5:
                text_boxes.append({
                    'x': int(x),
                    'y': int(y),
                    'w': int(w),
                    'h': int(h),
                    'area': int(w * h),
                    'extent': 0.95,
                    'contrast': 30.0,
                    'type': 'text'
                })

    # 3. Vertical closing on the line mask to synthesize paragraph and code blocks
    k_para = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 15))
    closed_para = cv2.morphologyEx(thresh_line, cv2.MORPH_CLOSE, k_para)
    contours_para, _ = cv2.findContours(closed_para, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours_para:
        x, y, w, h = cv2.boundingRect(cnt)
        # Paragraphs must have substantial height (at least 2 lines) and width
        if w >= 36 and h >= 26 and (w * h) >= 1200:
            roi = gray[y:y+h, x:x+w]
            if roi.size and float(np.std(roi)) >= 6.5:
                text_boxes.append({
                    'x': int(x),
                    'y': int(y),
                    'w': int(w),
                    'h': int(h),
                    'area': int(w * h),
                    'extent': 0.96,
                    'contrast': 35.0,
                    'type': 'text_block'
                })

    return text_boxes

def is_duplicate(a, b, tol=5):
    """Checks whether box a and box b are virtually identical."""
    return (abs(a['x'] - b['x']) <= tol and
            abs(a['y'] - b['y']) <= tol and
            abs(a['w'] - b['w']) <= tol * 1.5 and
            abs(a['h'] - b['h']) <= tol * 1.5)

def detect_ui_elements(image_path, clients_path=None, min_area=64, max_area_ratio=0.98):
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

    # 3. Multi-threshold Canny edge detection & Multi-scale closing
    edges_sharp = cv2.Canny(filtered, 28, 85)
    edges_dark = cv2.Canny(filtered, 12, 45)
    edges_raw = cv2.bitwise_or(edges_sharp, edges_dark)

    # Fine kernel preserves small 10-24px buttons/slots without bridging adjacent gaps
    k_fine = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed_fine = cv2.morphologyEx(edges_raw, cv2.MORPH_CLOSE, k_fine)
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed_standard = cv2.morphologyEx(edges_raw, cv2.MORPH_CLOSE, k_close)
    closed_edges = cv2.bitwise_or(closed_fine, closed_standard)

    # 4. Large-scale morphological closing for dark/translucent panels (dialogue, chat, HUD)
    # Apply closing on both raw gray and CLAHE filtered to detect both translucent HUDs and dark frames
    k_panel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
    closed_filtered = cv2.morphologyEx(filtered, cv2.MORPH_CLOSE, k_panel)
    panel_grad_f = cv2.morphologyEx(closed_filtered, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    _, panel_edges_f = cv2.threshold(panel_grad_f, 8, 255, cv2.THRESH_BINARY)

    closed_gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, k_panel)
    panel_grad_g = cv2.morphologyEx(closed_gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    _, panel_edges_g = cv2.threshold(panel_grad_g, 12, 255, cv2.THRESH_BINARY)

    combined = cv2.bitwise_or(closed_edges, cv2.bitwise_or(panel_edges_f, panel_edges_g))

    # 5. Find contours using two-level hierarchy
    contours, _ = cv2.findContours(combined, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    raw_boxes = []
    client_boxes = []

    # Pre-seed visible Hyprland client windows (especially floating overlay windows)
    if clients_path and os.path.isfile(clients_path):
        try:
            active_ws_str = os.environ.get("SMARTSHOT_WORKSPACE_ID", "").strip()
            mon_x_str = os.environ.get("SMARTSHOT_MONITOR_X", "").strip()
            mon_y_str = os.environ.get("SMARTSHOT_MONITOR_Y", "").strip()
            mon_x = int(float(mon_x_str)) if mon_x_str else 0
            mon_y = int(float(mon_y_str)) if mon_y_str else 0
            mon_scale_str = os.environ.get("SMARTSHOT_MONITOR_SCALE", "").strip()
            try:
                mon_scale = float(mon_scale_str) if mon_scale_str else 1.0
                if mon_scale <= 0:
                    mon_scale = 1.0
            except ValueError:
                mon_scale = 1.0

            with open(clients_path, "r") as cf:
                clients_data = json.load(cf)
                if isinstance(clients_data, list):
                    for c in clients_data:
                        if not isinstance(c, dict):
                            continue
                        if c.get("hidden") is True or c.get("mapped") is False:
                            continue
                        is_pinned = bool(c.get("pinned", False))
                        if active_ws_str and not is_pinned:
                            ws = c.get("workspace")
                            ws_id = ws.get("id") if isinstance(ws, dict) else ws
                            ws_name = ws.get("name") if isinstance(ws, dict) else None
                            matches = False
                            if ws_id is not None and str(ws_id) == active_ws_str:
                                matches = True
                            elif ws_name is not None and str(ws_name) == active_ws_str:
                                matches = True
                            if not matches:
                                continue
                        at = c.get("at", [])
                        size = c.get("size", [])
                        if len(at) == 2 and len(size) == 2:
                            cx, cy = int(at[0]) - mon_x, int(at[1]) - mon_y
                            cw, ch = int(size[0]), int(size[1])
                            if cw >= 20 and ch >= 20:
                                phys_x = int(round(cx * mon_scale))
                                phys_y = int(round(cy * mon_scale))
                                phys_w = int(round(cw * mon_scale))
                                phys_h = int(round(ch * mon_scale))

                                # Clamping [0, orig_w] and [0, orig_h]
                                clamped_x1 = max(0, min(orig_w, phys_x))
                                clamped_y1 = max(0, min(orig_h, phys_y))
                                clamped_x2 = max(0, min(orig_w, phys_x + phys_w))
                                clamped_y2 = max(0, min(orig_h, phys_y + phys_h))
                                clamped_w = clamped_x2 - clamped_x1
                                clamped_h = clamped_y2 - clamped_y1

                                if clamped_w >= 20 and clamped_h >= 20:
                                    is_fl = bool(c.get("floating", False))
                                    win_obj = {
                                        "x": int(clamped_x1),
                                        "y": int(clamped_y1),
                                        "w": int(clamped_w),
                                        "h": int(clamped_h),
                                        "area": int(clamped_w * clamped_h),
                                        "extent": 1.0,
                                        "contrast": 60.0,
                                        "type": "floating_window" if is_fl else "window",
                                        "floating": is_fl,
                                        "pinned": is_pinned,
                                        "focusHistoryID": c.get("focusHistoryID", 999),
                                        "title": c.get("title", ""),
                                        "class": c.get("class", ""),
                                        "is_client": True
                                    }
                                    raw_boxes.append(win_obj)
                                    client_boxes.append(win_obj)
        except Exception:
            pass

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 10 or h < 10:
            continue

        box_area = w * h
        if box_area < min_area or box_area > max_area:
            continue

        # Filter out extreme 1-4px line dividers
        if (h <= 4 and w > 40) or (w <= 4 and h > 40):
            continue

        area = cv2.contourArea(cnt)
        extent = float(area) / box_area
        min_extent = 0.45 if box_area < 450 else 0.50
        if extent < min_extent:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        max_vertices = 18 if box_area < 500 else 14
        if len(approx) > max_vertices:
            continue

        valid, contrast = is_valid_border(gray, x, y, w, h)
        if not valid:
            continue

        # Classify basic type
        elem_type = "detected"
        if w >= 220 and h >= 140:
            elem_type = "panel"
        elif 10 <= w <= 180 and 10 <= h <= 180 and 0.65 <= (w / h) <= 1.54:
            elem_type = "slot"
        elif 20 <= w <= 800 and 12 <= h <= 64:
            elem_type = "input" if w > 260 else "button"

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

    # Suppress periodic mesh / background texture tiling (e.g. 14+ identical tiles with low contrast)
    size_bins = {}
    for b in raw_boxes:
        key = (b["w"] // 4, b["h"] // 4)
        size_bins[key] = size_bins.get(key, 0) + 1

    filtered_boxes = []
    for b in raw_boxes:
        key = (b["w"] // 4, b["h"] // 4)
        if size_bins[key] > 14 and b.get("contrast", 0) < 22.0:
            continue
        filtered_boxes.append(b)

    # 1. Deduplicate concentric inner/outer border boxes FIRST to produce clean, unique frames
    deduped_raw = deduplicate_boxes(filtered_boxes, iou_thresh=0.72, contain_thresh=0.88)

    # 2. Classify nested items inside slots: if a box is inside an existing slot, mark it as 'item'
    for b in deduped_raw:
        for s in deduped_raw:
            if s is not b and s.get('type') == 'slot' and s['area'] > b['area'] * 1.3:
                if (b['x'] >= s['x'] - 2 and b['y'] >= s['y'] - 2 and
                    b['x'] + b['w'] <= s['x'] + s['w'] + 2 and
                    b['y'] + b['h'] <= s['y'] + s['h'] + 2):
                    b['type'] = 'item'
                    break

    # 3. Synthesize inventory rows and grid containers from clean slots
    synthesized = cluster_slots_and_grids(deduped_raw)

    # 3b. Synthesize composite panels / columns into unified parent containers (web page body / split panels)
    column_unions = cluster_adjacent_columns(deduped_raw)

    # 3c. Detect window content viewports (web page body below browser header)
    window_content_areas = detect_window_content_areas(gray, client_boxes)

    # 3d. Detect text lines, code snippets, labels, and paragraph blocks
    text_regions = detect_text_regions(gray, orig_w, orig_h)

    all_boxes = deduped_raw + synthesized + column_unions + window_content_areas + text_regions

    # 4. Final deduplication pass to merge synthesized grids with detected panels
    final_deduped = deduplicate_boxes(all_boxes, iou_thresh=0.80, contain_thresh=0.90)

    # Clamping and filtering minimum size
    clamped_boxes = []
    for b in final_deduped:
        bx1 = max(0, min(orig_w, b["x"]))
        by1 = max(0, min(orig_h, b["y"]))
        bx2 = max(0, min(orig_w, b["x"] + b["w"]))
        by2 = max(0, min(orig_h, b["y"] + b["h"]))
        bw = bx2 - bx1
        bh = by2 - by1
        if bw < 8 or bh < 8:
            continue
        b["x"] = int(bx1)
        b["y"] = int(by1)
        b["w"] = int(bw)
        b["h"] = int(bh)
        b["area"] = int(bw * bh)
        clamped_boxes.append(b)

    # Semantic hierarchy depth calculation
    boxes_asc = sorted(clamped_boxes, key=lambda b: b["area"])
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
        print(json.dumps({"error": "Usage: detect_ui.py <image_path> [output_json_path] [clients_json_path]"}))
        sys.exit(1)

    image_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    clients_path = sys.argv[3] if len(sys.argv) > 3 else None

    result = detect_ui_elements(image_path, clients_path=clients_path)
    output_json = json.dumps(result, indent=None)

    if output_path:
        temp_path = f"{output_path}.tmp.{os.getpid()}"
        try:
            with open(temp_path, "w") as f:
                f.write(output_json)
            os.replace(temp_path, output_path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            raise
    else:
        print(output_json)

if __name__ == "__main__":
    main()
