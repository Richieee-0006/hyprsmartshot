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
import argparse
import cv2
import numpy as np

_VISION_DIR = os.path.dirname(os.path.abspath(__file__))
if _VISION_DIR not in sys.path:
    sys.path.insert(0, _VISION_DIR)

from config_loader import load_config
from rating import rate_and_filter_boxes

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

def _sat_mean(sat, x1, y1, x2, y2):
    """Computes exact rectangle mean in O(1) from an OpenCV integral image."""
    if x2 <= x1 or y2 <= y1:
        return 0.0
    total = float(sat[y2, x2] - sat[y1, x2] - sat[y2, x1] + sat[y1, x1])
    return total / ((x2 - x1) * (y2 - y1))


def deduplicate_boxes(boxes, iou_thresh=0.72, contain_thresh=0.88):
    """
    Eliminates concentric inner/outer border artifacts created by multi-pixel frames,
    merging them into the unified outer bounding box and preserving specific types.
    Uses spatial grid bucketing to preserve exact insertion-order semantics in near-linear time.
    """
    sorted_boxes = sorted(boxes, key=lambda b: b['area'], reverse=True)
    deduped = []
    # Track [x, y, x2, y2, w, h, area, is_client, cell_x, cell_y] per deduped entry
    meta = []
    grid = {}
    cell_size = 32
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

    for b in sorted_boxes:
        bx = b['x']
        by = b['y']
        bw = b['w']
        bh = b['h']
        bx2 = bx + bw
        by2 = by + bh
        b_area = bw * bh
        b_client = bool(b.get("is_client"))

        gx = bx // cell_size
        gy = by // cell_size
        cand_indices = []
        for dx in (-1, 0, 1):
            cx = gx + dx
            for dy in (-1, 0, 1):
                bucket = grid.get((cx, gy + dy))
                if bucket:
                    cand_indices.extend(bucket)

        if len(cand_indices) > 1:
            cand_indices.sort()

        merged = False
        for idx in cand_indices:
            m = meta[idx]
            if m[7] != b_client:
                continue

            ex, ey, ex2, ey2, ew, eh, e_area = m[0], m[1], m[2], m[3], m[4], m[5], m[6]

            # Never merge distinct structural regions (max edge diff > 25px)
            if (abs(bx - ex) > 25 or abs(by - ey) > 25 or
                    abs(bx2 - ex2) > 25 or abs(by2 - ey2) > 25):
                continue

            ix1 = bx if bx > ex else ex
            iy1 = by if by > ey else ey
            ix2 = bx2 if bx2 < ex2 else ex2
            iy2 = by2 if by2 < ey2 else ey2
            iw = ix2 - ix1
            ih = iy2 - iy1
            if iw <= 0 or ih <= 0:
                continue

            inter_area = iw * ih
            union_area = b_area + e_area - inter_area
            iou = float(inter_area) / union_area if union_area > 0 else 0.0
            min_area = b_area if b_area < e_area else e_area
            contain = float(inter_area) / min_area if min_area > 0 else 0.0

            size_diff = abs(bw - ew) + abs(bh - eh)
            min_dim = min(bw, bh, ew, eh)
            max_size_diff = min(28, max(5, int(min_dim * 0.42)))

            # Keep distinct parent panel vs synthesized grid/row containers when padding separates them
            b_type = b.get("type")
            e_type = deduped[idx].get("type")
            if (({b_type, e_type} & {"grid_container", "grid_row"}) and
                    ({b_type, e_type} & {"panel", "detected"}) and
                    (abs(bw - ew) + abs(bh - eh)) > 10):
                continue

            if iou >= iou_thresh or (contain >= contain_thresh and size_diff <= max_size_diff):
                merged = True
                existing = deduped[idx]
                nx = ex if ex < bx else bx
                ny = ey if ey < by else by
                nx2 = ex2 if ex2 > bx2 else bx2
                ny2 = ey2 if ey2 > by2 else by2
                nw = nx2 - nx
                nh = ny2 - ny
                n_area = nw * nh

                existing['x'] = int(nx)
                existing['y'] = int(ny)
                existing['w'] = int(nw)
                existing['h'] = int(nh)
                existing['area'] = int(n_area)

                p_new = type_priority.get(b.get("type"), 1)
                p_old = type_priority.get(existing.get("type"), 1)
                if p_new > p_old:
                    existing['type'] = b['type']

                old_gx, old_gy = m[8], m[9]
                new_gx, new_gy = nx // cell_size, ny // cell_size
                if new_gx != old_gx or new_gy != old_gy:
                    grid[(old_gx, old_gy)].remove(idx)
                    grid.setdefault((new_gx, new_gy), []).append(idx)
                    m[8], m[9] = new_gx, new_gy
                m[0], m[1], m[2], m[3], m[4], m[5], m[6] = nx, ny, nx2, ny2, nw, nh, n_area
                break

        if not merged:
            idx = len(deduped)
            deduped.append(dict(b))
            meta.append([bx, by, bx2, by2, bw, bh, b_area, b_client, gx, gy])
            grid.setdefault((gx, gy), []).append(idx)

    return deduped


