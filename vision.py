"""TBH — VISION: динамический детект панелей (масштаб + что открыто) каждый цикл.

Идея (north-star): не доверять фиксированным долям окна (ломаются при смене
масштаба/Авто-макета). Вместо этого КАЖДЫЙ раз:
  1) matchTemplate баннеров заголовков (мультимасштаб) -> какие панели открыты,
     их центр и ШИРИНА баннера (= текущий масштаб UI);
  2) элементы внутри панели задаём смещением, НОРМИРОВАННЫМ на ширину баннера
     -> scale-инвариантно и позиционно-инвариантно.

API:
  detect(win, sct) -> {name: Panel}   Panel = {cx,cy,w,h,scale,score} в ЭКРАННЫХ коорд.
  pt(panel, ox, oy) -> (x,y)          точка по нормированному смещению от центра баннера
  norm_offset(panel, sx, sy) -> (ox,oy)   обратное: экранная точка -> норм. смещение
"""
import json
import os
import ctypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
PDIR = os.path.join(HERE, "templates", "panels")
MATCH_THR = CFG.get("panel_match_threshold", 0.72)


def reload_config():
    """Перечитать config.json в рантайме (порог матча баннеров из настроек панели)."""
    global CFG, MATCH_THR
    CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    MATCH_THR = CFG.get("panel_match_threshold", 0.72)
PANELS = ["stash", "hero", "cube", "portal", "runes", "status", "settings", "tradeship", "mail"]
# диапазон масштабов шаблона: ШИРОКИЙ, чтобы окно/экран любого масштаба и DPI ловились
# (game Window Scale 1x..2x, разные разрешения/мониторы). Эталоны ~300px; 0.30..2.0 покрывает
# баннер ~90..600px. MATCH_THR=0.72 отсекает ложные на «лишних» масштабах.
SCALES = [round(s, 3) for s in np.arange(0.30, 2.01, 0.05)]
# КЭШ МАСШТАБА: полный свип по SCALES медленный (~20с на 1455px-окне). Масштаб окна в
# рамках сессии постоянен -> кэшируем найденный и ищем узкой полосой вокруг (быстро).
# Полный свип только первый раз и после серии промахов (= масштаб реально сменился).
_SCALE_CACHE = {}         # name -> последний удачный масштаб (ПО КАЖДОМУ шаблону: они разного
_MISS = {}                # размера, общий кэш ломал детект, напр. mail.png 190px vs hero.png 300px)
_SCALE_BAND = 0.15        # ± вокруг кэша
_MISS_BEFORE_FULL = 3     # столько промахов подряд -> полный пересвип шаблона
# ГЛОБАЛЬНЫЙ масштаб сессии: игра ОДНОГО масштаба всю сессию. Полный свип 35 масштабов × 9 панелей
# ≈5с КАЖДЫЙ detect, когда панель закрыта (per-name кэш пуст → полный свип). Как только ЛЮБАЯ панель
# нашлась на масштабе S — ВСЕ панели (даже невиданные) ищем узкой полосой вокруг S → detect <1с.
_SESSION_SCALE = None


def reset_session_scale():
    global _SESSION_SCALE
    _SESSION_SCALE = None

_TPL = {}


def _templates():
    if not _TPL:
        for name in PANELS:
            p = os.path.join(PDIR, f"{name}.png")
            if os.path.exists(p):
                img = cv2.imread(p)
                if img is not None:
                    _TPL[name] = img
    return _TPL


def grab(win, sct):
    top = max(0, int(win.top))
    h = int(win.height) - (top - int(win.top))
    img = np.array(sct.grab({"left": int(win.left), "top": top,
                             "width": int(win.width), "height": h}))[:, :, :3]
    return np.ascontiguousarray(img), top - int(win.top)


_SEARCH_DS = 0.5   # даунскейл картинки поиска: matchTemplate ~4x быстрее, баннеры (крупные
                   # цветные фичи) переживают; широкий диапазон масштабов остаётся быстрым.


