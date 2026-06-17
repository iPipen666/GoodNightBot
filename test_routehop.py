"""test_routehop.py — таймерный маршрут (парс + тайминг + защита). Офлайн, без pytest/игры."""
import sys

import routehop


# ── парс ──────────────────────────────────────────────────────────────────────
def t_parse_canonical():
    stop, err = routehop.parse_line("3-3-9 / time: 235 sec")
    assert err is None and stop == {"label": "3-3-9", "dwell_sec": 235}, (stop, err)


def t_parse_alt_formats():
    for line, exp in [("2-1-4: 180", 180), ("4-2-7   300s", 300), ("1-1-10=90", 90)]:
        stop, err = routehop.parse_line(line)
        assert err is None and stop["dwell_sec"] == exp, (line, stop, err)


def t_parse_comment_and_blank():
    assert routehop.parse_line("   ") == (None, None)
    assert routehop.parse_line("# just a note") == (None, None)
    stop, err = routehop.parse_line("3-3-9 235 # circuit start")
    assert err is None and stop["dwell_sec"] == 235, (stop, err)


def t_parse_bad_label():
    _, err = routehop.parse_line("9-9-9 100")      # сложность 9 / этап вне 1-10
    assert err and "диапазон" in err, err
    _, err = routehop.parse_line("hello 100")
    assert err and "метк" in err, err


def t_parse_missing_time():
    _, err = routehop.parse_line("3-3-9")
    assert err and "врем" in err, err
    _, err = routehop.parse_line("3-3-9 0")
    assert err and ">0" in err, err


def t_parse_route_collects_errors():
    stops, errs = routehop.parse_route("3-3-9 / time: 235 sec\nbad line\n2-1-4 180")
    assert [s["label"] for s in stops] == ["3-3-9", "2-1-4"], stops
    assert len(errs) == 1, errs


def t_parse_route_cfg_dicts_and_strings():
    stops, errs = routehop.parse_route_cfg(
        [{"label": "3-3-9", "dwell_sec": 235}, "2-1-4 180", {"label": "x", "time": 5}])
    assert [s["label"] for s in stops] == ["3-3-9", "2-1-4"], stops
    assert len(errs) == 1, errs


def t_format_roundtrip():
    stops, _ = routehop.parse_route("3-3-9/time:235sec\n2-1-4: 180")
    txt = routehop.format_route(stops)
    again, _ = routehop.parse_route(txt)
    assert again == stops, (txt, again)


# ── контроллер ──────────────────────────────────────────────────────────────────
def _mk(navigate_ok=True, stops=None):
    box = {"t": 1000.0}
    visited = []
    if stops is None:
        stops = [{"label": "3-3-9", "dwell_sec": 200},
                 {"label": "2-1-4", "dwell_sec": 100}]
    rh = routehop.RouteHop(stops, now=lambda: box["t"],
                           navigate=lambda s: (visited.append(s["label"]) or navigate_ok))
    return rh, box, visited


def t_first_tick_enters_stage_one():
    rh, box, visited = _mk()
    lab = rh.tick()
    assert lab == "3-3-9" and visited == ["3-3-9"] and rh.idx == 0 and rh.hops == 0, (lab, visited)


def t_no_hop_before_dwell():
    rh, box, visited = _mk()
    rh.tick()                                          # вошли на 3-3-9 (dwell 200)
    box["t"] += 150
    assert rh.tick() is None and visited == ["3-3-9"], visited


def t_hop_after_dwell_and_loop():
    rh, box, visited = _mk()
    rh.tick()                                          # 3-3-9
    box["t"] += 201
    assert rh.tick() == "2-1-4" and rh.hops == 1, (visited, rh.hops)
    box["t"] += 101                                    # время 2-1-4 (100) вышло → по кругу на 3-3-9
    assert rh.tick() == "3-3-9" and rh.hops == 2, (visited, rh.hops)
    assert visited == ["3-3-9", "2-1-4", "3-3-9"], visited


def t_defer_hop_during_boss_chest():
    # босс умирает почти в момент истечения времени → защита в окне грейса (~8с)
    rh, box, visited = _mk()
    rh.tick()                                          # на 3-3-9 (dwell 200)
    box["t"] += 199
    rh.on_log_events([("stage_clear", None, box["t"])])  # босс убит, сундук НЕ забран
    box["t"] += 2                                      # время вышло, но 2с с момента клира < грейс
    assert rh.tick() is None, "не прыгаем пока боссовый сундук не забран"
    rh.on_log_events([("getbox", "stage_boss", box["t"])])  # сундук забран
    assert rh.tick() == "2-1-4", "сундук забран → можно прыгать"


def t_failed_nav_retries():
    rh, box, visited = _mk(navigate_ok=False)
    assert rh.tick() is None and rh.idx == -1, "навигация провалилась → не зашли"
    assert visited == ["3-3-9"], visited                # попытка была
    box["t"] += 5
    rh.tick()
    assert visited == ["3-3-9", "3-3-9"], "повтор захода на следующем тике"


def t_empty_route_noop():
    rh, _, _ = _mk(stops=[])
    assert rh.tick() is None


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
