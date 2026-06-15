"""TBH — калибратор BANNER-RELATIVE смещений (scale/позиция-инвариантно).

Каждая точка хранится как смещение от ЦЕНТРА баннера своей панели, нормированное
на ШИРИНУ баннера (vision.norm_offset). Тогда любой масштаб/Авто-макет/перемещение
окна не ломают координаты — рантайм детектит баннер и считает точки от него.

Управление: F8 — снять | S — пропустить | Esc — отмена.
Открывай нужную панель, когда скрипт попросит. Пишет offsets.json.

Запуск: .\\.venv\\Scripts\\python.exe calibrate_all.py
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
import keyboard
import vision

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
OUTF = os.path.join(HERE, "offsets.json")


def fw():
    for w in gw.getAllWindows():
        t = w.title or ""
        if t and any(s.lower() in t.lower() for s in CFG["window_title_contains"]) and w.width > 100:
            return w
    return None


def wait_key():
    while True:
        ev = keyboard.read_event()
        if ev.event_type == "down":
            if ev.name == "esc":
                return "cancel"
            if ev.name == "s":
                return "skip"
            if ev.name == "f8":
                time.sleep(0.15); return "ok"


def focus_game():
    from ctypes import wintypes
    u = ctypes.windll.user32; res = []

    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h); b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1); c = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, c, 256)
            if any(s.lower() in (b.value or "").lower() for s in CFG["window_title_contains"]) \
                    and "unity" in c.value.lower():
                res.append(h)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    if res:
        u.ShowWindow(res[0], 9); u.SetForegroundWindow(res[0]); u.BringWindowToTop(res[0])
        time.sleep(0.4)


def detect_banner(name):
    """Поймать баннер панели name (vision). Вернуть Panel dict или None."""
    focus_game()
    w = fw()
    with mss.mss() as sct:
        d = vision.detect(w, sct)
    return d.get(name)


def cap(prompt, banner):
    print(f"  • {prompt}\n    [F8 | S-пропуск | Esc-отмена]")
    a = wait_key()
    if a == "cancel":
        print("ОТМЕНА."); sys.exit(1)
    if a == "skip":
        print("    (пропуск)"); return None
    x, y = pyautogui.position()
    ox, oy = vision.norm_offset(banner, x, y)
    print(f"    OK off=({ox:.4f},{oy:.4f}) от баннера (экран {x},{y})")
    return [round(ox, 4), round(oy, 4)]


def phase(title, panel_name):
    print("\n" + "=" * 62 + f"\n{title}\n" + "=" * 62)
    input(f"Открой панель {panel_name.upper()} и Enter (потом наводи курсор в игре)...")
    b = detect_banner(panel_name)
    if not b:
        print(f"[!] Баннер {panel_name} НЕ найден vision'ом. Открыта ли панель? Попробуй ещё раз.")
        input("Enter для повтора детекта...")
        b = detect_banner(panel_name)
        if not b:
            print("Всё ещё нет. Пропускаю фазу."); return None
    print(f"  баннер {panel_name}: центр=({b['cx']},{b['cy']}) ширина={b['w']} масштаб={b['scale']}")
    return b


def main():
    if not fw():
        print("Окно игры не найдено."); sys.exit(1)
    data = json.load(open(OUTF, encoding="utf-8")) if os.path.exists(OUTF) else {}

    # ---- STASH ----
    b = phase("ФАЗА 1 — STASH (по баннеру STASH)", "stash")
    if b:
        st = data.setdefault("stash", {})
        for i in range(1, 6):
            p = cap(f"ЦЕНТР вкладки {i}", b)
            if p: st[f"tab{i}"] = p
        print("  Перейди на вкладку 1.")
        for key, prompt in [("grid_tl", "ЦЕНТР левой-верхней ячейки стэша"),
                            ("grid_br", "ЦЕНТР правой-нижней ячейки сетки стэша"),
                            ("take_all", "кнопка «Забрать всё»"),
                            ("save_all", "кнопка «Сохранить всё»"),
                            ("sort", "кнопка «Сортировать предметы» (≡)")]:
            p = cap(prompt, b)
            if p: st[key] = p
        json.dump(data, open(OUTF, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("  -> offsets.json (stash)")

    # ---- CUBE ----
    b = phase("ФАЗА 2 — CUBE, режим «Синтез» (по баннеру CUBE)", "cube")
    if b:
        cu = data.setdefault("cube", {})
        steps = [("mode_toggle", "выпадашка РЕЖИМА (слева, «Синтез»)"),
                 ("mode_synthesis", "ОТКРОЙ выпадашку режима -> пункт «Синтез»"),
                 ("autofill", "кнопка «Автозаполнение» (закрой список режима сперва)"),
                 ("confirm", "кнопка ПОДТВЕРДИТЬ (предметы→меч, справа внизу)"),
                 ("return_btn", "кнопка «возврат/←» (предметы из куба обратно)"),
                 ("grid_tl", "ЦЕНТР левой-верхней ячейки куба 3x3"),
                 ("grid_br", "ЦЕНТР правой-нижней ячейки куба 3x3"),
                 ("type_toggle", "стрелка-выпадашка ТИПА (справа от «Автозаполнение»)"),
                 ("type_gear", "ОТКРОЙ выпадашку типа -> пункт «Снаряжение»"),
                 ("type_materials", "пункт «Материалы»"),
                 ("type_accessory", "пункт «Аксессуар»")]
        for key, prompt in steps:
            p = cap(prompt, b)
            if p: cu[key] = p
        json.dump(data, open(OUTF, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("  -> offsets.json (cube)")

    # ---- HERO (тогглы открытия) ----
    b = phase("ФАЗА 3 — HERO (ряд круглых кнопок снизу)", "hero")
    if b:
        he = data.setdefault("hero", {})
        steps = [("open_stash", "кнопка-ОТКРЫВАШКА STASH (сундук) в ряду"),
                 ("open_cube", "кнопка-ОТКРЫВАШКА CUBE (куб/синтез) в ряду"),
                 ("inv_sort", "кнопка «Сортировать» в инвентаре HERO (если есть, иначе S)"),
                 ("inv_tl", "ЦЕНТР левой-верхней ячейки инвентаря HERO"),
                 ("inv_br", "ЦЕНТР правой-нижней ячейки инвентаря HERO")]
        for key, prompt in steps:
            p = cap(prompt, b)
            if p: he[key] = p
        json.dump(data, open(OUTF, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("  -> offsets.json (hero)")

    print("\nГОТОВО. offsets.json записан (banner-relative). Скажи Claude — соберёт бота.")


if __name__ == "__main__":
    main()
