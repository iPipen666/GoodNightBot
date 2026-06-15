"""chest_stock.py — детект и управление АВТО-ОТКРЫТИЕМ сундуков (SCENARIO A2.4).

Сундуковый HUD: иконка сундука (видна всегда) + значок «A» авто-открытия, который ВЫЛАЗИТ
ТОЛЬКО при наведении курсора на иконку сундука. «A» золотая = ВКЛ, серая = ВЫКЛ.

Бот сам будит «A»: focus_window → move_abs на иконку сундука (двухшаговый hover будит PointerEnter,
проверено живьём 2026-06-10: бот навёлся → 152 золотых пикселя). Затем читает ЦВЕТ рамки «A»
СЧЁТОМ золотых пикселей в её боксе (золото >= gold_min → ВКЛ). Цвет надёжнее OCR буквы, без языка.

Юзер хочет, чтобы бот ВЫКЛючал авто-открытие (чтобы открывать сундуки самому, контролируемо и в
лог). `toggle_off()` кликает по «A» если она золотая, и проверяет, что стала серой.

Координаты — ДОЛИ окна игры (`chest_calibration.json`) → инвариантно к позиции/масштабу.
Калибровка вшита замерами; перекалибровать: python chest_stock.py --cal (F8 на иконку сундука,
F8 на «A»).
"""
import json
import os
import time

import numpy as np

import logwatch

CAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chest_calibration.json")

_DEFAULT = {
    "chest_hover": [0.547, 0.825],
    "a_box": [0.530, 0.808, 0.582, 0.858],
    "a_click": [0.5737, 0.8206],
    "gold_min": 20,
    "chest_brown_min": 60,
}


def _load_cal():
    if os.path.exists(CAL_PATH):
        try:
            d = json.load(open(CAL_PATH, encoding="utf-8"))
            return {**_DEFAULT, **d}
        except Exception:
            pass
    return dict(_DEFAULT)


def _gold_mask(frame):
    """Маска золотых пикселей кадра: тёплый тон (hue 22..52°), насыщенные, не тёмные."""
    ff = frame.astype(float)
    R, G, B = ff[:, :, 0], ff[:, :, 1], ff[:, :, 2]
    mx = np.maximum(np.maximum(R, G), B)
    mn = np.minimum(np.minimum(R, G), B)
    d = mx - mn
    sat = np.where(mx > 0, d / np.maximum(mx, 1), 0)
    hue = np.zeros_like(mx)
    m = (mx == R) & (d > 0); hue[m] = ((G[m] - B[m]) / d[m] % 6) * 60
    m = (mx == G) & (d > 0); hue[m] = ((B[m] - R[m]) / d[m] + 2) * 60
    m = (mx == B) & (d > 0); hue[m] = ((R[m] - G[m]) / d[m] + 4) * 60
    return (hue >= 22) & (hue <= 52) & (sat >= 0.40) & (mx >= 130)


def _gold_count(frame, a_box):
    """Сколько золотых пикселей в боксе «A» (доли окна). Клампим/упорядочиваем границы —
    кривая калибровка (доли >1/отрицательные/инверсия) иначе даёт wrap-индекс и ложное чтение."""
    H, W = frame.shape[:2]
    x0, y0, x1, y1 = a_box
    gx0, gx1 = sorted((int(x0 * W), int(x1 * W)))
    gy0, gy1 = sorted((int(y0 * H), int(y1 * H)))
    gx0, gy0 = max(0, gx0), max(0, gy0)
    gx1, gy1 = min(W, gx1), min(H, gy1)
    if gx1 <= gx0 or gy1 <= gy0:
        return 0
    g = _gold_mask(frame)
    return int(g[gy0:gy1, gx0:gx1].sum())


def _brown_count(frame, cal):
    """Сколько «коричневых» (дерево сундука) пикселей в зоне сундукового HUD. Дёшево, БЕЗ ховера."""
    H, W = frame.shape[:2]
    hx, hy = cal["chest_hover"]
    fx, fy = int(hx * W), int(hy * H)
    y0, y1 = max(0, fy - 35), min(H, fy + 45)
    x0, x1 = max(0, fx - 40), min(W, fx + 40)
    reg = frame[y0:y1, x0:x1].astype(float)
    R, G, B = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
    brown = (R > 70) & (R < 180) & (G > 35) & (G < 130) & (B < 95) & (R - B > 30) & (R - G > 15)
    return int(brown.sum())


def chest_present(frame=None):
    """Есть ли сундук в стоке — ДЁШЕВО, БЕЗ ховера/кликов (иконка сундука видна всегда, когда есть
    сундук). Для частой проверки в observe-цикле: визуальный триггер открытия, не дожидаясь лог-OCR.
    Вернуть bool. Игра не поверх / нет окна → False (лог-путь подстрахует)."""
    cal = _load_cal()
    if frame is None:
        if not logwatch.is_game_foreground():
            return False
        w = logwatch.find_game_window()
        if not w:
            return False
        frame = logwatch.grab(w)
    return _brown_count(frame, cal) >= cal.get("chest_brown_min", 60)


def _hover_chest(cal):
    """Разбудить «A»: фокус окна + двухшаговый move_abs на иконку сундука. True если окно в фокусе."""
    import human
    w = logwatch.find_game_window()
    if not w:
        return None, None
    hwnd = getattr(w, "_hWnd", None)
    if hwnd and not human.focus_window(hwnd):
        return w, False
    hx, hy = cal["chest_hover"]
    human.move_abs(int(hx * w.width) + w.left, int(hy * w.height) + w.top, nudge=16, settle=0.15)
    time.sleep(0.65)
    return w, True


