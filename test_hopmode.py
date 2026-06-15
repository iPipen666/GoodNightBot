"""test_hopmode.py — мозг hop-режима (офлайн, фейковый навигатор + инжект времени). Без pytest."""
import sys
import hopmode


def _stages():
    # 6 стадий разных уровней вокруг геро-уровня 88 (Torment)
    return [{"label": f"4-1-{i}", "level": 80 + i, "act": 1, "no": i, "difficulty": "TORMENT"}
            for i in range(1, 7)]


def _mk(navigate_ok=True):
    box = {"t": 1000.0}
    visited = []
    hm = hopmode.HopMode(_stages(), hero_level=88, max_ahead=8,
                         navigate=lambda s: (visited.append(s["label"]) or navigate_ok),
                         seed=1, now=lambda: box["t"])
    hm.start_on(_stages()[0])                            # старт на 4-1-1
    return hm, box, visited


def t_no_hop_mid_run():
    hm, box, visited = _mk()
    box["t"] += 5
    assert hm.tick() is None, "в бою не прыгаем"
    assert visited == [], visited


def t_hop_only_after_chest_and_new_run():
    hm, box, visited = _mk()
    hm.on_log_events([("stage_clear", None, box["t"])])  # босс убит
    box["t"] += 2
    hm.on_log_events([("getbox", "stage_boss", box["t"])])  # сундук забран
    box["t"] += 1
    assert hm.tick() is None, "новый проход ещё не устаканился — рано"
    box["t"] += 3                                         # прошёл settle
    lab = hm.tick()
    assert lab is not None and hm.hops == 1, (lab, hm.hops)
    assert visited and visited[-1] == lab


def t_no_hop_if_only_boss_dead():
    hm, box, visited = _mk()
    hm.on_log_events([("stage_clear", None, box["t"])])
    box["t"] += 1
    assert hm.tick() is None, "босс убит, но сундук не забран → НЕ прыгать (потеряем сундук)"


def t_pullback_on_three_wipes():
    hm, box, visited = _mk()
    hm.on_log_events([("defeat", None, box["t"]), ("defeat", None, box["t"]),
                      ("defeat", None, box["t"])])        # 3 вайпа → pullback
    assert hm.pullbacks == 1, hm.pullbacks
    assert visited, "pullback должен инициировать навигацию вниз"
    # стадия отката — уровнем ниже текущей (88 герой, старт 4-1-1=L81; target=81-5=76 → нет в пуле
    # (мин 81) → берём ближайшую снизу, т.е. самую низкую доступную)


def t_failed_nav_keeps_state():
    hm, box, visited = _mk(navigate_ok=False)
    hm.on_log_events([("stage_clear", None, box["t"])])
    box["t"] += 2; hm.on_log_events([("getbox", "stage_boss", box["t"])])
    box["t"] += 4
    assert hm.tick() is None and hm.hops == 0, "навигация провалилась → хоп не засчитан"


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
