"""test_gamesettings.py — чистая логика установки игровых настроек (офлайн). Без pytest."""
import sys
import types
import gamesettings as gs


def t_plan_known():
    p = gs.plan("pin_log")
    assert [k for _, k in p] == ["gear", "toggle:pin_log", "close"], p
    assert gs.plan("nope") is None


def t_resolve_points():
    win = types.SimpleNamespace(left=10, top=20, width=1000, height=1000)
    cal = {"gear": {"rx": 0.6, "ry": 0.3}, "toggles": {"pin_log": {"rx": 0.62, "ry": 0.48}}}
    assert gs.resolve(cal, "gear", win) == (10 + 600, 20 + 300)
    assert gs.resolve(cal, "toggle:pin_log", win) == (10 + 620, 20 + 480)
    assert gs.resolve(cal, "toggle:chest_autoopen", win) is None        # не откалибровано
    assert gs.resolve(cal, "close", win) is None


def t_empty_calibration_safe():
    cal = gs._cal()                                                     # реальный скелет (пуст)
    win = types.SimpleNamespace(left=0, top=0, width=970, height=892)
    for _, key in gs.plan("pin_log"):
        assert gs.resolve(cal, key, win) is None, key                  # ничего не кликнем


def t_known_covers_log_and_chest():
    assert "pin_log" in gs.KNOWN and "chest_autoopen" in gs.KNOWN
    assert all(gs.plan(n) for n in gs.KNOWN)                           # у каждой известной есть план


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
