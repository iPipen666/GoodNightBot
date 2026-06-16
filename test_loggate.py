"""test_loggate.py — стартовый лог-гейт farm2.ensure_log_ready (офлайн, моки). Ключевая проверка:
clear_panels вызывается ДО оценки лога (найденный баг перекрытия). Запуск: .venv python."""
import sys
import types
import farm2

calls = []


class _DummySct:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _setup(find_seq):
    calls.clear()
    farm2.time.sleep = lambda *a, **k: None
    farm2.farm.focus_game = lambda: True
    farm2.farm.clear_panels = lambda sct: calls.append("clear")
    farm2.farm._hardstop = lambda: False
    farm2.farm._stat = lambda **k: calls.append(("stat", k.get("records_ready")))
    farm2.mss.mss = lambda: _DummySct()
    seq = list(find_seq)
    ls = types.ModuleType("log_setup")
    ls.find_log = lambda: (calls.append("find") or {"n": (seq.pop(0) if seq else find_seq[-1])})
    sys.modules["log_setup"] = ls
    rc = types.ModuleType("records_ctl")
    rc.collapse_for_observe = lambda cfg, sct, log=None: calls.append("clear")  # закрывает HERO/stash/cube
    rc.ensure_ready = lambda cfg, log=None, expand=True: (calls.append("open") or (True, True))
    rc.pin_and_expand = lambda cfg, log=None: (calls.append("expand") or True)
    sys.modules["records_ctl"] = rc


def t_clear_before_find():
    _setup([5, 5])
    farm2.ensure_log_ready()
    assert calls.index("clear") < calls.index("find"), f"clear_panels должен быть ДО find_log: {calls}"


def t_ready_first_try_no_open():
    _setup([5, 5])                                   # n>=MIN сразу → не открывать через Settings
    ok, n = farm2.ensure_log_ready()
    assert ok and n == 5, (ok, n)
    assert "open" not in calls, f"при готовом логе Settings НЕ трогаем: {calls}"
    assert "expand" in calls                          # но до макс доразворачиваем


def t_opens_when_closed_then_ready():
    _setup([0, 0, 5, 5])                              # закрыт → open+expand → 2-я попытка готов
    ok, n = farm2.ensure_log_ready()
    assert ok and n == 5, (ok, n)
    assert "open" in calls, f"закрытый лог → должен открыть через Settings: {calls}"


def t_gives_up_after_attempts():
    _setup([0])                                       # всегда 0 → сдаться, не вечный цикл
    ok, n = farm2.ensure_log_ready(attempts=3)
    assert not ok and n == 0, (ok, n)
    assert ("stat", False) in calls, "records_ready=False при провале"


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
