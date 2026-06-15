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
    plan = sn.nav_plan("4-2-7")
    keys = [k for _, k in plan]
    assert keys == ["portal_open", "diff_dropdown", "diff_option_torment",
                    "act_tab_2", "stage_nodes/2/7"], keys
    assert sn.nav_plan("badlabel") is None


def t_resolve_node_and_point():
    win = types.SimpleNamespace(left=100, top=200, width=1000, height=800)
    cal = {"diff_dropdown": {"rx": 0.5, "ry": 0.1},
           "stage_nodes": {"2": [{"rx": 0.6, "ry": 0.3}, {"rx": 0.6, "ry": 0.4}]}}
    assert sn.resolve(cal, "diff_dropdown", win) == (100 + 500, 200 + 80)          # (600,280)
    assert sn.resolve(cal, "stage_nodes/2/2", win) == (100 + 600, 200 + 320)        # (700,520)
    assert sn.resolve(cal, "stage_nodes/2/9", win) is None                          # нет такого узла
    assert sn.resolve(cal, "portal_open", win) is None                              # ключа нет


def t_empty_calibration_is_safe():
    # Реальный скелет portal_calibration.json пустой → resolve всех ключей плана = None
    cal = sn._cal()
    win = types.SimpleNamespace(left=0, top=0, width=970, height=892)
    plan = sn.nav_plan("4-2-7")
    resolved = [sn.resolve(cal, k, win) for _, k in plan]
    assert all(r is None for r in resolved), f"пустая калибровка → ничего не кликаем: {resolved}"


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
