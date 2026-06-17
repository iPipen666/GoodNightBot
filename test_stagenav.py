"""test_stagenav.py — чистая логика навигации PORTAL (офлайн). Без pytest."""
import sys
import types
import stagenav as sn


def t_parse_label_ok():
    p = sn.parse_label("4-2-7")
    assert p == {"diff_idx": 4, "difficulty": "TORMENT", "act": 2, "no": 7}, p
    assert sn.parse_label("2-3-6")["difficulty"] == "NIGHTMARE"
    assert sn.parse_label("1-1-1")["difficulty"] == "NORMAL"


def t_parse_label_bad():
    for bad in ("5-1-1", "4-4-1", "4-2-11", "4-2-0", "abc", "4-2", "", "4-2-7-1"):
        assert sn.parse_label(bad) is None, bad


def t_nav_plan_sequence():
    # этап 7 ≤ 7 → страница bottom, скролл вниз
    plan = sn.nav_plan("4-2-7")
    assert plan == [("click", "diff_dropdown"),
                    ("click", "diff_option_torment"), ("click", "act_tab_2"),
                    ("scroll", "down"), ("node", "bottom:7")], plan
    # этап 9 ≥ 8 → страница top, скролл вверх
    plan2 = sn.nav_plan("2-3-9")
    assert plan2[-2:] == [("scroll", "up"), ("node", "top:9")], plan2
    assert sn.nav_plan("badlabel") is None


def t_page_for():
    assert [sn._page_for(n) for n in (1, 7, 8, 10)] == ["bottom", "bottom", "top", "top"]


def t_calib_status_vision_driven():
    # PORTAL навигируется зрением → отдельная калибровка не нужна, статус всегда ok
    assert sn.calibration_status()[0] == "ok"
    assert sn.is_calibrated() is True


def t_node_re_matches():
    assert sn._NODE_RE.search("[2-7]").groups() == ("2", "7")
    assert sn._NODE_RE.search("2-10]").groups() == ("2", "10")
    assert sn._NODE_RE.search("Полуночные") is None


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