def compute_border_contrast(gray, x, y, w, h, sat=None):
    """
    Measures edge contrast across the outer perimeter of a candidate bounding box.
    Uses adaptive probe depth (1px for small shapes <24px, 2px for <44px, 3px for large)
    to prevent sampling interference from adjacent items or grid slots.
    """
    h_img, w_img = gray.shape
    if x <= 1 or y <= 1 or x + w >= w_img - 2 or y + h >= h_img - 2:
        return 30.0  # Outer boundaries / screen panels are given full confidence

    d = 1 if (w < 24 or h < 24) else (2 if (w < 44 or h < 44) else 3)

    if sat is not None:
        ty_out = max(0, y - d)
        ty_in = min(h_img, y + d)
        by_in = max(0, y + h - d)
        by_out = min(h_img, y + h + d)
        lx_out = max(0, x - d)
        lx_in = min(w_img, x + d)
        rx_in = max(0, x + w - d)
        rx_out = min(w_img, x + w + d)

        diff_t = abs(_sat_mean(sat, x, ty_out, x + w, y) - _sat_mean(sat, x, y, x + w, ty_in)) if y > ty_out and ty_in > y else 0.0
        diff_b = abs(_sat_mean(sat, x, by_in, x + w, y + h) - _sat_mean(sat, x, y + h, x + w, by_out)) if y + h > by_in and by_out > y + h else 0.0
        diff_l = abs(_sat_mean(sat, lx_out, y, x, y + h) - _sat_mean(sat, x, y, lx_in, y + h)) if x > lx_out and lx_in > x else 0.0
        diff_r = abs(_sat_mean(sat, rx_in, y, x + w, y + h) - _sat_mean(sat, x + w, y, rx_out, y + h)) if x + w > rx_in and rx_out > x + w else 0.0
    else:
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

    # Best 3 edges (handles HUD/game panels with an open/gradient edge against 3D game scenes)
    diffs = sorted([diff_t, diff_b, diff_l, diff_r], reverse=True)
    best3 = float(sum(diffs[:3]) / 3.0)
    avg4 = float(sum(diffs) / 4.0)
    return max(avg4, best3 * 0.92)


