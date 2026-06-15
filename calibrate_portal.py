r"""calibrate_portal.py — калибратор окна PORTAL для stagenav (прыжки по стадиям).
Наводишь курсор на элемент В ИГРЕ → F8. Координаты — ДОЛИ окна игры (rx,ry) → устойчиво к
масштабу/позиции. S пропустить точку, Esc отмена. Результат: portal_calibration.json.

Запуск (видимое окно игры, открой PORTAL):
  .\.venv\Scripts\python.exe calibrate_portal.py

Порядок: открой PORTAL в игре. Снимем: кнопку открытия PORTAL, дропдаун сложности, 4 опции
сложности (раскрой дропдаун!), 3 таба актов, затем по каждому акту — узлы этапов 1..N сверху-вниз.
"""
import json
import os
import sys
import time

import logwatch

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "portal_calibration.json")


def _win():
    w = logwatch.find_game_window()
    if not w:
        print("❌ Окно игры не найдено. Запусти игру."); sys.exit(1)
    return w


def _wait():
    import keyboard
    while True:
        ev = keyboard.read_event()
        if ev.event_type == "down":
            if ev.name == "esc":
                return "cancel"
            if ev.name == "s":
                return "skip"
            if ev.name == "f8":
                time.sleep(0.12); return "ok"


def _frac(w, prompt):
    import pyautogui
    print(f"  ▸ {prompt}\n      [F8 снять | S пропустить | Esc стоп]")
    a = _wait()
    if a == "cancel":
        return "cancel"
    if a == "skip":
        print("      (пропущено)"); return None
    x, y = pyautogui.position()
    rx, ry = round((x - w.left) / w.width, 4), round((y - w.top) / w.height, 4)
    print(f"      ✓ ({rx}, {ry})  экран=({x},{y})")
    return {"rx": rx, "ry": ry}


def main():
    w = _win()
    cal = {}
    if os.path.exists(PATH):
        try:
            cal = json.load(open(PATH, encoding="utf-8"))
        except Exception:
            cal = {}
    cal.setdefault("stage_nodes", {"1": [], "2": [], "3": []})

    print("=" * 64 + "\nКАЛИБРОВКА PORTAL → stagenav. Открой PORTAL в игре.\n" + "=" * 64)
    simple = [
        ("portal_open", "Кнопка ОТКРЫТЬ PORTAL (в игре)"),
        ("diff_dropdown", "Дропдаун сложности (шапка 'Мучение ▾')"),
        ("diff_option_normal", "Опция 'Обычный' (раскрой дропдаун!)"),
        ("diff_option_nightmare", "Опция 'Кошмар'"),
        ("diff_option_hell", "Опция 'Ад'"),
        ("diff_option_torment", "Опция 'Мучение'"),
        ("act_tab_1", "Таб 'Акт 1'"),
        ("act_tab_2", "Таб 'Акт 2'"),
        ("act_tab_3", "Таб 'Акт 3'"),
    ]
    for key, prompt in simple:
        r = _frac(w, prompt)
        if r == "cancel":
            print("отмена."); break
        if r:
            cal[key] = r
        json.dump(cal, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    for act in ("1", "2", "3"):
        print(f"\n--- Узлы этапов АКТ {act} (открой этот акт; снимай сверху-вниз; S=хватит) ---")
        nodes = []
        i = 1
        while True:
            r = _frac(w, f"Узел этапа {act}-{i} (или S если узлы кончились/нужен скролл)")
            if r == "cancel" or r is None:
                break
            nodes.append(r)
            i += 1
        if nodes:
            cal["stage_nodes"][act] = nodes
            json.dump(cal, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n💾 Сохранено: {PATH}")


if __name__ == "__main__":
    main()
