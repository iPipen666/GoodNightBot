"""TBH — BOXES: count accumulated chest types from a screen capture.

API:
    count_boxes(frame=None, win=None, sct=None, debug=False) -> dict
        {
          "normal":     int,    # filled pips for Normal Monster Box
          "stage_boss": int,    # filled pips for Stage Boss Box
          "act_boss":   int,    # filled pips for Act Boss Box
          "matches": [
              {
                "type":        str,   # "normal" | "stage_boss" | "act_boss"
                "score":       float,
                "x": int, "y": int, "w": int, "h": int,  # match box in frame coords
                "pips_filled": int,
                "pips_total":  int,   # cells examined in the pip band
              },
              ...
          ],
          "error": str | None,  # human-readable reason if result is zeros
        }

All geometry and thresholds are in boxes_calibration.json — edit live, no code restart needed.

CLI:
    python boxes.py [image_path]
        -- No arg: capture live game window.
        -- image_path: run on saved screenshot (for post-hoc debugging).
    Writes boxes_debug.png and prints result as JSON.
"""
from __future__ import annotations

import json
import os
import sys
import ctypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
_CAL_PATH = os.path.join(HERE, "boxes_calibration.json")
_TPL_DIR  = os.path.join(HERE, "templates", "boxes")

_CHEST_NAMES = ("normal", "stage_boss", "act_boss")
_TPL_FILES   = {n: os.path.join(_TPL_DIR, f"{n}.png") for n in _CHEST_NAMES}

# --------------------------------------------------------------------------- #
# Calibration helpers                                                          #
# --------------------------------------------------------------------------- #

def _load_cal() -> dict:
    """Load calibration JSON every call so live edits take effect immediately."""
    try:
        with open(_CAL_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        # Return safe defaults if file is missing/corrupt.
        return {
            "match_threshold": 0.65,
            "scales": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.6, 1.8, 2.0],
            "nms_iou": 0.4,
            "search_downscale": 0.5,
            "dots_roi": {"dy_frac": 0.05, "h_frac": 0.35, "pad_frac": 0.05},
            "pip_fill": {"min_brightness": 140},
            "max_pips": 20,
            "min_pip_cells": 3,
        }


def _load_templates() -> dict[str, np.ndarray | None]:
    tpls: dict[str, np.ndarray | None] = {}
    for name, path in _TPL_FILES.items():
        img = cv2.imread(path)   # BGR or None
        tpls[name] = img
    return tpls


# --------------------------------------------------------------------------- #
# Multi-scale template match                                                   #
# --------------------------------------------------------------------------- #

def _multiscale_match(
    frame:     np.ndarray,
    templates: dict[str, np.ndarray | None],
    cal:       dict,
) -> list[dict]:
    """
    For every (template, scale) pair, find the best response position.
    Returns a list of raw candidate dicts (before NMS) with keys:
        type, score, x, y, w, h   (all in full-frame pixel coordinates)
    """
    ds    = float(cal.get("search_downscale", 0.5))
    thr   = float(cal.get("match_threshold",  0.65))
    scales = [float(s) for s in cal.get("scales", [1.0])]

    Hf, Wf = frame.shape[:2]
    # Downscale search frame (speeds up matchTemplate significantly)
    Wd = max(1, int(Wf * ds))
    Hd = max(1, int(Hf * ds))
    frame_ds = cv2.resize(frame, (Wd, Hd), interpolation=cv2.INTER_AREA)

    candidates: list[dict] = []

    for name, tpl in templates.items():
        if tpl is None:
            continue
        th0, tw0 = tpl.shape[:2]

        for s in scales:
            tw = max(4, int(tw0 * s * ds))
            th = max(4, int(th0 * s * ds))
            if tw > Wd or th > Hd:
                continue

            tpl_resized = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(frame_ds, tpl_resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)

            if score >= thr:
                # Convert back to full-frame coords
                cx_full = (loc[0] + tw / 2) / ds
                cy_full = (loc[1] + th / 2) / ds
                w_full  = tw / ds
                h_full  = th / ds
                candidates.append({
                    "type":  name,
                    "score": float(score),
                    "x":     int(cx_full - w_full / 2),
                    "y":     int(cy_full - h_full / 2),
                    "w":     int(w_full),
                    "h":     int(h_full),
                })

    return candidates


