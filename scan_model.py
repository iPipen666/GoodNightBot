"""scan_model.py — structured grade-sorted snapshot of inventory / stash / heroes.

Singleton in-memory model + JSON persistence.  Feed for future HERO/STASH/INVENTORY
UI tabs in control.py.  Reuses existing scan infrastructure (farm, items, inv_probe)
without modifying any of those modules.

Public API
----------
refresh(sct, deep=True)  — live scan: inventory + stash tabs + heroes.
                           Every step guarded; never raises out.
get_inventory()          → list[SlotDict] sorted high→low grade
get_stash()              → dict[int, list[SlotDict]] per tab, sorted high→low
get_heroes()             → list[HeroDict]
get_meta()               → MetaDict {stage, ts, inv_filled, stash_filled}
set_stage(label)         — store current stage label in meta (called from logwatch)

Types
-----
SlotDict  = {row, col, filled, name, grade, grade_tier, level, type, accessory}
HeroDict  = {name, level, class_name}   (placeholder; hero-panel OCR not yet wired)
MetaDict  = {stage, ts, inv_filled, stash_filled, deep}

Persistence
-----------
scan_snapshot.json  — written by refresh(); loaded by getters when memory is empty.
"""

import json
import os
import time
import traceback

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_PATH = os.path.join(HERE, "scan_snapshot.json")

# ---------------------------------------------------------------------------
# Grade ordering — pulled from items.RANK_TIERS (low→high index 0..9).
# We import lazily inside functions so that import scan_model succeeds even
# when Tesseract / mss are absent (headless / no-game scenario).
# ---------------------------------------------------------------------------
_GRADE_ORDER = [
    "обычный", "необычный", "редкий", "легендарный", "бессмертный",
    "аркана", "запредельный", "celestial", "божественный", "космический",
]
# map grade_ru → tier (0..9); anything unknown → -1
_GRADE_TIER: dict[str, int] = {g: i for i, g in enumerate(_GRADE_ORDER)}

# English probe aliases used by inv_probe / farm (colour-based rank names)
_PROBE_TO_RU: dict[str, str] = {
    "common":     "обычный",
    "uncommon":   "необычный",
    "rare":       "редкий",
    "legendary":  "легендарный",
    "epic":       "аркана",
    "red":        "бессмертный",   # best approximation for colour-probe "red" tier
}


def _grade_tier(grade: str | None) -> int:
    """Return tier index (0..9) for a grade string (ru or en probe key). -1 if unknown."""
    if not grade:
        return -1
    g = grade.lower().strip()
    if g in _GRADE_TIER:
        return _GRADE_TIER[g]
    ru = _PROBE_TO_RU.get(g)
    if ru:
        return _GRADE_TIER.get(ru, -1)
    # substring match for partial OCR reads
    for canon, idx in _GRADE_TIER.items():
        if g in canon or canon in g:
            return idx
    return -1


def _to_ru_grade(raw: str | None) -> str | None:
    """Normalise probe/OCR grade to canonical Russian grade string or None."""
    if not raw:
        return None
    g = raw.lower().strip()
    if g in _GRADE_TIER:
        return g
    ru = _PROBE_TO_RU.get(g)
    if ru:
        return ru
    for canon in _GRADE_TIER:
        if g in canon or canon in g:
            return canon
    return raw  # pass through as-is


def _sort_slots(slots: list) -> list:
    """Sort slot list high-grade first (tier desc), then row/col asc."""
    return sorted(slots, key=lambda s: (-_grade_tier(s.get("grade")),
                                        s.get("row", 0), s.get("col", 0)))


# ---------------------------------------------------------------------------
# In-memory model (module-level singletons)
# ---------------------------------------------------------------------------
_INVENTORY: list = []          # list[SlotDict]
_STASH: dict = {}              # {tab_no: list[SlotDict]}
_HEROES: list = []             # list[HeroDict]
_META: dict = {
    "stage": "",
    "ts": 0.0,
    "inv_filled": 0,
    "stash_filled": {},
    "deep": False,
}
_LOADED = False   # True once snapshot was loaded/refreshed at least once


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _save_snapshot():
    """Persist current model to scan_snapshot.json (best-effort)."""
    try:
        data = {
            "inventory": _INVENTORY,
            "stash": {str(k): v for k, v in _STASH.items()},
            "heroes": _HEROES,
            "meta": _META,
        }
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # never raise — persistence is best-effort


def _load_snapshot():
    """Load snapshot from disk into memory (once, idempotent)."""
    global _INVENTORY, _STASH, _HEROES, _META, _LOADED
    if _LOADED:
        return
    _LOADED = True
    if not os.path.exists(SNAPSHOT_PATH):
        return
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _INVENTORY = data.get("inventory", [])
        raw_stash = data.get("stash", {})
        _STASH = {int(k): v for k, v in raw_stash.items()}
        _HEROES = data.get("heroes", [])
        _META.update(data.get("meta", {}))
    except Exception:
        pass  # corrupted snapshot → start fresh


# ---------------------------------------------------------------------------
# Public getters (load snapshot on first call if memory is empty)
# ---------------------------------------------------------------------------