def is_valid_border(gray, x, y, w, h, sat=None):
    """
    Checks if a candidate bounding box has a genuine UI border.
    In dark scenes (mean < 55, typical dark fantasy UI / RPG frames),
    a contrast of 1.8 is clearly visible and accepted.
    In brighter scenes, a contrast of 4.2 is required.
    """
    h_img, w_img = gray.shape
    if x <= 1 or y <= 1 or x + w >= w_img - 2 or y + h >= h_img - 2:
        return True, 30.0

    if sat is not None:
        local_mean = _sat_mean(sat, max(0, x), max(0, y), min(w_img, x + w), min(h_img, y + h))
    else:
        roi = gray[max(0, y):min(h_img, y+h), max(0, x):min(w_img, x+w)]
        local_mean = float(roi.mean()) if roi.size else 128.0

    contrast = compute_border_contrast(gray, x, y, w, h, sat=sat)

    # Adaptive contrast threshold based on human contrast sensitivity (Weber-Fechner law)
    if local_mean < 45.0:
        req_contrast = 1.8
    elif local_mean < 80.0:
        req_contrast = 2.8
    else:
        req_contrast = 4.2

    # Small shapes (<28px) have concentrated borders; allow slight tolerance
    if w < 28 or h < 28:
        req_contrast = max(1.8, req_contrast * 0.85)

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
        tol_y = max(4, s1['h'] * 0.25)
        for j, s2 in enumerate(slots_sorted):
            if s2['y'] - s1['y'] > tol_y:
                break
            if j == i or j in used_slot_indices:
                continue
            if abs(s1['y'] - s2['y']) <= tol_y and abs(s1['h'] - s2['h']) <= tol_y:
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
    panels = [b for b in boxes if b.get('w', 0) >= 50 and b.get('h', 0) >= 100 and b.get('type') in ('panel', 'detected', 'grid_container')]
    if len(panels) < 2:
        return []

    panels_sorted = sorted(panels, key=lambda p: (p['y'], p['x']))
    unions = []

    for i, p1 in enumerate(panels_sorted):
        max_y_tol = max(12, int(p1['h'] * 0.10))
        for j in range(i + 1, len(panels_sorted)):
            p2 = panels_sorted[j]
            y_diff = p2['y'] - p1['y']
            if y_diff > max_y_tol:
                break
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
    Detects internal window structure in desktop applications (browsers, Discord, Slack, editors):
    1. Browser page viewport below the header/URL bar.
    2. Column panels & sidebars across multi-pane application layouts.
    3. Header bars, chat message panes, and footer input fields within panels.
    """
    content_boxes = []
    h_img, w_img = gray.shape

    for win in client_boxes:
        if win.get("is_layer"):
            continue
        wx = max(0, int(win.get('x', 0)))
        wy = max(0, int(win.get('y', 0)))
        ww = min(w_img - wx, int(win.get('w', 0)))
        wh = min(h_img - wy, int(win.get('h', 0)))

        if ww < 180 or wh < 150:
            continue

        win_sub = gray[wy:wy+wh, wx:wx+ww]
        if win_sub.size == 0:
            continue

        # 1. Full-window browser header & page body detection
        if ww >= 300 and wh >= 200:
            header_min_y = wy + 40
            header_max_y = wy + min(160, int(wh * 0.35))
            if header_max_y > header_min_y and header_max_y < h_img:
                sub_gray = gray[header_min_y:header_max_y, wx:wx + ww]
                if sub_gray.shape[0] >= 5 and sub_gray.shape[1] >= 100:
                    row_diffs = np.mean(cv2.absdiff(sub_gray[1:, :], sub_gray[:-1, :]), axis=1)
                    if len(row_diffs) > 0:
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

        # 2. Multi-column and sidebar detection (Discord, Slack, VS Code, Spotify)
        # Skip for game windows where 3D terrain/sky edges should not be split into fake columns
        win_class = str(win.get("class", "")).lower()
        win_title = str(win.get("title", "")).lower()
        is_game = any(g in win_class for g in ["minecraft", "steam_app", "gamescope", "wine", "lutris", "heroic", "retroarch", "unity", "unreal"]) or ("multiplayer" in win_title and "third-party" in win_title)
        if is_game:
            continue

        diffs_col = cv2.absdiff(win_sub[:, 1:], win_sub[:, :-1])
        col_frac = np.mean(diffs_col >= 3, axis=0)
        splits = [idx + 1 for idx, frac in enumerate(col_frac) if frac >= 0.40]

        merged_splits = []
        for s in splits:
            if not merged_splits or (s - merged_splits[-1]) > 8:
                merged_splits.append(s)

        left_edge = 0
        right_edge = ww
        inner_splits = []
        for s in merged_splits:
            if s < 36:
                left_edge = s
            elif s > ww - 36:
                right_edge = s
            else:
                inner_splits.append(s)

        col_bounds = [left_edge] + inner_splits + [right_edge]
        if len(col_bounds) > 2:
            for k in range(len(col_bounds) - 1):
                cx1 = col_bounds[k]
                cx2 = col_bounds[k + 1]
                cw = cx2 - cx1
                if cw >= 40:
                    sub_col = win_sub[:, cx1:cx2]
                    diffs_row = cv2.absdiff(sub_col[1:, :], sub_col[:-1, :])
                    row_frac = np.mean(diffs_row >= 3, axis=1)
                    row_splits = [idx + 1 for idx, frac in enumerate(row_frac) if frac >= 0.40]

                    merged_row_splits = []
                    for rs in row_splits:
                        if not merged_row_splits or (rs - merged_row_splits[-1]) > 8:
                            merged_row_splits.append(rs)

                    top_edge = 0
                    bottom_edge = wh
                    inner_rows = []
                    for rs in merged_row_splits:
                        if rs < 36:
                            top_edge = rs
                        elif rs > wh - 36:
                            bottom_edge = rs
                        else:
                            inner_rows.append(rs)

                    row_bounds = [top_edge] + inner_rows + [bottom_edge]
                    # Full column panel
                    content_boxes.append({
                        "x": int(wx + cx1),
                        "y": int(wy + top_edge),
                        "w": int(cw),
                        "h": int(bottom_edge - top_edge),
                        "area": int(cw * (bottom_edge - top_edge)),
                        "extent": 1.0,
                        "contrast": 28.0,
                        "type": "panel",
                        "title": win.get("title", ""),
                        "class": win.get("class", "")
                    })

                    # Sub-panels within column (if any internal horizontal dividers)
                    if len(row_bounds) > 2:
                        for rk in range(len(row_bounds) - 1):
                            ry1 = row_bounds[rk]
                            ry2 = row_bounds[rk + 1]
                            rh = ry2 - ry1
                            if rh >= 24 and rh != (bottom_edge - top_edge):
                                content_boxes.append({
                                    "x": int(wx + cx1),
                                    "y": int(wy + ry1),
                                    "w": int(cw),
                                    "h": int(rh),
                                    "area": int(cw * rh),
                                    "extent": 1.0,
                                    "contrast": 30.0,
                                    "type": "input" if (24 <= rh <= 80 and ry2 >= wh - 100) else "panel",
                                    "title": win.get("title", ""),
                                    "class": win.get("class", "")
                                })

    return content_boxes

def _make_text_block(lines):
    px = min(l['x'] for l in lines)
    py = min(l['y'] for l in lines)
    pw = max(l['x'] + l['w'] for l in lines) - px
    ph = max(l['y'] + l['h'] for l in lines) - py
    return {
        'x': int(px),
        'y': int(py),
        'w': int(pw),
        'h': int(ph),
        'area': int(pw * ph),
        'extent': 0.96,
        'contrast': 35.0,
        'type': 'text_block'
    }


def cluster_text_paragraphs(text_lines, min_lines=2, multi_column=True):
    """Clusters vertically adjacent text lines into column-aware paragraph bounding boxes."""
    if len(text_lines) < min_lines:
        return []

    sorted_lines = sorted(text_lines, key=lambda b: (b['y'], b['x']))
    if not multi_column:
        paragraphs = []
        current_para = [sorted_lines[0]]
        for line in sorted_lines[1:]:
            last = current_para[-1]
            vgap = line['y'] - (last['y'] + last['h'])
            max_vgap = max(18, min(26, int(last['h'] * 1.35)))
            overlap_w = min(last['x'] + last['w'], line['x'] + line['w']) - max(last['x'], line['x'])
            aligned = (overlap_w > 0) or (abs(line['x'] - last['x']) <= 36)
            if -6 <= vgap <= max_vgap and aligned:
                current_para.append(line)
            else:
                if len(current_para) >= min_lines:
                    paragraphs.append(_make_text_block(current_para))
                current_para = [line]
        if len(current_para) >= min_lines:
            paragraphs.append(_make_text_block(current_para))
        return paragraphs

    # Group lines into independent horizontal column tracks before vertical termination
    active_cols = []
    finished = []
    for line in sorted_lines:
        lx1 = line['x']
        lx2 = lx1 + line['w']
        ly = line['y']
        best_idx = -1
        best_vgap = 10**9
        still_active = []

        for col in active_cols:
            last = col[-1]
            vgap = ly - (last['y'] + last['h'])
            max_vgap = max(18, min(26, int(last['h'] * 1.35)))
            if vgap > max_vgap:
                if len(col) >= min_lines:
                    finished.append(col)
                continue
            still_active.append(col)

        active_cols = still_active
        for idx, col in enumerate(active_cols):
            last = col[-1]
            vgap = ly - (last['y'] + last['h'])
            if vgap < -6:
                continue
            cx1 = min(l['x'] for l in col)
            cx2 = max(l['x'] + l['w'] for l in col)
            cw = cx2 - cx1
            overlap_w = min(cx2, lx2) - max(cx1, lx1)
            min_w = max(1, min(cw, line['w']))
            max_w = max(cw, line['w'])
            width_ok = (max_w <= 2.8 * min_w) or (abs(lx1 - cx1) <= 28)
            horiz_ok = (overlap_w >= min_w * 0.22) or (abs(lx1 - cx1) <= 36)
            if width_ok and horiz_ok and vgap < best_vgap:
                best_vgap = vgap
                best_idx = idx

        if best_idx >= 0:
            active_cols[best_idx].append(line)
        else:
            active_cols.append([line])

    for col in active_cols:
        if len(col) >= min_lines:
            finished.append(col)

    return [_make_text_block(col) for col in finished]


def _sat_has_std(gray, sat, sqsat, x, y, w, h, min_std=6.0):
    """Checks std(gray[y:y+h, x:x+w]) >= min_std using integral images when available."""
    if sat is not None and sqsat is not None:
        area = w * h
        if area <= 0:
            return False
        s1 = float(sat[y + h, x + w] - sat[y, x + w] - sat[y + h, x] + sat[y, x])
        s2 = float(sqsat[y + h, x + w] - sqsat[y, x + w] - sqsat[y + h, x] + sqsat[y, x])
        mean = s1 / area
        var = (s2 / area) - (mean * mean)
        return var >= (min_std * min_std)
    roi = gray[y:y+h, x:x+w]
    return bool(roi.size and float(np.std(roi)) >= min_std)


def _merge_collinear_text_words(lines):
    """Joins adjacent horizontal fragments of large headlines on the same baseline row."""
    if len(lines) < 2:
        return lines
    ordered = sorted(lines, key=lambda b: (b['y'], b['x']))
    merged = []
    for box in ordered:
        joined = False
        if box['h'] >= 24:
            by1, by2 = box['y'], box['y'] + box['h']
            for prev in reversed(merged[-6:]):
                py1, py2 = prev['y'], prev['y'] + prev['h']
                v_overlap = min(by2, py2) - max(by1, py1)
                min_h = min(box['h'], prev['h'])
                if min_h >= 24 and v_overlap >= min_h * 0.55:
                    gap = box['x'] - (prev['x'] + prev['w'])
                    max_gap = max(18, int(min_h * 0.65))
                    if -4 <= gap <= max_gap:
                        nx = min(prev['x'], box['x'])
                        ny = min(prev['y'], box['y'])
                        nx2 = max(prev['x'] + prev['w'], box['x'] + box['w'])
                        ny2 = max(prev['y'] + prev['h'], box['y'] + box['h'])
                        prev['x'], prev['y'] = nx, ny
                        prev['w'], prev['h'] = nx2 - nx, ny2 - ny
                        prev['area'] = prev['w'] * prev['h']
                        joined = True
                        break
        if not joined:
            merged.append(box)
    return merged


def detect_text_regions(gray, orig_w, orig_h, sat=None, sqsat=None, clahe_gray=None, detection_cfg=None):
    """
    Detects text lines, code blocks, display headers, and multi-column paragraphs.
    Fuses Otsu with local contrast-enhanced gradients so dim text isn't suppressed
    by bright headlines on the same screen.
    """
    dcfg = detection_cfg if isinstance(detection_cfg, dict) else {}
    adaptive_text = bool(dcfg.get("adaptiveTextThreshold", True))
    filter_icons = bool(dcfg.get("filterIconsFromText", True))
    multi_col = bool(dcfg.get("multiColumnParagraphs", True))
    max_header_h = int(dcfg.get("maxHeaderHeight", 96) or 96)

    grad_x = cv2.convertScaleAbs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    k_line = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
    closed_line = cv2.morphologyEx(grad_x, cv2.MORPH_CLOSE, k_line)
    _, thresh_line = cv2.threshold(closed_line, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    min_std = 6.0
    if adaptive_text:
        if clahe_gray is None:
            clahe_gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
        grad_cl = cv2.convertScaleAbs(cv2.Sobel(clahe_gray, cv2.CV_32F, 1, 0, ksize=3))
        closed_cl = cv2.morphologyEx(grad_cl, cv2.MORPH_CLOSE, k_line)
        _, thresh_cl = cv2.threshold(closed_cl, 48, 255, cv2.THRESH_BINARY)
        thresh_line = cv2.bitwise_or(thresh_line, thresh_cl)
        min_std = 4.5

    contours_line, _ = cv2.findContours(thresh_line, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    raw_lines = []

    for cnt in contours_line:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 18 or h < 8 or h > max_header_h:
            continue
        if _sat_has_std(gray, sat, sqsat, x, y, w, h, min_std):
            raw_lines.append({
                'x': int(x),
                'y': int(y),
                'w': int(w),
                'h': int(h),
                'area': int(w * h),
                'extent': 0.95,
                'contrast': 30.0,
                'type': 'text'
            })

    text_boxes = _merge_collinear_text_words(raw_lines)
    if filter_icons:
        text_boxes = [
            b for b in text_boxes
            if not (b['w'] <= 56 and b['h'] >= 22 and (b['w'] / float(b['h'])) < 1.55)
        ]

    # Synthesize multi-line paragraph blocks from detected text lines
    para_boxes = [
        p for p in cluster_text_paragraphs(text_boxes, multi_column=multi_col)
        if not (p['w'] >= orig_w * 0.85 and p['h'] >= orig_h * 0.65)
        and not (filter_icons and (p['w'] < 48 or (p['w'] / float(p['h'])) < 0.80))
    ]
    text_boxes.extend(para_boxes)

    # 3. Morphological closing on the line mask to capture dense code/text blocks
    k_para_h = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 1))
    closed_h = cv2.morphologyEx(thresh_line, cv2.MORPH_CLOSE, k_para_h)
    k_para_v = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 14))
    closed_para = cv2.morphologyEx(closed_h, cv2.MORPH_CLOSE, k_para_v)
    contours_para, _ = cv2.findContours(closed_para, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours_para:
        x, y, w, h = cv2.boundingRect(cnt)
        if w >= orig_w * 0.85 and h >= orig_h * 0.65:
            continue
        if filter_icons and (w < 48 or (w / float(h)) < 0.80):
            continue
        # Skip single-line display header already captured as 'text'
        is_single_line = any(
            abs(t['x'] - x) <= 6 and abs(t['y'] - y) <= 6 and abs(t['w'] - w) <= 10 and abs(t['h'] - h) <= 10
            for t in text_boxes if t['type'] == 'text'
        )
        if is_single_line:
            continue
        if w >= 36 and h >= 26 and (w * h) >= 1000:
            if _sat_has_std(gray, sat, sqsat, x, y, w, h, min_std):
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

def _resolve_active_preset(cfg, preset_key=None):
    if preset_key:
        return str(preset_key)
    env_preset = os.environ.get("SMARTSHOT_PRESET", "").strip()
    if env_preset:
        return env_preset
    app_cls = os.environ.get("SMARTSHOT_ACTIVE_CLASS", "").strip().lower()
    if app_cls and isinstance(cfg.get("appRules"), dict):
        for rule, target in cfg["appRules"].items():
            if rule.lower() in app_cls:
                return str(target)
    return str(cfg.get("activePreset", "default") or "default")


def detect_ui_elements(image_path, clients_path=None, min_area=None, max_area_ratio=None, config=None, preset_key=None):
    start_time = time.time()

    if config is not None:
        cfg = config
    elif os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("SMARTSHOT_CONFIG"):
        from config_loader import DEFAULT_CONFIG
        cfg = DEFAULT_CONFIG
    else:
        cfg = load_config()

    det_cfg = cfg.get("detection", {}) if isinstance(cfg, dict) else {}
    if min_area is None:
        min_area = int(det_cfg.get("minArea", 64) or 64)
    if max_area_ratio is None:
        max_area_ratio = float(det_cfg.get("maxAreaRatio", 0.98) or 0.98)
    tiny_contrast_min = float(det_cfg.get("tinyContrastMin", 4.5) or 4.5)
    enable_panels = bool(det_cfg.get("enablePanels", True))
    enable_grids = bool(det_cfg.get("enableGrids", True))
    enable_win_content = bool(det_cfg.get("enableWindowContent", True))
    enable_text = bool(det_cfg.get("enableText", True))
    effective_preset = _resolve_active_preset(cfg, preset_key=preset_key)

    img = cv2.imread(image_path)
    if img is None:
        return {"error": f"Failed to load image: {image_path}", "boxes": []}

    orig_h, orig_w = img.shape[:2]
    total_area = orig_w * orig_h
    max_area = total_area * max_area_ratio

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sat, sqsat = cv2.integral2(gray)

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

    # Integral image over sharp closed edges enables O(1) perimeter & interior density checks
    edge_sat = cv2.integral((closed_edges > 0).astype(np.uint8))

    # 4. Large-scale morphological closing kept separate so blurry blobs only form panels, never tiny slots/buttons
    k_panel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
    k_grad = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed_filtered = cv2.morphologyEx(filtered, cv2.MORPH_CLOSE, k_panel)
    panel_grad_f = cv2.morphologyEx(closed_filtered, cv2.MORPH_GRADIENT, k_grad)
    _, panel_edges_f = cv2.threshold(panel_grad_f, 8, 255, cv2.THRESH_BINARY)

    closed_gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, k_panel)
    panel_grad_g = cv2.morphologyEx(closed_gray, cv2.MORPH_GRADIENT, k_grad)
    _, panel_edges_g = cv2.threshold(panel_grad_g, 12, 255, cv2.THRESH_BINARY)

    panel_mask = cv2.bitwise_or(panel_edges_f, panel_edges_g)

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
                                    is_layer = bool(c.get("is_layer", False))
                                    win_class = str(c.get("class", "") or "")
                                    cls_low = win_class.lower()
                                    # Skip fullscreen transparent overlays (e.g. BongoCat, drawers backdrop) that mask real windows below
                                    if ("bongocat" in cls_low or
                                            cls_low in ("caelestia-drawers", "caelestia-background", "caelestia-border-exclusion", "awww-daemon") or
                                            (is_fl and is_pinned and clamped_w >= orig_w * 0.92 and clamped_h >= orig_h * 0.92)):
                                        continue
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
                                        "is_layer": is_layer,
                                        "focusHistoryID": c.get("focusHistoryID", 999),
                                        "title": c.get("title", ""),
                                        "class": win_class,
                                        "is_client": True
                                    }
                                    raw_boxes.append(win_obj)
                                    client_boxes.append(win_obj)
        except Exception:
            pass

    # 5. Find contours separately on sharp UI borders and blurred panel morphs
    mask_passes = ((False, closed_edges), (True, panel_mask)) if enable_panels else ((False, closed_edges),)
    for is_panel_morph, mask in mask_passes:
        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if is_panel_morph:
                if w < 120 or h < 50:
                    continue
            elif w < 12 or h < 12:
                continue

            box_area = w * h
            if box_area < min_area or box_area > max_area:
                continue

            # Filter out extreme 1-4px line dividers
            if (h <= 4 and w > 40) or (w <= 4 and h > 40):
                continue

            area = cv2.contourArea(cnt)
            extent = float(area) / box_area
            # Allow ornate/curved game panels down to 0.38 extent if substantial in size
            min_extent = 0.38 if (w >= 160 and h >= 50) else (0.42 if box_area < 450 else 0.48)
            if extent < min_extent:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            nv = len(approx)
            # Support ornate fantasy frames, beveled corner UI, and game HUD contours with up to 28 vertices
            max_vertices = 24 if box_area < 500 else 28
            if nv > max_vertices:
                continue

            is_big_panel = (w >= 220 and h >= 140)
            avg_edge = None
            in_ed = None
            if not is_panel_morph and not is_big_panel:
                if nv < 4:
                    continue
                t = _sat_mean(edge_sat, x, y, x + w, min(y + h, y + 2))
                b = _sat_mean(edge_sat, x, max(y, y + h - 2), x + w, y + h)
                l = _sat_mean(edge_sat, x, y, min(x + w, x + 2), y + h)
                r = _sat_mean(edge_sat, max(x, x + w - 2), y, x + w, y + h)
                sides = sorted((t, b, l, r))
                avg_edge = (t + b + l + r) * 0.25
                in_ed = _sat_mean(edge_sat, x + 3, y + 3, x + w - 3, y + h - 3) if (w > 8 and h > 8) else 0.0
                # Keep rounded icons/items with continuous halo & clean interior while dropping open text noise
                is_clean_rounded = (sides[0] >= 0.25 and avg_edge >= 0.32 and in_ed <= 0.20 and extent >= 0.60)
                if not is_clean_rounded:
                    if sides[0] < 0.22 and sides[1] < 0.38:
                        continue
                    if avg_edge < 0.42:
                        continue
                if w < 120 and h < 48 and in_ed > 0.60:
                    continue

            valid, contrast = is_valid_border(gray, x, y, w, h, sat=sat)
            if not valid:
                continue
            if not is_panel_morph and w < 48 and h < 48 and contrast < tiny_contrast_min:
                continue

            if is_panel_morph:
                elem_type = "panel" if is_big_panel else "detected"
            else:
                elem_type = "detected"
                if is_big_panel:
                    elem_type = "panel"
                elif 10 <= w <= 180 and 10 <= h <= 180 and 0.65 <= (w / h) <= 1.54:
                    elem_type = "slot"
                elif 20 <= w <= 800 and 12 <= h <= 64:
                    elem_type = "input" if w > 260 else "button"

            box_entry = {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "area": int(box_area),
                "extent": round(extent, 2),
                "contrast": round(contrast, 1),
                "type": elem_type
            }
            if avg_edge is not None:
                box_entry["edge_score"] = round(avg_edge, 3)
            if in_ed is not None:
                box_entry["interior_edge"] = round(in_ed, 3)
            raw_boxes.append(box_entry)

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
    slots_only = [s for s in deduped_raw if s.get('type') == 'slot']
    if slots_only:
        for b in deduped_raw:
            bx1 = b['x']
            by1 = b['y']
            bx2 = bx1 + b['w']
            by2 = by1 + b['h']
            thresh_area = b['area'] * 1.3
            for s in slots_only:
                if s is not b and s['area'] > thresh_area:
                    if (bx1 >= s['x'] - 2 and by1 >= s['y'] - 2 and
                            bx2 <= s['x'] + s['w'] + 2 and
                            by2 <= s['y'] + s['h'] + 2):
                        b['type'] = 'item'
                        break

    # 3. Synthesize inventory rows and grid containers from clean slots
    synthesized = cluster_slots_and_grids(deduped_raw) if enable_grids else []

    # 3b. Synthesize composite panels / columns into unified parent containers (web page body / split panels)
    column_unions = cluster_adjacent_columns(deduped_raw) if enable_panels else []

    # 3c. Detect window content viewports (web page body below browser header)
    window_content_areas = detect_window_content_areas(gray, client_boxes) if enable_win_content else []

    # 3d. Detect text lines, code snippets, labels, and paragraph blocks
    text_regions = (
        detect_text_regions(gray, orig_w, orig_h, sat=sat, sqsat=sqsat, clahe_gray=cl, detection_cfg=det_cfg)
        if enable_text else []
    )

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

    # Apply heuristic + adaptive rating system and confidence floor
    profile_arg = None
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("SMARTSHOT_RATING_PROFILE"):
        profile_arg = "__pytest_isolated__"
    rated_boxes = rate_and_filter_boxes(
        clamped_boxes,
        active_preset=effective_preset,
        config=cfg,
        profile_path=profile_arg,
    )

    # Semantic hierarchy depth calculation
    boxes_asc = sorted(rated_boxes, key=lambda b: b["area"])
    n_boxes = len(boxes_asc)
    for i, box in enumerate(boxes_asc):
        box["id"] = i
        bx1 = box["x"]
        by1 = box["y"]
        bx2 = bx1 + box["w"]
        by2 = by1 + box["h"]
        min_parent_area = box["area"] * 1.05
        depth = 0
        for j in range(i + 1, n_boxes):
            p = boxes_asc[j]
            if (p["area"] > min_parent_area and
                    bx1 >= p["x"] - 4 and by1 >= p["y"] - 4 and
                    bx2 <= p["x"] + p["w"] + 4 and
                    by2 <= p["y"] + p["h"] + 4):
                depth += 1
        box["depth"] = depth

    final_boxes = sorted(boxes_asc, key=lambda b: b["area"], reverse=True)
    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    return {
        "screen_width": orig_w,
        "screen_height": orig_h,
        "preset": effective_preset,
        "count": len(final_boxes),
        "elapsed_ms": elapsed_ms,
        "boxes": final_boxes
    }

def main():
    parser = argparse.ArgumentParser(description="HyprSmartShot UI Detector")
    parser.add_argument("image_path", help="Path to captured screen image")
    parser.add_argument("output_path", nargs="?", default=None, help="Output JSON path")
    parser.add_argument("clients_path", nargs="?", default=None, help="Hyprland clients JSON path")
    parser.add_argument("--preset", default=None, help="Override preset key for rating/detection")
    parser.add_argument("--config", default=None, help="Explicit config JSON path")
    args = parser.parse_args()

    cfg = load_config(args.config) if args.config else None
    result = detect_ui_elements(
        args.image_path,
        clients_path=args.clients_path,
        config=cfg,
        preset_key=args.preset,
    )
    output_json = json.dumps(result, indent=None)

    if args.output_path:
        temp_path = f"{args.output_path}.tmp.{os.getpid()}"
        try:
            with open(temp_path, "w") as f:
                f.write(output_json)
            os.replace(temp_path, args.output_path)
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
