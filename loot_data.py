"""
loot_data.py — Drop-table data for the LOOT UI tab.
stdlib + json + gamedb only; no extra pip deps.

Public API
----------
loot_for_stage(stage_label, locale="en-US") -> list[dict]
    Return all items that drop at stages matching `stage_label` (e.g. "2-9"),
    sorted by grade tier descending then name ascending.  Each element:
        {
            "name":      str,           # localised
            "name_i18n": dict,          # all 16 locales
            "grade":     str,           # e.g. "COMMON"
            "pct":       float | None,  # drop chance from drop table entry
            "source":    str,           # localised box / group name
            "icon":      str,           # local path if sprite downloaded, else wiki path
            "kind":      "item" | "group",
            "id":        int,
        }

stages_index() -> dict[str, dict]
    {label: stage_record} built from gamedb stages.json.

download_sprites(items, dest="templates/sprites") -> int
    Download item icons from the wiki; skip existing.  Returns count downloaded.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

import gamedb

# ---------------------------------------------------------------------------
# Grade ordering (0 = weakest → 9 = strongest)
# ---------------------------------------------------------------------------
_GRADE_ORDER = {
    "COMMON":    0,
    "UNCOMMON":  1,
    "RARE":      2,
    "LEGENDARY": 3,
    "IMMORTAL":  4,
    "ARCANA":    5,
    "BEYOND":    6,
    "CELESTIAL": 7,
    "DIVINE":    8,
    "COSMIC":    9,
}

_HERE = os.path.dirname(os.path.abspath(__file__))
_WIKI_DATA_BOXES = os.path.join(_HERE, "wiki_data", "raw", "data", "boxes")
_WIKI_ITEMS_JSON = os.path.join(_HERE, "wiki_data", "raw", "data", "items.json")

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal caches (lazy-loaded)
# ---------------------------------------------------------------------------
_items_map: dict | None = None        # {item_id_int: item_record}
_stages_idx: dict | None = None       # {label: stage_record}
_box_cache: dict = {}                 # {box_id_int: table entries list}


def _load_items_map() -> dict:
    """Load wiki items.json → {id: record}."""
    global _items_map
    if _items_map is None:
        with open(_WIKI_ITEMS_JSON, encoding="utf-8") as f:
            items = json.load(f)
        _items_map = {item["id"]: item for item in items}
        log.debug("Loaded %d items from wiki items.json", len(_items_map))
    return _items_map


def _load_box_entries(box_id: int) -> list:
    """
    Load wiki_data/raw/data/boxes/<box_id>.json entries.
    Each entry has: type (ITEMGROUP|ITEM), pct, item (or None), group (or None).
    Returns [] if file not found (logs warning).
    """
    if box_id in _box_cache:
        return _box_cache[box_id]
    path = os.path.join(_WIKI_DATA_BOXES, f"{box_id}.json")
    if not os.path.exists(path):
        log.warning("Box file not found: %s (box_id=%d)", path, box_id)
        _box_cache[box_id] = []
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("table", {}).get("entries", [])
    _box_cache[box_id] = entries
    log.debug("Loaded %d entries from box %d", len(entries), box_id)
    return entries


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def stages_index() -> dict:
    """Return {label: stage_record} for quick lookup."""
    global _stages_idx
    if _stages_idx is None:
        _stages_idx = {}
        for s in gamedb.stages():
            lbl = s.get("label")
            if lbl and lbl not in _stages_idx:
                _stages_idx[lbl] = s
    return _stages_idx


def _item_name_i18n(item_record: dict) -> dict:
    """Extract i18n name dict from an item record (wiki items.json shape)."""
    n = item_record.get("name")
    if isinstance(n, dict):
        return n
    return {"en-US": str(n) if n else "?"}


def _item_icon(item_id: int, dest: str) -> str:
    """Return local sprite path if exists, else wiki relative path."""
    items_map = _load_items_map()
    item = items_map.get(item_id, {})
    wiki_icon = item.get("icon", "")
    local_path = os.path.join(dest, f"Item_{item_id}.png")
    if os.path.exists(local_path):
        return local_path
    return wiki_icon


def _resolve_entry(entry: dict, box_name_i18n: dict, items_map: dict,
                   locale: str, pct: float | None) -> list[dict]:
    """
    Convert a single box table entry → list of loot dicts.
    ITEM entries → 1 item.
    ITEMGROUP entries → N items (one per member in group.items[]).
    Unresolved group members (not in items_map) are logged and skipped.
    """
    results = []
    entry_type = entry.get("type")
    if entry_type == "ITEM":
        item_rec = entry.get("item")
        if not item_rec:
            return results
        iid = item_rec.get("id")
        if not isinstance(iid, int):
            return results
        # Prefer full record from items_map for multi-lang names
        full = items_map.get(iid, item_rec)
        name_i18n = _item_name_i18n(full)
        name = name_i18n.get(locale) or name_i18n.get("en-US") or next(iter(name_i18n.values()), "?")
        grade = full.get("grade") or item_rec.get("grade", "COMMON")
        icon = full.get("icon") or item_rec.get("icon", "")
        source = name_i18n.get(locale) or name_i18n.get("en-US") or "?"
        box_src = box_name_i18n.get(locale) or box_name_i18n.get("en-US") or "?"
        results.append({
            "name": name,
            "name_i18n": name_i18n,
            "grade": grade,
            "pct": pct,
            "source": box_src,
            "icon": icon,
            "kind": "item",
            "id": iid,
        })

    elif entry_type == "ITEMGROUP":
        group = entry.get("group")
        if not group:
            return results
        group_id = group.get("id")
        group_name_i18n = group.get("name_i18n") or {}
        group_grade = group.get("grade", "COMMON")
        member_ids = group.get("items") or []
        if not member_ids:
            log.warning("ITEMGROUP %s has no items[] array — unresolved", group_id)
            return results

        box_src = box_name_i18n.get(locale) or box_name_i18n.get("en-US") or "?"
        grp_src = group_name_i18n.get(locale) or group_name_i18n.get("en-US") or f"Group {group_id}"

        for mid in member_ids:
            full = items_map.get(mid)
            if not full:
                log.warning("Group %s member item %d not found in items_map — skipping", group_id, mid)
                continue
            name_i18n = _item_name_i18n(full)
            name = name_i18n.get(locale) or name_i18n.get("en-US") or next(iter(name_i18n.values()), "?")
            grade = full.get("grade") or group_grade
            icon = full.get("icon", "")
            results.append({
                "name": name,
                "name_i18n": name_i18n,
                "grade": grade,
                "pct": pct,     # group's pct — each member shares the group slot
                "source": grp_src,
                "icon": icon,
                "kind": "group",
                "id": mid,
            })
    else:
        log.debug("Unknown entry type %r — skipping", entry_type)

    return results


def loot_for_stage(stage_label: str, locale: str = "en-US") -> list[dict]:
    """
    Return everything that drops at stages matching `stage_label` (e.g. "2-9").
    Includes all difficulty variants (NORMAL, NIGHTMARE, HELL, TORMENT).
    Groups → expanded to member items.  Deduplicated by item id (best pct kept).
    Sorted by grade tier descending, then name ascending.

    Logs a warning for unresolved groups / missing items; never silently drops them.
    """
    items_map = _load_items_map()
    box_index = gamedb.box_index_all()  # {box_id_str: {name_i18n, entries, stages}}

    # Find all box_ids whose stages include this label
    matching_box_ids: list[int] = []
    for bid_str, box_rec in box_index.items():
        stages_list = box_rec.get("stages") or []
        for s in stages_list:
            if s.get("label") == stage_label:
                try:
                    matching_box_ids.append(int(bid_str))
                except ValueError:
                    log.warning("Non-integer box id in box_index: %r", bid_str)
                break

    if not matching_box_ids:
        log.warning("No boxes found for stage %s", stage_label)

    # Collect from boxes (wiki resolution)
    by_id: dict[int, dict] = {}   # {item_id: best loot dict}
    groups_total = 0
    groups_resolved = 0
    groups_unresolved = 0

    def _merge(item_dict: dict) -> None:
        """Add item to by_id; keep entry with higher pct if duplicate."""
        iid = item_dict["id"]
        existing = by_id.get(iid)
        if existing is None:
            by_id[iid] = item_dict
        else:
            # keep higher pct (None < any float)
            ep = existing.get("pct")
            np_ = item_dict.get("pct")
            if ep is None or (np_ is not None and np_ > ep):
                by_id[iid] = item_dict

    for bid in matching_box_ids:
        box_rec = box_index.get(str(bid), {})
        box_name_i18n = box_rec.get("name_i18n") or {"en-US": f"Box {bid}"}

        entries = _load_box_entries(bid)
        for entry in entries:
            pct = entry.get("pct")
            etype = entry.get("type")
            if etype == "ITEMGROUP":
                groups_total += 1
                grp = entry.get("group") or {}
                members = grp.get("items") or []
                if members:
                    groups_resolved += 1
                    results = _resolve_entry(entry, box_name_i18n, items_map, locale, pct)
                    for r in results:
                        _merge(r)
                else:
                    groups_unresolved += 1
                    gid = grp.get("id", "?")
                    log.warning("UNRESOLVED group %s in box %d — no items[] in box file", gid, bid)
            elif etype == "ITEM":
                results = _resolve_entry(entry, box_name_i18n, items_map, locale, pct)
                for r in results:
                    _merge(r)
            # else skip silently via _resolve_entry's debug log

    # Also pull from drop_map (item-level sources) as supplement
    # — drop_map is item-keyed so we can add items that appear via drop_map
    #   but are listed as individual items (not groups) there.
    # Note: boxes/*.json already covers all drops; drop_map is redundant for group members
    # but we add any ITEM-type direct drops that may have been missed.
    drop_map = gamedb.drop_map_all()  # {item_id_str: [{box, boxName, pct, stages}]}
    for iid_str, sources in drop_map.items():
        # skip group-prefixed keys like "group:1002200"
        if iid_str.startswith("group:"):
            continue
        try:
            iid = int(iid_str)
        except ValueError:
            continue
        for src in sources:
            src_stages = src.get("stages") or []
            if not any(s.get("label") == stage_label for s in src_stages):
                continue
            # Item appears in this stage via drop_map
            if iid in by_id:
                continue   # already resolved via boxes
            full = items_map.get(iid)
            if not full:
                log.warning("drop_map item %d not found in wiki items_map — skipping", iid)
                continue
            name_i18n = _item_name_i18n(full)
            name = name_i18n.get(locale) or name_i18n.get("en-US") or next(iter(name_i18n.values()), "?")
            grade = full.get("grade", "COMMON")
            icon = full.get("icon", "")
            box_name = src.get("boxName") or {}
            if isinstance(box_name, dict):
                box_src = box_name.get(locale) or box_name.get("en-US") or "?"
            else:
                box_src = str(box_name)
            _merge({
                "name": name,
                "name_i18n": name_i18n,
                "grade": grade,
                "pct": src.get("pct"),
                "source": box_src,
                "icon": icon,
                "kind": "item",
                "id": iid,
            })

    # Sort: grade tier desc, then name asc
    result_list = sorted(
        by_id.values(),
        key=lambda x: (-_GRADE_ORDER.get(x["grade"], 0), x["name"].lower()),
    )

    log.info(
        "loot_for_stage(%r): %d items, %d boxes, groups total=%d resolved=%d unresolved=%d",
        stage_label, len(result_list), len(matching_box_ids),
        groups_total, groups_resolved, groups_unresolved,
    )
    return result_list


# ---------------------------------------------------------------------------
# Sprite downloader
# ---------------------------------------------------------------------------

_WIKI_BASE = "https://taskbarhero.wiki"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def download_sprites(
    items: list[dict],
    dest: str = "templates/sprites",
    delay: float = 0.2,
) -> int:
    """
    Download wiki sprites for each item in `items` list.
    Each item must have "id" (int) and "icon" (wiki path like /game/items/...).
    Saves to <dest>/Item_<id>.png.  Skips existing files.
    Returns count of newly downloaded files.
    Logs warnings for 404 / network errors (never raises).
    """
    os.makedirs(dest, exist_ok=True)
    items_map = _load_items_map()

    seen_ids: set = set()
    downloaded = 0

    for item in items:
        iid = item.get("id")
        if not isinstance(iid, int) or iid in seen_ids:
            continue
        seen_ids.add(iid)

        out_path = os.path.join(dest, f"Item_{iid}.png")
        if os.path.exists(out_path):
            continue

        # Resolve icon path: prefer full record in items_map
        full = items_map.get(iid, item)
        icon_path = full.get("icon") or item.get("icon", "")
        if not icon_path:
            log.warning("No icon path for item %d — skipping", iid)
            continue

        url = _WIKI_BASE + icon_path
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            # Validate PNG header
            if data[:4] != b"\x89PNG":
                log.warning("Item %d: unexpected content from %s (not PNG, %d bytes)", iid, url, len(data))
                continue
            with open(out_path, "wb") as f:
                f.write(data)
            downloaded += 1
            log.debug("Downloaded %s → %s (%d bytes)", url, out_path, len(data))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log.warning("Item %d: 404 at %s — skipping", iid, url)
            else:
                log.warning("Item %d: HTTP %d at %s — skipping", iid, e.code, url)
        except Exception as e:
            log.warning("Item %d: error downloading %s — %s", iid, url, e)

        time.sleep(delay)

    return downloaded


# ---------------------------------------------------------------------------
# __main__: demo for stage 2-9
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    label = "2-9"
    print(f"\n=== loot_for_stage({label!r}) ===")
    loot = loot_for_stage(label, locale="en-US")
    print(f"Total items: {len(loot)}")

    if not loot:
        print("ERROR: empty result!")
        sys.exit(1)

    print("\nFirst 8 items (grade-sorted):")
    for i, item in enumerate(loot[:8]):
        pct_str = f"{item['pct']:.3f}%" if item["pct"] is not None else "pct=?"
        print(
            f"  {i+1:2d}. [{item['grade']:10s}] {item['name']:<40s} "
            f"{pct_str:>10}  src={item['source']!r}  id={item['id']}"
        )

    # Grade distribution
    from collections import Counter
    grade_counts = Counter(item["grade"] for item in loot)
    print("\nGrade distribution:")
    for grade in reversed(
        sorted(grade_counts.keys(), key=lambda g: _GRADE_ORDER.get(g, 0))
    ):
        print(f"  {grade:10s}: {grade_counts[grade]}")

    # Download sprites
    print(f"\n=== Downloading sprites for {len(loot)} items ===")
    count = download_sprites(loot, dest="templates/sprites")
    print(f"Downloaded: {count} new sprites")

    # Verify a few PNG signatures
    dest = "templates/sprites"
    verified = 0
    for item in loot[:8]:
        path = os.path.join(dest, f"Item_{item['id']}.png")
        if os.path.exists(path):
            with open(path, "rb") as f:
                sig = f.read(4)
            ok = "OK" if sig == b"\x89PNG" else "BAD"
            print(f"  {path}: {ok} ({os.path.getsize(path)} bytes)")
            if ok == "OK":
                verified += 1
    print(f"Verified {verified}/8 PNG signatures.")
