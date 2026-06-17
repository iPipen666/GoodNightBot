"""test_hop_presets.py — библиотека пресетов хопа (community + кастомные + apply). Офлайн, без pytest."""
import os
import sys
import tempfile

import hop_presets as hp
import stagenav


def _tmp():
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd); os.remove(path)
    return path


# ── community ────────────────────────────────────────────────────────────────
def t_community_nonempty_and_valid():
    com = hp.community()
    assert len(com) >= 3, com
    for p in com:
        assert p["name"] and p["kind"] in ("strategy", "route"), p
        assert p.get("description"), p


def t_community_is_copy():
    hp.community()[0]["name"] = "MUTATED"
    assert hp.COMMUNITY[0]["name"] != "MUTATED", "community() must return copies"


# ── кастомная CRUD ─────────────────────────────────────────────────────────────
def t_user_add_load_roundtrip():
    path = _tmp()
    stops = [{"label": "1-1-3", "dwell_sec": 120}, {"label": "2-1-4", "dwell_sec": 180}]
    ok, _ = hp.add_user("My night map", stops, path=path)
    assert ok
    loaded = hp.load_user(path)
    assert len(loaded) == 1 and loaded[0]["name"] == "My night map", loaded
    assert loaded[0]["stops"] == stops, loaded
    os.remove(path)


def t_user_add_rejects_reserved_and_empty():
    path = _tmp()
    ok, msg = hp.add_user("Level-window circuit", [{"label": "1-1-1", "dwell_sec": 60}], path=path)
    assert not ok and "built-in" in msg, msg
    ok, msg = hp.add_user("", [{"label": "1-1-1", "dwell_sec": 60}], path=path)
    assert not ok, msg
    ok, msg = hp.add_user("Empty", [], path=path)
    assert not ok and "empty" in msg, msg
    assert hp.load_user(path) == []


def t_user_add_overwrites_same_name():
    path = _tmp()
    hp.add_user("dup", [{"label": "1-1-1", "dwell_sec": 60}], path=path)
    hp.add_user("dup", [{"label": "2-2-2", "dwell_sec": 90}], path=path)
    loaded = hp.load_user(path)
    assert len(loaded) == 1 and loaded[0]["stops"][0]["label"] == "2-2-2", loaded
    os.remove(path)


def t_user_delete():
    path = _tmp()
    hp.add_user("a", [{"label": "1-1-1", "dwell_sec": 60}], path=path)
    hp.add_user("b", [{"label": "1-1-2", "dwell_sec": 60}], path=path)
    ok, _ = hp.delete_user("a", path=path)
    assert ok and [p["name"] for p in hp.load_user(path)] == ["b"]
    ok, msg = hp.delete_user("nope", path=path)
    assert not ok and "no custom" in msg, msg
    ok, msg = hp.delete_user("Safe (at-level only)", path=path)
    assert not ok and "built-in" in msg, msg
    os.remove(path)


def t_load_missing_file_is_empty():
    assert hp.load_user(_tmp() + "_does_not_exist") == []


# ── get / all ────────────────────────────────────────────────────────────────
def t_get_community_and_unknown():
    assert hp.get("Level-window circuit")["kind"] == "strategy"
    assert hp.get("totally unknown preset", path=_tmp()) is None


def t_all_presets_marks_builtin():
    path = _tmp()
    hp.add_user("mine", [{"label": "1-1-1", "dwell_sec": 60}], path=path)
    allp = hp.all_presets(path=path)
    builtin = [p for p in allp if p["builtin"]]
    custom = [p for p in allp if not p["builtin"]]
    assert len(builtin) == len(hp.COMMUNITY) and len(custom) == 1, allp
    assert custom[0]["name"] == "mine"
    os.remove(path)


# ── apply (чистый патч) ────────────────────────────────────────────────────────
def t_apply_strategy_patch():
    patch = hp.apply(hp.get("Safe (at-level only)"), hero_level=50)
    assert patch["mode"] == "strategy" and patch["max_ahead"] == 0, patch
    assert "route_stops" not in patch, patch


def t_apply_strategy_needs_difficulty_warns():
    patch = hp.apply(hp.get("Single-difficulty sweep"), hero_level=50, difficulty=None)
    assert patch["mode"] == "strategy" and patch.get("warn"), patch
    patch2 = hp.apply(hp.get("Single-difficulty sweep"), hero_level=50, difficulty="HELL")
    assert "warn" not in patch2, patch2


def t_apply_route_generate_within_level_window():
    # Auto timed circuit генерит маршрут, все этапы — в окне уровня (≤ hero+max_ahead)
    patch = hp.apply(hp.get("Auto timed circuit"), hero_level=40, difficulty=None)
    assert patch["mode"] == "route" and patch.get("route_stops"), patch
    import hopper
    nav = {s["label"]: s for s in hopper.load_nav()}
    for st in patch["route_stops"]:
        assert stagenav.parse_label(st["label"]), st
        lvl = nav[st["label"]]["level"]
        assert lvl <= 40 + 8, (st["label"], lvl)         # уровневое окно соблюдено
        assert st["dwell_sec"] > 0, st


def t_apply_route_fixed_stops():
    path = _tmp()
    stops = [{"label": "3-3-9", "dwell_sec": 235}]
    hp.add_user("fixed", stops, path=path)
    patch = hp.apply(hp.get("fixed", path=path), hero_level=80)
    assert patch["mode"] == "route" and patch["route_stops"] == stops, patch
    os.remove(path)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_")]
    fails = 0
    for fn in tests:
        try:
            fn(); print(f"  PASS {fn.__name__}")
        except Exception as e:
            fails += 1; print(f"  FAIL {fn.__name__}: {e!r}")
    print("ALL PASS" if not fails else f"{fails} FAILED")
    sys.exit(1 if fails else 0)