def _match(full, tpl, scales=None):
    """Лучшее совпадение по масштабам -> (score, cx, cy, w, h, scale) в коорд. кадра.
    Поиск на даунскейл-копии (скорость), координаты/размеры масштабируются обратно."""
    ds = _SEARCH_DS
    fs = cv2.resize(full, (max(1, int(full.shape[1] * ds)), max(1, int(full.shape[0] * ds))),
                    interpolation=cv2.INTER_AREA)
    Hs, Ws = fs.shape[:2]
    best = (-1.0, 0, 0, 0, 0, 1.0)
    for s in (scales or SCALES):
        th, tw = int(tpl.shape[0] * s * ds), int(tpl.shape[1] * s * ds)
        if th < 6 or tw < 12 or th > Hs or tw > Ws:
            continue
        t = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(fs, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx > best[0]:
            best = (mx, (loc[0] + tw / 2) / ds, (loc[1] + th / 2) / ds,
                    tw / ds, th / ds, s)
    return best


def detect(win, sct, names=None):
    """Открытые панели -> {name: {cx,cy,w,h,scale,score}} (центр баннера, ЭКРАН. коорд).
    names=[…] — матчить ТОЛЬКО эти панели (быстрее, когда нужны 2-3 из 9)."""
    global _SESSION_SCALE
    full, off = grab(win, sct)
    cands = []
    items = [(n, t) for n, t in _templates().items() if names is None or n in names]
    for name, tpl in items:
        # масштаб: per-name кэш → иначе ГЛОБАЛЬНЫЙ масштаб сессии (узкая полоса) → иначе полный свип.
        # Сессионный масштаб убирает 5с-свипы для ещё-не-виданных/закрытых панелей (игра 1 масштаба).
        cs = _SCALE_CACHE.get(name)
        if cs is not None and _MISS.get(name, 0) < _MISS_BEFORE_FULL:
            scales = [s for s in SCALES if cs - _SCALE_BAND <= s <= cs + _SCALE_BAND]
        elif _SESSION_SCALE is not None:
            # масштаб игры фиксирован всю сессию → закрытая/невиданная панель ищется узкой полосой
            # вокруг session_scale БЕЗ _MISS-эскалации (закрытая панель не значит «другой масштаб»).
            scales = [s for s in SCALES if _SESSION_SCALE - _SCALE_BAND <= s <= _SESSION_SCALE + _SCALE_BAND]
        else:
            scales = SCALES
        score, cx, cy, w, h, scale = _match(full, tpl, scales)
        if score >= MATCH_THR:
            cands.append((score, name, cx, cy, w, h, scale))
        else:
            _MISS[name] = _MISS.get(name, 0) + 1
    # NMS: один баннер физически не может быть двумя панелями. Шаблоны похожей формы
    # (cube.png ложно матчит плашку RUNES на 0.73 < runes 0.98) дают двойной матч в одной
    # точке -> оставляем тот, у кого score выше, остальные перекрывающиеся считаем промахом.
    cands.sort(reverse=True)
    accepted = []
    out = {}
    for score, name, cx, cy, w, h, scale in cands:
        if any(abs(cx - acx) < 0.5 * max(w, aw) and abs(cy - acy) < 0.6 * max(h, ah)
               for acx, acy, aw, ah in accepted):
            _MISS[name] = _MISS.get(name, 0) + 1   # подавлен перекрытием -> для него это промах
            continue
        accepted.append((cx, cy, w, h))
        out[name] = {"cx": win.left + cx, "cy": win.top + off + cy,
                     "w": w, "h": h, "scale": round(scale, 3),
                     "score": round(float(score), 3)}
        _SCALE_CACHE[name] = scale
        _SESSION_SCALE = scale          # игра 1 масштаба → запомнить для ВСЕХ панелей сессии
        _MISS[name] = 0
    return out


_ICON_CACHE = {}   # path -> tpl image


def find_icon(win, sct, tpl_path, thr=0.62):
    """Найти произвольную иконку по шаблону на экране -> (cx, cy, score) ЭКРАН или None.
    Мультимасштаб (как баннеры). Для мелких иконок тулбара (почта и т.п.), позиция которых
    НЕ привязана к баннеру панели — устойчиво к перемещению/масштабу окна."""
    tpl = _ICON_CACHE.get(tpl_path)
    if tpl is None:
        tpl = cv2.imread(tpl_path)
        if tpl is None:
            return None
        _ICON_CACHE[tpl_path] = tpl
    full, off = grab(win, sct)
    score, cx, cy, w, h, scale = _match(full, tpl)
    if score >= thr:
        return (int(win.left + cx), int(win.top + off + cy), round(float(score), 3))
    return None


_ANCHOR_TPL = {}     # path -> tpl image
_ANCHOR_SCALE = {}   # path -> последний удачный масштаб (узкая полоса вокруг = быстро)


def find_anchor(win, sct, tpl_path, thr=0.60):
    """Найти ЯКОРЬ (шаблон, напр. «стрелка вверх» боя) -> (left, top, w, h, score) в ЭКРАННЫХ
    коорд. (top-left бокса) или None. Мультимасштаб с кэшем масштаба (как баннеры). Нужен для
    привязки HUD-таймера к нижней границе боя — адаптивно к масштабу/позиции окна."""
    tpl = _ANCHOR_TPL.get(tpl_path)
    if tpl is None:
        if not os.path.exists(tpl_path):
            return None
        tpl = cv2.imread(tpl_path)
        if tpl is None:
            return None
        _ANCHOR_TPL[tpl_path] = tpl
    full, off = grab(win, sct)
    cs = _ANCHOR_SCALE.get(tpl_path)
    scales = [s for s in SCALES if cs - _SCALE_BAND <= s <= cs + _SCALE_BAND] if cs else SCALES
    score, cx, cy, w, h, scale = _match(full, tpl, scales)
    if score < thr and cs:                       # узкая полоса промахнулась -> полный свип
        score, cx, cy, w, h, scale = _match(full, tpl, SCALES)
    if score < thr:
        return None
    _ANCHOR_SCALE[tpl_path] = scale
    return (int(win.left + cx - w / 2), int(win.top + off + cy - h / 2),
            int(w), int(h), round(float(score), 3))


def capture_anchor(sct, cx, cy, tpl_path, size=64):
    """Снять кроп size×size вокруг (cx,cy) ЭКРАН и сохранить как шаблон якоря (калибровка HUD).
    Сбрасывает кэш, чтобы новый шаблон сразу подхватился. Вернуть True/False."""
    half = size // 2
    img = np.array(sct.grab({"left": int(cx - half), "top": int(cy - half),
                             "width": size, "height": size}))[:, :, :3]
    os.makedirs(os.path.dirname(tpl_path), exist_ok=True)
    ok = cv2.imwrite(tpl_path, img)
    _ANCHOR_TPL.pop(tpl_path, None)
    _ANCHOR_SCALE.pop(tpl_path, None)
    return bool(ok)


def pt(panel, ox, oy):
    """Экранная точка по норм. смещению (доли ШИРИНЫ баннера) от его центра."""
    return (int(panel["cx"] + ox * panel["w"]), int(panel["cy"] + oy * panel["w"]))


def norm_offset(panel, sx, sy):
    """Обратное: экранная точка -> норм. смещение от центра баннера (в ширинах баннера)."""
    return ((sx - panel["cx"]) / panel["w"], (sy - panel["cy"]) / panel["w"])


if __name__ == "__main__":
    # самотест: печать открытых панелей + масштаб
    import time
    import pygetwindow as gw
    import mss

    def fw():
        for w in gw.getAllWindows():
            t = w.title or ""
            if t and any(s.lower() in t.lower() for s in CFG["window_title_contains"]) and w.width > 100:
                return w
        return None
    w = fw()
    if not w:
        print("окно не найдено")
    else:
        print(f"окно ({w.left},{w.top},{w.width}x{w.height})")
        with mss.mss() as sct:
            d = detect(w, sct)
        if not d:
            print("панелей не найдено (нет баннеров? порог?)")
        for name in PANELS:
            if name in d:
                p = d[name]
                print(f"  ОТКРЫТА {name:9s} центр=({p['cx']},{p['cy']}) ширина={p['w']} "
                      f"масштаб={p['scale']} score={p['score']}")
