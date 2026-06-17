r"""calibrate_master.py — ЕДИНЫЙ мастер-калибратор всего UI (anchor-relative, см. ADR 0002).

Меряем КАЖДУЮ контрольную точку как смещение от ЯКОРЯ (баннер панели или икона), нормированное на
ширину якоря → пишем offsets.json. Меряется ОДИН РАЗ (нами) → шипится универсально, юзер в норме не
калибрует ничего (баннер детектится сам).

Запуск (игра видима/foreground):  .\.venv\Scripts\python.exe calibrate_master.py [секция ...]
Без аргументов — все секции по порядку. Управление: курсор на элемент + F8 снять · S пропустить ·
N следующая секция · Esc выход. Перед каждой секцией скрипт говорит, что открыть в игре.

Якорь: баннер (vision.detect по имени секции) ИЛИ икона (vision.find_anchor по шаблону) для лога/
сундука (у них нет баннера). Смещение = vision.norm_offset(anchor, x, y).
"""
import json
import os
import sys
import time

import logwatch
import vision

HERE = os.path.dirname(os.path.abspath(__file__))
OFFS = os.path.join(HERE, "offsets.json")

# Спец-шаги: ("@msg", "текст-инструкция") — не снимаем точку, просто ждём Enter (напр. «прокрути карту»).
SECTIONS = [
    {"key": "hero", "anchor": {"banner": "hero"},
     "open": "Открой HERO (инвентарь героя). STATUS/PORTAL закрой, чтобы баннер HERO читался чисто.",
     "points": [
         ("close", "ЗАКРЫТЬ ✕ панели HERO (мелкий крестик справа вверху)"),
         ("inv_sort", "кнопка СОРТИРОВАТЬ предметы (у вкладки «Инвентарь»)"),
         ("open_settings", "шестерёнка ⚙ панели HERO"),
         ("inv_tab", "вкладка «Инвентарь»"),
         ("inv_tl", "ЦЕНТР ЛЕВОЙ-ВЕРХНЕЙ ячейки инвентаря (7×3)"),
         ("inv_br", "ЦЕНТР ПРАВОЙ-НИЖНЕЙ ячейки инвентаря"),
         ("open_stash", "кнопка ряда: открыть ТАЙНИК (сундук)"),
         ("open_cube", "кнопка ряда: открыть КУБ"),
         ("open_portal", "кнопка ряда: открыть PORTAL (крайняя правая)"),
         ("open_mail", "кнопка ряда: открыть ПОЧТУ"),
     ]},
    {"key": "status", "anchor": {"banner": "status"},
     "open": "Открой STATUS (характеристики).",
     "points": [
         ("close", "ЗАКРЫТЬ ✕ панели STATUS"),
         ("details_expand", "строка/кнопка «Подробные характеристики»"),
     ]},
    {"key": "cube", "anchor": {"banner": "cube"},
     "open": "Открой КУБ (Синтез).",
     "points": [
         ("close", "ЗАКРЫТЬ ✕ панели КУБ"),
     ]},
    {"key": "stash", "anchor": {"banner": "stash"},
     "open": "Открой ТАЙНИК.",
     "points": [
         ("close", "ЗАКРЫТЬ ✕ панели ТАЙНИК"),
     ]},
    {"key": "mail", "anchor": {"banner": "mail"},
     "open": "Открой ПОЧТУ.",
     "points": [
         ("close", "ЗАКРЫТЬ ✕ панели ПОЧТА"),
     ]},
    {"key": "portal", "anchor": {"banner": "portal"},
     "open": "Открой PORTAL на ПРОЙДЕННОМ Акте 1 (чтобы карта скроллилась по всем этапам).",
     "points": [
         ("close", "ЗАКРЫТЬ ✕ панели PORTAL"),
         ("diff_dropdown", "ДРОПДАУН СЛОЖНОСТИ (надпись «Мучение ▾» вверху)"),
         ("@msg", "Кликни по дропдауну сложности в игре, чтобы он РАСКРЫЛСЯ."),
         ("diff_option_normal", "опция «Обычный»"),
         ("diff_option_nightmare", "опция «Кошмар»"),
         ("diff_option_hell", "опция «Ад»"),
         ("diff_option_torment", "опция «Мучение»"),
         ("act_tab_1", "таб «Акт 1»"),
         ("act_tab_2", "таб «Акт 2»"),
         ("act_tab_3", "таб «Акт 3»"),
         ("scroll_anchor", "ЦЕНТР карты этапов (над ним крутят колесо)"),
         ("@msg", "Прокрути карту колесом в САМЫЙ НИЗ (этапы 1–7). Затем снимай узлы снизу вверх."),
         ("node_1", "узел этапа 1 (нижний)"), ("node_2", "узел этапа 2"),
         ("node_3", "узел этапа 3"), ("node_4", "узел этапа 4"),
         ("node_5", "узел этапа 5"), ("node_6", "узел этапа 6"), ("node_7", "узел этапа 7"),
         ("@msg", "Прокрути карту в САМЫЙ ВЕРХ (этапы 8–10). Снимай сверху вниз."),
         ("node_10", "узел этапа 10 (верхний)"), ("node_9", "узел этапа 9"),
         ("node_8", "узел этапа 8"),
     ]},
    {"key": "log", "anchor": {"icon": "templates/records_expand.png"},
     "open": "Закрой HERO/STATUS/КУБ. Наведи курсор в область ЛОГА — появится рамка RECORDS с ⛶.\n"
             "  (Якорь лога — иконка ⛶ «развернуть». Держи лог раскрытым/закреплённым.)",
     "points": [
         ("rec_expand", "иконка ⛶ РАЗВЕРНУТЬ в шапке RECORDS (это и есть якорь)"),
         ("rec_gear", "шестерёнка ⚙ самого RECORDS"),
         ("log_field", "ЦЕНТР области строк лога (зона OCR)"),
         ("row_first", "ЦЕНТР ВЕРХНЕЙ строки лога"),
         ("row_last", "ЦЕНТР НИЖНЕЙ строки лога"),
     ]},
    {"key": "chest", "anchor": {"icon": "templates/chests/normal.png"},
     "open": "В стоке должен быть СУНДУК (значок «A» вылазит при наведении). Якорь — иконка сундука.",
     "points": [
         ("chest_hover", "ЦЕНТР иконки СУНДУКА (будит «A»)"),
         ("a_click", "ЦЕНТР значка «A» (золотой/серый)"),
     ]},
]


