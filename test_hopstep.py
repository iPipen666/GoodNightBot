"""test_hopstep.py — farm2._hop_step: дельты лог-счётчиков → события HopMode (офлайн, моки)."""
import sys
import types
import farm2


class _FakeHM:
    def __init__(self):
        self.events = []
        self.ticks = 0

    def on_log_events(self, ev):
        self.events += list(ev)

    def tick(self, now=None):
        self.ticks += 1


def _setup(stages_cleared=0, chests=None, defeats=0):
    farm2.farm._LOG = types.SimpleNamespace(
        stages_cleared=stages_cleared, chests=chests or {}, defeats=defeats)
    hm = _FakeHM()
    ctx = {"_hop": hm, "_hop_sc": 0, "_hop_ct": 0, "_hop_df": 0}
    return ctx, hm


def t_noop_when_hop_off():
    farm2.farm._LOG = types.SimpleNamespace(stages_cleared=5, chests={"normal": 3}, defeats=1)
    ctx = {"_hop": None}
    farm2._hop_step(ctx, now=1.0)                      # не должно падать / ничего не делает
    assert ctx.get("_hop") is None


def t_stage_clear_delta():
    ctx, hm = _setup(stages_cleared=2)
    farm2._hop_step(ctx, now=1.0)
    sc = [e for e in hm.events if e[0] == "stage_clear"]
    assert len(sc) == 2, hm.events                     # 2 новых клира → 2 события
    assert ctx["_hop_sc"] == 2
    assert hm.ticks == 1


def t_getbox_on_chest_delta():
    ctx, hm = _setup(chests={"normal": 1, "stage_boss": 2})  # всего 3
    farm2._hop_step(ctx, now=1.0)
    gb = [e for e in hm.events if e[0] == "getbox"]
    assert len(gb) == 1, hm.events                     # рост сундуков → одно getbox-событие
    assert ctx["_hop_ct"] == 3


def t_defeat_delta():
    ctx, hm = _setup(defeats=3)
    farm2._hop_step(ctx, now=1.0)
    df = [e for e in hm.events if e[0] == "defeat"]
    assert len(df) == 3, hm.events
    assert ctx["_hop_df"] == 3


def t_no_double_count():
    ctx, hm = _setup(stages_cleared=1)
    farm2._hop_step(ctx, now=1.0)
    farm2._hop_step(ctx, now=2.0)                      # счётчик не вырос → новых событий нет
    assert len([e for e in hm.events if e[0] == "stage_clear"]) == 1
    assert hm.ticks == 2                               # тик всё равно каждый раз


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