def read(do_hover=True):
    """Замер авто-открытия. do_hover=True → бот сам наводится на сундук, будит «A», читает.
    Возвращает: {auto_open: True|False|None, gold: int, calibrated: True, no_fg/no_game/no_chest}.
    auto_open None → сундука/«A» нет (нет сундуков в стоке) либо игра не поверх."""
    cal = _load_cal()
    if not logwatch.is_game_foreground() and not do_hover:
        return {"no_fg": True, "auto_open": None, "gold": 0, "calibrated": True}
    if do_hover:
        w, fg = _hover_chest(cal)
        if w is None:
            return {"no_game": True, "auto_open": None, "gold": 0, "calibrated": True}
        if fg is False:
            return {"no_fg": True, "auto_open": None, "gold": 0, "calibrated": True}
    else:
        w = logwatch.find_game_window()
        if not w:
            return {"no_game": True, "auto_open": None, "gold": 0, "calibrated": True}
    frame = logwatch.grab(w)
    gold = _gold_count(frame, cal["a_box"])
    gmin = cal.get("gold_min", 40)
    # нет золота И нет серой рамки → вероятно сундука нет в стоке. Грубо: совсем мало золота = ВЫКЛ
    # либо нет сундука. Различить «ВЫКЛ» от «нет сундука» по «A» сложно; для действия это неважно
    # (нет золота → бот откроет Пробелом сам). auto_open=True только при уверенном золоте.
    auto_open = True if gold >= gmin else False
    return {"auto_open": auto_open, "gold": gold, "calibrated": True}


def toggle_off(log=lambda *_: None):
    """Если авто-открытие ВКЛ (золотая «A») — кликнуть по «A», выключить, проверить (стала серой).
    Возвращает dict: {was, now, clicked, ok}. Безопасно: один клик по тоглу, с верификацией."""
    import human
    cal = _load_cal()
    r = read(do_hover=True)
    if r.get("auto_open") is not True:
        return {"was": r.get("auto_open"), "now": r.get("auto_open"), "clicked": False,
                "ok": True, "gold": r.get("gold", 0), **{k: r[k] for k in ("no_fg", "no_game") if k in r}}
    w = logwatch.find_game_window()
    cxf, cyf = cal["a_click"]
    cx, cy = int(cxf * w.width) + w.left, int(cyf * w.height) + w.top
    log(f"авто-открытие ВКЛ (золото={r['gold']}) — выключаю ТОЧНЫМ кликом по «A» (без джиттера)")
    human.tap(cx, cy)                              # точный клик в центр «A», без джиттера к сундуку
    time.sleep(0.5)
    r2 = read(do_hover=True)                       # повторный ховер+чтение для верификации
    now = r2.get("auto_open")
    ok = (now is False)
    log(f"после клика: {'ВЫКЛ ✓' if ok else 'всё ещё ВКЛ ✗'} (золото={r2.get('gold')})")
    try:
        human.park()
    except Exception:
        pass
    return {"was": True, "now": now, "clicked": True, "ok": ok, "gold": r2.get("gold", 0)}


# ---------------------------------------------------------------- калибратор (standalone)
def _calibrate():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    import pyautogui
    import keyboard

    w = logwatch.find_game_window()
    if not w:
        print("Окно игры не найдено."); return
    print(f"окно: left={w.left} top={w.top} w={w.width} h={w.height}")
    print("Нужен сундук в стоке. Наводи курсор и жми F8.\n")

    def wait():
        while True:
            ev = keyboard.read_event()
            if ev.event_type == "down":
                if ev.name == "esc":
                    return "cancel"
                if ev.name == "f8":
                    time.sleep(0.15); return "ok"

    def frac(prompt):
        print(f"  • {prompt}\n    [F8 | Esc-отмена]")
        if wait() == "cancel":
            print("ОТМЕНА."); sys.exit(1)
        x, y = pyautogui.position()
        fx, fy = (x - w.left) / w.width, (y - w.top) / w.height
        print(f"    OK ({fx:.4f},{fy:.4f})")
        return [round(fx, 4), round(fy, 4)]

    cal = _load_cal()
    cal["chest_hover"] = frac("ЦЕНТР иконки СУНДУКА (наводись сюда чтобы будить «A»)")
    ac = frac("ЦЕНТР значка «A» (наведись на сундук, чтоб появилась)")
    cal["a_click"] = ac
    cal["a_box"] = [round(ac[0] - 0.026, 4), round(ac[1] - 0.018, 4),
                    round(ac[0] + 0.026, 4), round(ac[1] + 0.018, 4)]
    json.dump(cal, open(CAL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n  → {CAL_PATH}\n=== ЗАМЕР (бот сам наведётся) ===")
    for i in range(3):
        time.sleep(0.4)
        r = read(do_hover=True)
        print(f"  [{i+1}] auto_open={r['auto_open']} gold={r['gold']}")
    print("\nГотово.")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    if "--cal" in sys.argv or "--calibrate" in sys.argv:
        _calibrate()
    elif "--off" in sys.argv:
        print(toggle_off(log=print))
    else:
        print(read(do_hover=True))