def _win():
    w = logwatch.find_game_window()
    if not w:
        print("❌ Окно игры не найдено. Запусти игру."); sys.exit(1)
    return w


def _wait():
    import keyboard
    while True:
        ev = keyboard.read_event()
        if ev.event_type != "down":
            continue
        if ev.name == "esc":
            return "quit"
        if ev.name == "s":
            return "skip"
        if ev.name == "n":
            return "next"
        if ev.name == "f8":
            time.sleep(0.12); return "ok"


def _detect_anchor(section, win, sct):
    """Якорь секции: баннер (detect) или икона (find_anchor) → {cx,cy,w} ЭКРАН, иначе None."""
    a = section["anchor"]
    if a.get("banner"):
        det = vision.detect(win, sct, names=[a["banner"]])
        return det.get(a["banner"])
    tpl = os.path.join(HERE, a["icon"])
    r = vision.find_anchor(win, sct, tpl)
    if not r:
        return None
    left, top, w, h, _ = r
    return {"cx": left + w / 2, "cy": top + h / 2, "w": w}


def _load():
    try:
        return json.load(open(OFFS, encoding="utf-8"))
    except Exception:
        return {}


def _save(off):
    json.dump(off, open(OFFS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def run_section(section, win, sct, off):
    print("\n" + "=" * 66)
    print(f"СЕКЦИЯ «{section['key']}» — {section['open']}")
    print("=" * 66)
    input("Открыто/готово? Enter (или Ctrl-C выход)…")
    anchor = _detect_anchor(section, win, sct)
    if not anchor:
        print(f"  ⚠ якорь секции «{section['key']}» НЕ найден (баннер/икона не на экране). Пропуск.")
        return True
    print(f"  ✓ якорь: центр=({int(anchor['cx'])},{int(anchor['cy'])}) ширина={int(anchor['w'])}")
    sec = off.setdefault(section["key"], {})
    if section["anchor"].get("icon"):
        sec["_anchor"] = {"icon": section["anchor"]["icon"]}
    for name, prompt in section["points"]:
        if name == "@msg":
            input(f"  ▸ {prompt}\n    Enter когда готово…")
            continue
        print(f"  ▸ {prompt}\n      [F8 снять · S пропустить · N следующая секция · Esc выход]")
        a = _wait()
        if a == "quit":
            _save(off); print("выход."); sys.exit(0)
        if a == "next":
            _save(off); return True
        if a == "skip":
            print("      (пропущено)"); continue
        import pyautogui
        x, y = pyautogui.position()
        # передетект якоря (точнее: окно/панель могли чуть сместиться между шагами)
        fresh = _detect_anchor(section, win, sct) or anchor
        ox, oy = vision.norm_offset(fresh, x, y)
        sec[name] = [round(ox, 4), round(oy, 4)]
        _save(off)
        print(f"      ✓ {name} = [{sec[name][0]}, {sec[name][1]}]  (offset·ширина_якоря)")
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    win = _win()
    import mss
    sct = mss.mss()
    print(f"Окно игры: {win.width}x{win.height}. Якоря детектятся автоматически.")
    which = [a for a in sys.argv[1:] if any(s["key"] == a for s in SECTIONS)]
    secs = [s for s in SECTIONS if not which or s["key"] in which]
    off = _load()
    for s in secs:
        run_section(s, win, sct, off)
    _save(off)
    print(f"\n💾 Сохранено в offsets.json (banner/icon-relative). Секций: {len(secs)}.")
    try:
        input("Enter — закрыть.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
