"""geom.py — деривация контрольных точек из ЯКОРЯ (единая anchor-relative система). См. ADR 0002.

Каждая точка хранится в offsets.json как смещение от центра ЯКОРЯ, нормированное на ширину якоря.
Якорь детектится автоматически: БАННЕР панели (vision.detect) или ИКОНКА (vision.find_anchor) для
экранов без баннера (лог/сундук). Экранная точка = центр_якоря + offset·ширина_якоря (vision.pt).

Схема offsets.json (расширенная):
  "hero":   {"close":[ox,oy], "inv_sort":[ox,oy], ...}          # якорь = баннер "hero"
  "portal": {"close":..., "diff_dropdown":..., "node_3":...}    # якорь = баннер "portal"
  "log":    {"_anchor":{"icon":"templates/records_expand.png"}, "log_field":[ox,oy], ...}
  "chest":  {"_anchor":{"icon":"templates/chests/normal.png"},  "a_click":[ox,oy], ...}
Секция без "_anchor" → якорь = баннер с именем секции. С "_anchor.icon" → икона-якорь (find_anchor).

API: point(section, name, win, sct) → (x,y) ЭКРАН или None (якорь не найден / точки нет → консумер
падает на свой старый путь). anchor(section, win, sct) → dict {cx,cy,w} или None.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_OFFS = os.path.join(HERE, "offsets.json")


def _load():
    try:
        with open(_OFFS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def anchor(section, win, sct, off=None):
    """Найти якорь секции → {cx,cy,w} (ЭКРАН) или None. Баннер (detect) или икона (find_anchor)."""
    import vision
    off = off if off is not None else _load()
    spec = (off.get(section) or {}).get("_anchor")
    if spec and spec.get("icon"):
        tpl = os.path.join(HERE, spec["icon"])
        r = vision.find_anchor(win, sct, tpl)            # (left,top,w,h,score) | None
        if not r:
            return None
        left, top, w, h, _ = r
        return {"cx": left + w / 2, "cy": top + h / 2, "w": w}
    det = vision.detect(win, sct, names=[section])       # баннер с именем секции
    return det.get(section)


def point(section, name, win, sct, off=None):
    """Экранная точка контрольной точки section.name через её якорь. None если нет данных/якоря."""
    import vision
    off = off if off is not None else _load()
    sec = off.get(section) or {}
    o = sec.get(name)
    if not o or not isinstance(o, (list, tuple)) or len(o) < 2:
        return None
    a = anchor(section, win, sct, off)
    if not a:
        return None
    return vision.pt(a, o[0], o[1])


def has(section, name, off=None):
    """Есть ли измеренное смещение для section.name (banner-relative готов)."""
    off = off if off is not None else _load()
    o = (off.get(section) or {}).get(name)
    return isinstance(o, (list, tuple)) and len(o) >= 2
