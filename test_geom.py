"""test_geom.py — деривация точек из якоря (banner/icon), офлайн с фейковым vision."""
import sys
import types


def _fake_vision():
    v = types.ModuleType("vision")
    v.pt = lambda a, ox, oy: (int(a["cx"] + ox * a["w"]), int(a["cy"] + oy * a["w"]))
    v.norm_offset = lambda a, x, y: ((x - a["cx"]) / a["w"], (y - a["cy"]) / a["w"])
    v.detect = lambda win, sct, names=None: {"hero": {"cx": 500, "cy": 300, "w": 200}} \
        if (names and "hero" in names) else {}
    v.find_anchor = lambda win, sct, tpl, thr=0.6: (600, 400, 40, 30, 0.9)  # left,top,w,h,score
    return v


def t_point_banner():
    sys.modules["vision"] = _fake_vision()
    import importlib
    import geom; importlib.reload(geom)
    off = {"hero": {"close": [0.5, -0.2]}}
    p = geom.point("hero", "close", win=object(), sct=object(), off=off)
    # cx+ox*w=500+0.5*200=600 ; cy+oy*w=300+(-0.2)*200=260
    assert p == (600, 260), p


def t_point_icon_anchor():
    sys.modules["vision"] = _fake_vision()
    import importlib
    import geom; importlib.reload(geom)
    off = {"log": {"_anchor": {"icon": "templates/records_expand.png"}, "log_field": [1.0, 0.5]}}
    # icon anchor: cx=600+40/2=620, cy=400+30/2=415, w=40 ; pt=620+1.0*40=660, 415+0.5*40=435
    p = geom.point("log", "log_field", win=object(), sct=object(), off=off)
    assert p == (660, 435), p


def t_point_missing_returns_none():
    sys.modules["vision"] = _fake_vision()
    import importlib
    import geom; importlib.reload(geom)
    assert geom.point("hero", "nope", win=object(), sct=object(), off={"hero": {}}) is None
    assert geom.has("hero", "close", off={"hero": {"close": [0.1, 0.2]}}) is True
    assert geom.has("hero", "nope", off={"hero": {}}) is False


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
