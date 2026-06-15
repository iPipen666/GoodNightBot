"""test_runtracker.py — стейт-машина тайминга хопа (офлайн). Стиль проекта: без pytest.
Время инжектим вручную (детерминизм)."""
import sys
import runtracker as rt


def _ctrl(t0=1000.0):
    box = {"t": t0}
    c = rt.HopController(pullback_levels=5, fail_threshold=3,
                         chest_grace_s=8.0, new_run_settle_s=3.0, now=lambda: box["t"])
    c.set_stage("4-2-7", level=88)
    return c, box


def t_no_hop_during_run():
    c, _ = _ctrl()
    assert c.state == rt.IN_RUN
    assert not c.ready_to_hop(), "в бою хоп запрещён"


def t_no_hop_right_after_boss_before_chest():
    c, box = _ctrl()
    c.on_event("stage_clear", ts=box["t"])          # босс убит
    assert c.state == rt.CLEARED
    box["t"] += 1.0
    assert not c.ready_to_hop(), "сразу после босса, до сундука — НЕ хопать (потеряем сундук)"


def t_hop_after_chest_and_new_run():
    c, box = _ctrl()
    c.on_event("stage_clear", ts=box["t"])
    box["t"] += 2.0
    c.on_event("getbox", kind="stage_boss", ts=box["t"])  # сундук забран
    assert c.state == rt.SECURED
    box["t"] += 1.0
    assert not c.ready_to_hop(), "сундук есть, но новый проход ещё не устаканился"
    box["t"] += 3.0                                  # прошёл new_run_settle
    assert c.ready_to_hop(), "босс мёртв + сундук забран + новый проход → хоп ОК"


def t_chest_grace_autoopen():
    c, box = _ctrl()
    c.on_event("stage_clear", ts=box["t"])
    box["t"] += 8.0                                  # сундук не залогался, но авто-открылся (грейс)
    c.poll()
    assert c.state == rt.SECURED, "по истечении chest_grace считаем сундук забранным"


def t_pullback_after_3_fails():
    c, box = _ctrl()
    assert c.on_event("defeat") is None
    assert c.on_event("stage_fail") is None
    act = c.on_event("defeat")                       # 3-й вайп подряд
    assert act == "pullback", act
    assert c.pullback_target_level() == 83          # 88 - 5


def t_clear_resets_fail_counter():
    c, box = _ctrl()
    c.on_event("defeat"); c.on_event("defeat")
    assert c.fails_on() == 2
    c.on_event("stage_clear")                        # прошли → счётчик вайпов сброшен
    assert c.fails_on() == 0


def t_set_stage_resets_state():
    c, box = _ctrl()
    c.on_event("stage_clear"); box["t"] += 20; c.ready_to_hop()
    assert c.state == rt.READY_HOP
    c.set_stage("4-1-3", level=78)                   # перешли на новую стадию
    assert c.state == rt.IN_RUN and c.stage == "4-1-3"


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