def get_inventory() -> list:
    """Return last known inventory snapshot (list of SlotDict), high-grade first."""
    _load_snapshot()
    return list(_INVENTORY)


def get_stash() -> dict:
    """Return last known stash snapshot: {tab_no: list[SlotDict]}, each sorted high→low."""
    _load_snapshot()
    return {k: list(v) for k, v in _STASH.items()}


def get_heroes() -> list:
    """Return last known heroes list."""
    _load_snapshot()
    return list(_HEROES)


def get_meta() -> dict:
    """Return metadata dict {stage, ts, inv_filled, stash_filled, deep}."""
    _load_snapshot()
    return dict(_META)


def set_stage(label: str):
    """Store current stage label in meta (called externally from logwatch/UI)."""
    _META["stage"] = label


# ---------------------------------------------------------------------------
# refresh() — live scan
# ---------------------------------------------------------------------------

def refresh(sct, deep: bool = True):
    """Populate model from a live screen scan.

    Parameters
    ----------
    sct   : mss.mss() instance (caller keeps it open across multiple calls)
    deep  : if True → tooltip-OCR for rare+ slots (items.read_item).
            if False → frame-colour only (fast, no hover).

    Every step is wrapped in try/except so a partial failure never raises out.
    State is grade-sorted after each section and persisted to scan_snapshot.json.
    """
    global _INVENTORY, _STASH, _HEROES, _META, _LOADED
    _LOADED = True   # suppress _load_snapshot() in getters after a live refresh

    # Lazy imports — only needed when a live game is present.
    try:
        import farm
        import items as _items
        import inv_probe as ip
    except Exception as exc:
        _META["stage"] = f"import-error: {exc}"
        _save_snapshot()
        return

    # ── helpers ────────────────────────────────────────────────────────────

    def _make_slot(row: int, col: int, filled: bool,
                   grade_raw=None, name=None, level=None,
                   item_type=None, accessory=False) -> dict:
        grade_ru = _to_ru_grade(grade_raw)
        return {
            "row": row,
            "col": col,
            "filled": filled,
            "name": name,
            "grade": grade_ru,
            "grade_tier": _grade_tier(grade_ru),
            "level": level,
            "type": item_type,
            "accessory": accessory,
        }

    def _scan_grid_slots(sct, panel, panel_name: str, tl: str, br: str,
                         cols: int, rows: int, do_ocr: bool, flip: str) -> list:
        """Scan one grid: frame-colour pass then optional OCR for filled slots.
        Returns list[SlotDict].  Never raises."""
        slots = []
        try:
            cells = farm.grid_centers(panel, panel_name, tl, br, cols, rows)
        except Exception:
            return slots

        # capture size for brightness/frame test
        s = max(farm.CFG.get("grid_cell_capture_size", 44), 8)
        thr = farm.SLOT_FILL_THR

        # ── pass A: fill + frame colour (no cursor movement) ──────────────
        try:
            import human as _human
            _human.park()
            time.sleep(0.12)
        except Exception:
            pass

        for r, c, x, y in cells:
            try:
                box = {"left": int(x - s / 2), "top": int(y - s / 2),
                       "width": s, "height": s}
                import numpy as np
                img = np.array(sct.grab(box))[:, :, :3]
                brightness = float(img.mean())
                if brightness < thr:
                    slots.append(_make_slot(r, c, False))
                    continue
                # frame-colour grade
                probe_rank = ip.analyze(img).get("rank")
                grade_raw = probe_rank
                slots.append(_make_slot(r, c, True, grade_raw=grade_raw))
            except Exception:
                slots.append(_make_slot(r, c, True))  # safe default: filled, grade unknown

        # ── pass B: OCR tooltip for rare+ filled slots ────────────────────
        if do_ocr:
            try:
                # Estimate OCR-worthy threshold: tier >= 2 (редкий) or unknown (-1)
                ocr_candidates = [
                    (i, cells[i][2], cells[i][3])
                    for i, sl in enumerate(slots)
                    if sl["filled"] and _grade_tier(sl.get("grade")) >= 2
                ]
                # Cap to avoid spending excessive time
                max_ocr = int(farm.CFG.get("policy", {}).get("ocr_drops_max", 8))
                for idx, x, y in ocr_candidates[:max_ocr]:
                    if farm._hardstop():
                        break
                    try:
                        d = _items.read_item(sct, (x, y), flip=flip,
                                             settle=farm.SCAN_SETTLE)
                        if d:
                            sl = slots[idx]
                            sl["name"]      = d.get("name") or sl["name"]
                            sl["grade"]     = _to_ru_grade(d.get("rank")) or sl["grade"]
                            sl["grade_tier"] = _grade_tier(sl["grade"])
                            sl["level"]     = d.get("level_req") or sl["level"]
                            sl["type"]      = d.get("type") or sl["type"]
                            sl["accessory"] = bool(d.get("accessory", sl["accessory"]))
                    except Exception:
                        pass   # OCR miss on one slot → keep frame-colour result
            except Exception:
                pass

        return _sort_slots(slots)

    # ── 1. INVENTORY ────────────────────────────────────────────────────────
    inv_slots: list = []
    try:
        hero = farm.ensure_inventory_tab(sct)
        if hero is None:
            hero = farm.ensure_open(sct, "hero")
        if hero is not None:
            cols = farm.INV["cols"]
            rows = farm.HERO_ROWS
            inv_slots = _scan_grid_slots(
                sct, hero, "hero", "inv_tl", "inv_br",
                cols, rows, do_ocr=deep, flip="left"
            )
    except Exception:
        pass   # HERO panel unavailable — leave inventory empty

    _INVENTORY = inv_slots
    _META["inv_filled"] = sum(1 for s in inv_slots if s["filled"])

    # ── 2. STASH ────────────────────────────────────────────────────────────
    stash_slots: dict = {}
    stash_filled: dict = {}
    try:
        stash_panel = farm.ensure_open(sct, "stash")
        if stash_panel is not None:
            n_tabs = farm.STASH_TABS
            # Phase 1: fast count per tab (no OCR)
            tab_counts: dict = {}
            for tab in range(1, n_tabs + 1):
                if farm._hardstop():
                    break
                try:
                    farm.click_el(stash_panel, "stash", f"tab{tab}",
                                  f"вкладка {tab}", fast=True)
                    farm.isleep(farm.COUNT_SETTLE)
                    n, _ = farm.count_filled(
                        sct, stash_panel, "stash", "grid_tl", "grid_br",
                        7, 6, park=False
                    )
                    tab_counts[tab] = n
                except Exception:
                    tab_counts[tab] = 0

            # Phase 2: grade scan per non-empty tab
            for tab in range(1, n_tabs + 1):
                if farm._hardstop():
                    break
                try:
                    if tab_counts.get(tab, 0) == 0 and deep:
                        stash_slots[tab] = []
                        stash_filled[tab] = 0
                        continue
                    farm.click_el(stash_panel, "stash", f"tab{tab}",
                                  f"вкладка {tab}", fast=True)
                    farm.isleep(0.3)
                    # re-detect after tab switch (panel may shift)
                    _, d = farm.detect(sct)
                    cur_panel = d.get("stash", stash_panel)
                    tab_slots = _scan_grid_slots(
                        sct, cur_panel, "stash", "grid_tl", "grid_br",
                        7, 6, do_ocr=deep, flip="right"
                    )
                    stash_slots[tab] = tab_slots
                    stash_filled[tab] = sum(1 for s in tab_slots if s["filled"])
                except Exception:
                    stash_slots[tab] = []
                    stash_filled[tab] = 0
    except Exception:
        pass   # STASH unavailable — leave stash empty

    _STASH = stash_slots
    _META["stash_filled"] = stash_filled

    # ── 3. HEROES (placeholder — hero-panel roster OCR not implemented yet) ──
    # Future: detect hero panel tab → OCR hero names/levels/classes.
    # For now we emit an empty list so the model shape is stable.
    _HEROES = []

    # ── 4. Finalise meta ────────────────────────────────────────────────────
    _META["ts"] = time.time()
    _META["deep"] = deep

    # ── 5. Persist ──────────────────────────────────────────────────────────
    _save_snapshot()


