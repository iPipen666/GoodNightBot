"""test_hopper.py — юниты планировщика прыжков (офлайн, без игры). Стиль проекта: без pytest."""
import sys
import hopper


def _fake(n):
    # n этапов с уникальными уровнями 1..n
    return [{"label": f"4-1-{i}", "level": i, "act": 1, "no": i, "difficulty": "TORMENT"}
            for i in range(1, n + 1)]


def t_load_nav_real():
    st = hopper.load_nav()
    assert len(st) == 120, len(st)
    assert all("label" in s and "level" in s for s in st)
    assert hopper.by_label(st, "4-2-7") is not None      # текущая стадия Дениса (Torment Акт2 этап7)


def t_level_window_blocks_too_high():
    st = [{"label": "a", "level": 60}, {"label": "b", "level": 80}, {"label": "c", "level": 74}]
    pool = hopper.level_window(st, hero_level=65, max_ahead=8)   # потолок 73
    labels = {s["label"] for s in pool}
    assert labels == {"a"}, labels                       # 80 и 74 отрезаны


def t_level_window_max_behind():
    st = [{"label": "a", "level": 40}, {"label": "b", "level": 64}]
    pool = hopper.level_window(st, hero_level=65, max_ahead=8, max_behind=10)
    assert {s["label"] for s in pool} == {"b"}           # 40 слишком низкий (>10 ниже)


def t_plan_no_consecutive_same_level():
    pool = _fake(10)
    seq = hopper.plan_hops(pool, 30, seed=3, avoid_recent=3)
    assert len(seq) == 30
    lv = [s["level"] for s in seq]
    for i in range(1, len(lv)):
        assert lv[i] != lv[i - 1], f"повтор уровня подряд на {i}: {lv}"


def t_plan_deterministic():
    pool = _fake(10)
    a = [s["label"] for s in hopper.plan_hops(pool, 12, seed=7)]
    b = [s["label"] for s in hopper.plan_hops(pool, 12, seed=7)]
    assert a == b, "один seed -> один план"


def t_hop_pair_diff_levels():
    pool = _fake(5)
    p = hopper.hop_pair(pool, seed=2)
    assert p and p[0]["level"] != p[1]["level"], p


def t_hop_pair_single_level_none():
    pool = [{"label": "x", "level": 50}, {"label": "y", "level": 50}]
    assert hopper.hop_pair(pool) is None                 # один уровень -> нет пары


def t_cluster_filters():
    st = hopper.load_nav()
    torment = hopper.cluster(st, difficulty="TORMENT")
    assert len(torment) == 30 and all(s["difficulty"] == "TORMENT" for s in torment)
    t_act2 = hopper.cluster(st, difficulty="TORMENT", act=2)
    assert len(t_act2) == 10 and all(s["act"] == 2 for s in t_act2)
    # внутри одной сложности всё ещё много разных уровней (juggling возможен)
    assert len({s["level"] for s in torment}) >= 10


def t_next_stage_avoids_recent():
    pool = _fake(4)                                       # уровни 1..4
    import random
    s = hopper.next_stage(pool, recent_levels=[1, 2, 3], rng=random.Random(0))
    assert s["level"] == 4, s                             # единственный свежий


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
