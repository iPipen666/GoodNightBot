"""test_calibration.py — единый реестр калибровок: статус/гейт (офлайн, без pytest/игры)."""
import sys
import types

import calibration as C


def _win(w=970, h=892):
    return types.SimpleNamespace(left=0, top=0, width=w, height=h)


def t_registry_shape():
    ids = [i["id"] for i in C.items()]
    assert {"panels", "log", "chest", "portal"} <= set(ids), ids
    # cube(calibration.json) и settings — легаси/вторичные, НЕ гейтим
    assert "cube" not in ids and "settings" not in ids and "boxes" not in ids, ids
    for it in C.items():
        assert it["coord"] in ("banner_relative", "window_fraction"), it
        assert it["produces"].endswith(".py") and it["gates"], it


def t_banner_relative_ok_if_present():
    it = C.get("panels")
    st, _ = C.status(it, _win(), cal={"stash": {"tab1": [0.1, 0.2]}})
    assert st == "ok", st


def t_banner_relative_missing():
    # пустая калибровка → missing (cal=None грузит реальный offsets.json с диска — это by design)
    assert C.status(C.get("panels"), _win(), cal={})[0] == "missing"


def t_window_fraction_ok_via_calib_window():
    it = C.get("chest")
    cal = {"chest_hover": {"rx": 0.5, "ry": 0.5}, "calib_window": {"w": 970, "h": 892}}
    assert C.status(it, _win(970, 892), cal=cal)[0] == "ok"


def t_window_fraction_ok_via_win_rect():
    # win_rect_at_cal (а не calib_window) должно читаться так же (легаси-формат куба)
    it = C.get("log")
    cal = {"log_field": {"rx": 0.7, "ry": 0.6},
           "win_rect_at_cal": {"width": 1940, "height": 1784}}
    assert C.status(it, _win(1940, 1784), cal=cal)[0] == "ok"


def t_window_fraction_mismatch():
    it = C.get("log")
    cal = {"log_field": {"rx": 0.7, "ry": 0.6}, "calib_window": {"w": 1940, "h": 1784}}
    assert C.status(it, _win(970, 892), cal=cal)[0] == "window_mismatch"


def t_start_blockers_feature_scoped():
    import stagenav
    win = _win()
    orig = stagenav.calibration_status
    stagenav.calibration_status = lambda off=None, win=None: ("missing", "test")
    try:
        # хоп ВЫКЛ → portal не блокирует START, даже если он не ok
        off = C.start_blockers(cfg={"hop": {"enabled": False}}, win=win)
        assert all(b[0] != "portal" for b in off), off
        # хоп ВКЛ + portal не ok → portal в блокерах
        on = C.start_blockers(cfg={"hop": {"enabled": True}}, win=win)
        assert any(b[0] == "portal" for b in on), on
    finally:
        stagenav.calibration_status = orig


def t_window_fraction_no_window_stamp():
    it = C.get("log")
    cal = {"log_open": {"rx": 0.5, "ry": 0.5}}        # нет calib_window/win_rect → no_window
    assert C.status(it, _win(), cal=cal)[0] == "no_window"


def t_window_fraction_missing_points():
    it = C.get("chest")
    assert C.status(it, _win(), cal={"_note": "x"})[0] == "missing"


def t_feature_status_contract():
    st, blocker, _ = C.feature_status("hop", _win())
    rank = {"ok": 0, "no_window": 1, "window_mismatch": 1, "missing": 2, "error": 3}
    assert st in rank, st


def t_summary_contract():
    s = C.summary(_win())
    for k in ("ready_basic", "all_ok", "missing", "stale", "by_id"):
        assert k in s, (k, s)
    assert isinstance(s["missing"], list) and isinstance(s["by_id"], dict)


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
