"""TBH — тайник: 'Сохранить всё' (инвентарь -> тайник) / 'Забрать всё' (тайник -> инвентарь).

Освобождает слоты инвентаря, чтобы ночной фарм не упирался в полный инвентарь.
Самокалибрующийся: при первом запуске просит навести курсор (F8) на кнопки —
нужна ОТКРЫТАЯ панель STASH. Координаты — относительно окна игры.

Usage:
  python stash.py save            # один раз: инвентарь -> тайник
  python stash.py take            # один раз: тайник -> инвентарь
  python stash.py save --loop 300 # каждые 300 сек жать 'Сохранить всё' (для ночного фарма)

Хоткей-калибровка: F8 — записать точку, Esc — отмена. Стоп цикла: F12.
"""
import json
import os
import sys
import time
import random
import ctypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import pyautogui
import pygetwindow as gw

pyautogui.FAILSAFE = True

import human

try:
    import keyboard

    def kill():
        try:
            return keyboard.is_pressed("f12")
        except Exception:
            return False

    def wait_f8():
        while True:
            ev = keyboard.read_event()
            if ev.event_type == "down":
                if ev.name == "esc":
                    print("Отмена."); sys.exit(1)
                if ev.name == "f8":
                    time.sleep(0.25); return
    HAVE_KB = True
except Exception:
    HAVE_KB = False

    def kill():
        return False

    def wait_f8():
        input("  [keyboard недоступен] клик в это окно + Enter...")

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
SCAL = os.path.join(HERE, "stash_calibration.json")


def find_window():
    for w in gw.getAllWindows():
        t = w.title or ""
        if t and any(s.lower() in t.lower() for s in CFG["window_title_contains"]) and w.width > 100:
            return w
    return None


def click_at(x, y, size=None):
    human.click(x, y, CFG, size=size)


def calibrate(win):
    print("=== Калибровка кнопок тайника (нужна ОТКРЫТАЯ панель STASH) ===")
    pts = {}
    for key, label in [("save_all", "Сохранить всё"), ("take_all", "Забрать всё")]:
        print(f"\n[{label}] наведи курсор на кнопку '{label}' и нажми F8 (Esc — отмена)")
        wait_f8()
        x, y = pyautogui.position()
        pts[key] = {"rx": (x - win.left) / win.width, "ry": (y - win.top) / win.height}
        print(f"  OK ({x},{y}) -> ({pts[key]['rx']:.4f}, {pts[key]['ry']:.4f})")
    json.dump({"points": pts}, open(SCAL, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Сохранено: {SCAL}")
    return pts


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("save", "take"):
        print("Usage: python stash.py save|take [--loop SECONDS]")
        sys.exit(1)
    action = sys.argv[1]
    loop_sec = None
    if "--loop" in sys.argv:
        try:
            loop_sec = float(sys.argv[sys.argv.index("--loop") + 1])
        except Exception:
            print("--loop требует число секунд"); sys.exit(1)

    dry = CFG.get("dry_run", True)
    if "--live" in sys.argv:
        dry = False
    if "--dry" in sys.argv:
        dry = True
    win = find_window()
    if not win:
        print("Окно игры не найдено."); sys.exit(1)

    if os.path.exists(SCAL):
        pts = json.load(open(SCAL, encoding="utf-8"))["points"]
    else:
        pts = calibrate(win)

    key = "save_all" if action == "save" else "take_all"
    label = "Сохранить всё" if action == "save" else "Забрать всё"

    def do_once():
        w = find_window()
        if not w:
            print("окно пропало"); return
        x = w.left + pts[key]["rx"] * w.width
        y = w.top + pts[key]["ry"] * w.height
        if dry:
            print(f"DRY: '{label}' @ ({x:.0f},{y:.0f}) [не кликаю]")
        else:
            click_at(x, y)
            print(f"Клик '{label}'.")

    print(f"=== stash.py {action} | {'DRY-RUN' if dry else 'LIVE'} | "
          f"{'loop '+str(loop_sec)+'s' if loop_sec else 'один раз'} ===")
    print("Панель STASH должна быть открыта. Стоп цикла: F12.")
    for i in (3, 2, 1):
        print(f"  старт через {i}..."); time.sleep(1)

    if not loop_sec:
        do_once()
    else:
        while True:
            if kill():
                print("F12 — стоп."); break
            do_once()
            # дробим сон, чтобы F12 ловился быстро
            slept = 0.0
            while slept < loop_sec:
                if kill():
                    break
                time.sleep(1.0); slept += 1.0
    print("Готово.")


if __name__ == "__main__":
    main()
