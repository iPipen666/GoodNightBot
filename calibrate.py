"""TBH Cube Clicker — калибровка координат (хоткеи, без переключения на консоль).

Наводишь курсор на элемент в ИГРЕ и жмёшь F8 (глобально — фокус консоли не нужен).
Записывает: Автозаполнение, Подтвердить, левую-верхнюю и правую-нижнюю ячейки
сетки 3x3. По двум углам clicker.py считает все 9 ячеек (детект '9/9 одной редкости').
F9 — замер яркости пустой ячейки. Esc — отмена.

Запуск (в отдельном окне):  python calibrate.py
"""
import json
import os
import sys
import time
import ctypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import numpy as np
import mss
import pyautogui
import pygetwindow as gw

try:
    import keyboard
    HAVE_KB = True
except Exception:
    HAVE_KB = False

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
CAL_PATH = os.path.join(HERE, "calibration.json")


def find_window():
    for w in gw.getAllWindows():
        t = w.title or ""
        if t and any(s.lower() in t.lower() for s in CFG["window_title_contains"]) and w.width > 100:
            return w
    return None


def brightness(left, top, size):
    with mss.mss() as sct:
        img = np.array(sct.grab({"left": int(left), "top": int(top),
                                 "width": int(size), "height": int(size)}))[:, :, :3]
    return float(img.mean())


def wait_key(key):
    """Ждать глобальное нажатие key (или Esc -> выход). Fallback: Enter в консоли."""
    if HAVE_KB:
        while True:
            ev = keyboard.read_event()
            if ev.event_type == "down":
                if ev.name == "esc":
                    print("Отмена."); sys.exit(1)
                if ev.name == key:
                    time.sleep(0.25)
                    return
    else:
        input(f"  [keyboard недоступен] наведи курсор и нажми Enter в этом окне...")


def cap(win, name, prompt, key="f8"):
    print(f"\n[{name}] {prompt}")
    print(f"  -> наведи курсор и нажми {key.upper()} (Esc — отмена)")
    wait_key(key)
    x, y = pyautogui.position()
    rx = (x - win.left) / win.width
    ry = (y - win.top) / win.height
    print(f"  OK: экран ({x},{y}) | относ. ({rx:.4f}, {ry:.4f})")
    return {"rx": rx, "ry": ry, "abs_at_cal": [x, y]}


def main():
    print("=== Калибровка TBH Cube Clicker (хоткеи F8 / F9) ===")
    if not HAVE_KB:
        print("[!] keyboard недоступен (нужны права админа для глоб. хоткеев).")
        print("    Работаю в режиме Enter — придётся кликать в это окно перед Enter.")
    win = find_window()
    if not win:
        print("Окно игры не найдено. Открой игру. (config window_title_contains)")
        sys.exit(1)
    print(f"Окно: {win.title!r}  rect=({win.left},{win.top},{win.width},{win.height})")
    print("\nПОДГОТОВКА: открой панель CUBE. Удобно сначала нажать 'Автозаполнение' в игре,")
    print("чтобы видеть ячейки сетки (для калибровки углов). Потом очистишь для замера 'пусто'.")

    pts = {}
    pts["autofill"] = cap(win, "Автозаполнение", "кнопка 'Автозаполнение'")
    pts["confirm"] = cap(win, "Подтвердить", "кнопка подтверждения (иконка 'предметы -> меч')")
    pts["grid_tl"] = cap(win, "Сетка ЛЕВ-ВЕРХ", "ЦЕНТР левой-верхней ячейки 3x3")
    pts["grid_br"] = cap(win, "Сетка ПРАВ-НИЗ", "ЦЕНТР правой-нижней ячейки 3x3")
    pts["return_btn"] = cap(win, "Вернуть", "кнопка 'вернуть' (стрелка-возврат, предметы из куба -> в инвентарь)")

    size = CFG["grid_cell_capture_size"]
    print("\n[Пусто] Нажми в игре 'вернуть' (грид опустеет), наведи курсор куда угодно и нажми F9...")
    wait_key("f9")
    gx = win.left + pts["grid_tl"]["rx"] * win.width
    gy = win.top + pts["grid_tl"]["ry"] * win.height
    empty_b = brightness(gx - size / 2, gy - size / 2, size)
    print(f"  Яркость пустой ячейки: {empty_b:.1f}")

    cal = {
        "window_title_used": win.title,
        "win_rect_at_cal": {"left": win.left, "top": win.top, "width": win.width, "height": win.height},
        "points": pts,
        "grid_cell_capture_size": size,
        "empty_brightness": empty_b,
    }
    json.dump(cal, open(CAL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nСОХРАНЕНО: {CAL_PATH}")
    print("Дальше:  python clicker.py   (DRY-RUN — посчитает X/9, без кликов)")
    print("\nОкно можно закрыть.")


if __name__ == "__main__":
    main()
