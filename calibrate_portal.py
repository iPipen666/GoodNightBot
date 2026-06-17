r"""calibrate_portal.py — калибратор окна PORTAL для stagenav (прыжки по стадиям).
Наводишь курсор на элемент В ИГРЕ → F8. Координаты — ДОЛИ окна игры (rx,ry) → устойчиво к
масштабу/позиции. S пропустить точку, Esc отмена. Результат: portal_calibration.json.

Запуск (видимое окно игры, открой PORTAL):
  .\.venv\Scripts\python.exe calibrate_portal.py

КАРТА СКРОЛЛИТСЯ, узлы на экране одинаковы для всех актов → калибруем ОДИН РАЗ (не по актам):
  1) кнопка открытия PORTAL, дропдаун сложности, 4 опции (раскрой дропдаун!), 3 таба актов;
  2) scroll_anchor — точка в ЦЕНТРЕ карты (над ней крутим колесо);
  3) nodes_bottom — прокрути карту В САМЫЙ НИЗ, снимай узлы СНИЗУ ВВЕРХ (нижний = этап 1);
  4) nodes_top    — прокрути карту В САМЫЙ ВЕРХ, снимай узлы СВЕРХУ ВНИЗ (верхний = этап 10).
Этапы 1-7 берутся со страницы «низ», 8-10 — со страницы «верх» (4-7 есть на обеих, не важно).
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


def _save(cal):
    json.dump(cal, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# Ключи, без которых хоп-навигация не полна (portal_open НЕ нужен — карту открывает
# offsets.hero.open_portal, не калибровка). Должно совпадать с stagenav.REQUIRED_KEYS.
REQUIRED = ["diff_dropdown", "diff_option_normal", "diff_option_nightmare", "diff_option_hell",
            "diff_option_torment", "act_tab_1", "act_tab_2", "act_tab_3", "scroll_anchor"]


def _report(cal):
    """Печатает, полна ли калибровка (для обязательного first-run прогона)."""
    miss = [k for k in REQUIRED if k not in cal]
    nb = {int(n.get("no", -1)) for n in cal.get("nodes_bottom", [])}
    nt = {int(n.get("no", -1)) for n in cal.get("nodes_top", [])}
    if not (set(range(1, 8)) <= nb):
        miss.append("nodes_bottom 1-7 (есть: %s)" % sorted(nb))
    if not ({8, 9, 10} <= nt):
        miss.append("nodes_top 8-10 (есть: %s)" % sorted(nt))
    if miss:
        print("⚠ КАЛИБРОВКА НЕ ПОЛНА — хоп работать НЕ будет. Не снято:")
        for m in miss:
            print("    •", m)
        print("  Перезапусти calibrate_portal.py и сними недостающее.")
    else:
        print("✅ Калибровка ПОЛНА — хоп можно включать.")
    return not miss


def main():
    w = _win()
    cal = {}
    if os.path.exists(PATH):
        try:
            cal = json.load(open(PATH, encoding="utf-8"))
        except Exception:
            cal = {}
    cal.pop("stage_nodes", None)                       # легаси per-act схема больше не нужна

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
        ("scroll_anchor", "ЦЕНТР карты этапов (над ним бот крутит колесо)"),
    ]
    for key, prompt in simple:
        r = _frac(w, prompt)
        if r == "cancel":
            print("отмена."); _save(cal); return
        if r:
            cal[key] = r
        _save(cal)

    # Узлы — две страницы (низ: этапы 1..7, верх: этапы 10..). Позиции общие для всех актов.
    for page, lo_hi in (("bottom", "В САМЫЙ НИЗ, снимай СНИЗУ ВВЕРХ (нижний = этап 1)"),
                        ("top", "В САМЫЙ ВЕРХ, снимай СВЕРХУ ВНИЗ (верхний = этап 10)")):
        print(f"\n--- Узлы (страница {page}): прокрути карту {lo_hi}; S=хватит ---")
        nodes = []
        seq = range(1, 8) if page == "bottom" else range(10, 3, -1)
        for no in seq:
            arrow = "снизу-вверх" if page == "bottom" else "сверху-вниз"
            r = _frac(w, f"Узел этапа [{no}] ({arrow}; S если узлы кончились)")
            if r == "cancel":
                _save(cal); return
            if r is None:
                break
            nodes.append({"no": no, "rx": r["rx"], "ry": r["ry"]})
        if nodes:
            cal["nodes_%s" % page] = nodes
            _save(cal)
    # размер окна, на котором снято — гейт в stagenav откажет на другом окне (доли окна непортативны)
    cal["calib_window"] = {"w": int(w.width), "h": int(w.height)}
    _save(cal)
    print(f"\n💾 Сохранено: {PATH}  (окно {w.width}x{w.height})")
    _report(cal)


if __name__ == "__main__":
    main()