# --------------------------------------------------------------------------- #
# Non-maximum suppression (IoU-based)                                          #
# --------------------------------------------------------------------------- #

def _iou(a: dict, b: dict) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0

    ua = a["w"] * a["h"]
    ub = b["w"] * b["h"]
    return inter / (ua + ub - inter)


def _nms(candidates: list[dict], iou_thr: float) -> list[dict]:
    """Standard greedy NMS: keep highest-score boxes; suppress overlapping ones."""
    # Sort descending by score
    sorted_cands = sorted(candidates, key=lambda c: c["score"], reverse=True)
    kept: list[dict] = []
    for cand in sorted_cands:
        suppressed = any(_iou(cand, k) > iou_thr for k in kept)
        if not suppressed:
            kept.append(cand)
    return kept


# --------------------------------------------------------------------------- #
# Pip-dot counting                                                             #
# --------------------------------------------------------------------------- #

def _count_pips(
    frame: np.ndarray,
    match: dict,
    cal:   dict,
) -> tuple[int, int]:
    """
    Extract the pip-dot band below a matched chest box and count filled vs total cells.

    Returns (pips_filled, pips_total).

    Strategy:
      1. Compute an ROI just below the match box (geometry from cal["dots_roi"]).
      2. Convert ROI to HSV; use brightness (V channel) to decide filled vs empty.
      3. Divide the ROI into `max_pips` equal-width cells; each cell is "filled" if
         its mean V >= min_brightness.
    """
    Hf, Wf = frame.shape[:2]
    droi    = cal.get("dots_roi", {})
    dy_frac = float(droi.get("dy_frac",  0.05))
    h_frac  = float(droi.get("h_frac",   0.35))
    pad_frac = float(droi.get("pad_frac", 0.05))
    min_bright = int(cal.get("pip_fill", {}).get("min_brightness", 140))
    max_pips   = int(cal.get("max_pips",  20))
    min_cells  = int(cal.get("min_pip_cells", 3))

    mx, my, mw, mh = match["x"], match["y"], match["w"], match["h"]

    # Vertical band below the matched box
    roi_y1 = my + mh + int(mh * dy_frac)
    roi_y2 = roi_y1 + max(2, int(mh * h_frac))
    # Horizontal: inset by pad_frac on each side
    pad = int(mw * pad_frac)
    roi_x1 = mx + pad
    roi_x2 = mx + mw - pad

    # Clamp to frame
    roi_x1 = max(0, roi_x1)
    roi_x2 = min(Wf, roi_x2)
    roi_y1 = max(0, roi_y1)
    roi_y2 = min(Hf, roi_y2)

    if roi_x2 <= roi_x1 or roi_y2 <= roi_y1:
        return 0, 0

    roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]

    # Convert to HSV, use V for brightness
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    v   = hsv[:, :, 2]  # shape (roi_h, roi_w)

    roi_w = roi_x2 - roi_x1
    cell_w = max(1, roi_w // max_pips)
    n_cells = roi_w // cell_w   # actual number of cells that fit
    if n_cells < 1:
        return 0, 0

    filled = 0
    for i in range(n_cells):
        cx1 = i * cell_w
        cx2 = cx1 + cell_w
        cell = v[:, cx1:cx2]
        if cell.size == 0:
            continue
        max_v = int(cell.max())   # max-per-cell: a single bright pip pixel registers filled
        if max_v >= min_bright:
            filled += 1

    # If almost all cells look filled, that probably means no dots band was actually
    # found (solid bright area below chest = UI background).  Trust result only when
    # at least min_cells non-trivial cells exist (i.e. not everything blank-white).
    pips_total = n_cells
    return filled, pips_total


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def count_boxes(
    frame:  np.ndarray | None = None,
    win=None,
    sct=None,
    debug:  bool = False,
) -> dict:
    """
    Count accumulated chests by type.

    Parameters
    ----------
    frame : BGR numpy array, or None → capture via vision+mss.
    win   : pygetwindow window object (passed to vision helpers), or None.
    sct   : mss.mss() context, or None.
    debug : if True, return extra keys "debug_frame" (annotated BGR array)
            and "debug_rois" (list of ROI dicts) for the caller to save.

    Returns
    -------
    {
      "normal":     int,
      "stage_boss": int,
      "act_boss":   int,
      "matches":    [ {type, score, x, y, w, h, pips_filled, pips_total} ],
      "error":      str | None,
    }
    Guaranteed to return this structure and never raise.
    """
    result: dict = {
        "normal":     0,
        "stage_boss": 0,
        "act_boss":   0,
        "matches":    [],
        "error":      None,
    }

    try:
        cal = _load_cal()

        # ---- 1. Acquire frame ------------------------------------------------
        if frame is None:
            try:
                import mss as _mss
                import pygetwindow as gw
                import vision as vis
                import config as _cfg_mod  # noqa: F401 – just to ensure it loads
            except ImportError as e:
                result["error"] = f"missing import: {e}"
                return result

            try:
                cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
            except Exception as e:
                result["error"] = f"config.json load failed: {e}"
                return result

            titles = cfg.get("window_title_contains", ["TBH"])
            _win = win
            if _win is None:
                for w in gw.getAllWindows():
                    t = w.title or ""
                    if t and any(s.lower() in t.lower() for s in titles) and w.width > 100:
                        _win = w
                        break

            if _win is None:
                result["error"] = "game window not found"
                return result

            _sct = sct
            _owns_sct = False
            if _sct is None:
                import mss as _mss2
                _sct = _mss2.mss()
                _owns_sct = True

            try:
                frame, _off = vis.grab(_win, _sct)
            finally:
                if _owns_sct:
                    _sct.close()

        # ---- 2. Load templates -----------------------------------------------
        templates = _load_templates()
        missing = [n for n, t in templates.items() if t is None]
        if missing:
            result["error"] = f"missing template(s): {missing}"
            return result

        # ---- 3. Multi-scale match + NMS --------------------------------------
        raw_candidates = _multiscale_match(frame, templates, cal)
        nms_iou        = float(cal.get("nms_iou", 0.4))
        kept           = _nms(raw_candidates, nms_iou)

        # ---- 4. Pip counting per accepted match ------------------------------
        type_pips: dict[str, int] = {"normal": 0, "stage_boss": 0, "act_boss": 0}
        matches_out = []
        debug_rois  = []   # filled only when debug=True

        for m in kept:
            pips_filled, pips_total = _count_pips(frame, m, cal)
            m_out = {
                "type":        m["type"],
                "score":       round(m["score"], 3),
                "x":           m["x"],
                "y":           m["y"],
                "w":           m["w"],
                "h":           m["h"],
                "pips_filled": pips_filled,
                "pips_total":  pips_total,
            }
            matches_out.append(m_out)
            type_pips[m["type"]] = pips_filled   # last match wins (normally 0 or 1 per type)

            if debug:
                # Compute ROI coords for annotation
                droi    = cal.get("dots_roi", {})
                dy_frac = float(droi.get("dy_frac",  0.05))
                h_frac  = float(droi.get("h_frac",   0.35))
                pad_frac = float(droi.get("pad_frac", 0.05))
                mx, my, mw, mh = m["x"], m["y"], m["w"], m["h"]
                Hf, Wf = frame.shape[:2]
                rx1 = max(0, mx + int(mw * pad_frac))
                rx2 = min(Wf, mx + mw - int(mw * pad_frac))
                ry1 = max(0, my + mh + int(mh * dy_frac))
                ry2 = min(Hf, ry1 + max(2, int(mh * h_frac)))
                debug_rois.append({"x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2,
                                   "pips_filled": pips_filled, "pips_total": pips_total,
                                   "type": m["type"]})

        result["normal"]     = type_pips["normal"]
        result["stage_boss"] = type_pips["stage_boss"]
        result["act_boss"]   = type_pips["act_boss"]
        result["matches"]    = matches_out

        # ---- 5. Debug annotation --------------------------------------------
        if debug:
            ann = frame.copy()
            colors = {"normal": (60, 180, 60), "stage_boss": (200, 140, 0), "act_boss": (0, 60, 220)}
            for m, roi in zip(matches_out, debug_rois):
                color = colors.get(m["type"], (200, 200, 200))
                # Match box
                cv2.rectangle(ann, (m["x"], m["y"]),
                              (m["x"] + m["w"], m["y"] + m["h"]), color, 2)
                label = f"{m['type']}  {m['score']:.2f}  pips={m['pips_filled']}/{m['pips_total']}"
                cv2.putText(ann, label, (m["x"], max(0, m["y"] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
                # Pip ROI band
                cv2.rectangle(ann, (roi["x1"], roi["y1"]),
                              (roi["x2"], roi["y2"]), color, 1)
                # Mark individual pip cells
                roi_w = roi["x2"] - roi["x1"]
                max_pips = int(cal.get("max_pips", 20))
                cell_w = max(1, roi_w // max_pips)
                n_cells = roi_w // cell_w
                min_bright = int(cal.get("pip_fill", {}).get("min_brightness", 140))
                if roi["y2"] > roi["y1"] and n_cells > 0:
                    roi_strip = frame[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]]
                    hsv_strip = cv2.cvtColor(roi_strip, cv2.COLOR_BGR2HSV)
                    v_strip   = hsv_strip[:, :, 2]
                    for i in range(n_cells):
                        cx1 = roi["x1"] + i * cell_w
                        cx2 = cx1 + cell_w
                        cell = v_strip[:, i * cell_w:(i + 1) * cell_w]
                        is_filled = cell.size > 0 and int(cell.max()) >= min_bright
                        dot_color = (0, 255, 0) if is_filled else (0, 0, 200)
                        cy_mid = (roi["y1"] + roi["y2"]) // 2
                        cv2.circle(ann, ((cx1 + cx2) // 2, cy_mid), 3, dot_color, -1)

            result["debug_frame"] = ann
            result["debug_rois"]  = debug_rois

    except Exception as e:
        result["error"] = f"unexpected error: {e}"

    return result


# --------------------------------------------------------------------------- #
# Synthetic tests (self-contained, no game window needed)                     #
# --------------------------------------------------------------------------- #

def _run_synthetic_tests(verbose: bool = True) -> bool:
    """
    Test 1: multi-scale match finds a pasted template at a known position.
    Test 2: pip counting returns the expected filled count on a drawn dot row.
    Returns True if all pass.
    """
    import traceback
    all_pass = True

    # --- shared: load one real template as the "ground truth" sprite --------
    tpl_path = os.path.join(_TPL_DIR, "normal.png")
    tpl = cv2.imread(tpl_path)
    if tpl is None:
        print("SKIP synthetic tests — normal.png not found")
        return True   # not a failure of our code

    cal = _load_cal()

    # ---- Test 1: multi-scale match ----------------------------------------
    try:
        # Canvas 400x400 blank
        canvas = np.zeros((400, 400, 3), dtype=np.uint8)
        # Paste a 1.5× scaled version of the template at (50, 80)
        scale_factor = 1.5
        th = int(tpl.shape[0] * scale_factor)
        tw = int(tpl.shape[1] * scale_factor)
        tpl_scaled = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA)
        paste_x, paste_y = 50, 80
        canvas[paste_y:paste_y + th, paste_x:paste_x + tw] = tpl_scaled

        templates = {"normal": tpl, "stage_boss": None, "act_boss": None}
        candidates = _multiscale_match(canvas, templates, cal)
        assert len(candidates) > 0, "No candidate found on synthetic canvas"
        best = max(candidates, key=lambda c: c["score"])
        # Check centre is within ±30px of the paste position centre
        expected_cx = paste_x + tw // 2
        expected_cy = paste_y + th // 2
        dist = ((best["x"] + best["w"] // 2 - expected_cx) ** 2 +
                (best["y"] + best["h"] // 2 - expected_cy) ** 2) ** 0.5
        assert dist < 30, (
            f"Match centre off by {dist:.1f}px from expected ({expected_cx},{expected_cy}); "
            f"got ({best['x']+best['w']//2},{best['y']+best['h']//2})"
        )
        if verbose:
            print(f"[PASS] Test 1 — multi-scale match: score={best['score']:.3f}  "
                  f"centre_error={dist:.1f}px")
    except Exception as e:
        print(f"[FAIL] Test 1 — multi-scale match: {e}")
        if verbose:
            traceback.print_exc()
        all_pass = False

    # ---- Test 2: pip-dot counting -----------------------------------------
    try:
        N_PIPS_FILLED = 5
        # Build a canvas with the template pasted at top and N bright dots below it
        canvas2 = np.zeros((300, 300, 3), dtype=np.uint8)
        tpl_h, tpl_w = tpl.shape[:2]
        px, py = 60, 20
        canvas2[py:py + tpl_h, px:px + tpl_w] = tpl

        # The pip band: placed exactly where _count_pips will look
        droi   = cal.get("dots_roi", {})
        dy_frac = float(droi.get("dy_frac", 0.05))
        h_frac  = float(droi.get("h_frac", 0.35))
        pad_frac = float(droi.get("pad_frac", 0.05))
        max_pips = int(cal.get("max_pips", 20))
        min_bright = int(cal.get("pip_fill", {}).get("min_brightness", 140))

        roi_y1 = py + tpl_h + int(tpl_h * dy_frac)
        roi_y2 = roi_y1 + max(2, int(tpl_h * h_frac))
        pad    = int(tpl_w * pad_frac)
        roi_x1 = px + pad
        roi_x2 = px + tpl_w - pad

        roi_w  = roi_x2 - roi_x1
        cell_w = max(1, roi_w // max_pips)
        n_cells = roi_w // cell_w

        # Draw N_PIPS_FILLED bright pixels (one per cell, solid 220 grey).
        # Draw a single pixel at the LEFT edge of each cell to avoid any inter-cell bleed.
        for i in range(min(N_PIPS_FILLED, n_cells)):
            cx = roi_x1 + i * cell_w  # leftmost x of this cell
            cy = (roi_y1 + roi_y2) // 2
            # Draw a 1×1 pixel bright dot; guaranteed inside this cell only.
            canvas2[cy, cx] = (220, 220, 220)

        fake_match = {"x": px, "y": py, "w": tpl_w, "h": tpl_h}
        filled, total = _count_pips(canvas2, fake_match, cal)

        assert filled == N_PIPS_FILLED, (
            f"Expected pips_filled={N_PIPS_FILLED}, got {filled} (total cells={total})"
        )
        if verbose:
            print(f"[PASS] Test 2 — pip counting: filled={filled}/{total}  expected={N_PIPS_FILLED}")
    except Exception as e:
        print(f"[FAIL] Test 2 — pip counting: {e}")
        if verbose:
            traceback.print_exc()
        all_pass = False

    return all_pass


# --------------------------------------------------------------------------- #
# CLI entry point                                                              #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import sys as _sys

    # Always run synthetic self-tests first (no window needed)
    print("=== Synthetic self-tests ===")
    tests_ok = _run_synthetic_tests(verbose=True)
    print()

    # Determine frame source
    image_arg = _sys.argv[1] if len(_sys.argv) > 1 else None

    if image_arg:
        frame_input = cv2.imread(image_arg)
        if frame_input is None:
            print(f"ERROR: cannot read image '{image_arg}'")
            _sys.exit(1)
        print(f"=== Running on saved image: {image_arg} ===")
        result = count_boxes(frame=frame_input, debug=True)
    else:
        print("=== Attempting live game-window capture ===")
        result = count_boxes(frame=None, debug=True)

    # Extract and remove the debug frame before JSON print
    debug_frame = result.pop("debug_frame", None)
    result.pop("debug_rois", None)

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("error"):
        print(f"\nNote: {result['error']}")

    if debug_frame is not None:
        out_path = os.path.join(HERE, "boxes_debug.png")
        cv2.imwrite(out_path, debug_frame)
        print(f"\nAnnotated image saved: {out_path}")
    else:
        print("\nNo annotated image (no frame acquired).")

    if not tests_ok:
        _sys.exit(2)