# ---------------------------------------------------------------------------
# __main__ — print snapshot summary without requiring a live game
# ---------------------------------------------------------------------------

def _summary():
    """Return a human-readable summary string from current (or loaded) model."""
    _load_snapshot()
    ts = _META.get("ts", 0)
    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "—"
    inv_filled = _META.get("inv_filled", sum(1 for s in _INVENTORY if s.get("filled")))
    stash_filled = _META.get("stash_filled", {})
    stage = _META.get("stage") or "—"
    deep = _META.get("deep", False)

    lines = [
        "=== scan_model snapshot ===",
        f"  timestamp : {ts_str}",
        f"  stage     : {stage}",
        f"  deep OCR  : {deep}",
        f"  inventory : {inv_filled} filled / {len(_INVENTORY)} slots",
    ]

    # Grade breakdown for inventory
    inv_grades: dict = {}
    for s in _INVENTORY:
        if s.get("filled"):
            g = s.get("grade") or "неизв"
            inv_grades[g] = inv_grades.get(g, 0) + 1
    if inv_grades:
        breakdown = ", ".join(f"{g}:{n}" for g, n in
                              sorted(inv_grades.items(),
                                     key=lambda kv: -_grade_tier(kv[0])))
        lines.append(f"    grades : {breakdown}")

    # Stash per tab
    if _STASH:
        lines.append(f"  stash tabs: {len(_STASH)}")
        for tab in sorted(_STASH.keys()):
            tab_slots = _STASH[tab]
            filled = sum(1 for s in tab_slots if s.get("filled"))
            lines.append(f"    tab {tab}: {filled} filled / {len(tab_slots)} slots")
    else:
        lines.append("  stash     : (empty or not scanned)")

    lines.append(f"  heroes    : {len(_HEROES)}")
    lines.append("===========================")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    # Make sure stdout uses UTF-8 on Windows consoles
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print(_summary())
