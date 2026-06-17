r"""calibrate_records.py — МАСТЕР-КАЛИБРАТОР всей игры (лог RECORDS + сундук). Видимая консоль,
пошагово. Наводишь курсор на элемент В ИГРЕ → F8. Координаты пишутся как ДОЛИ окна игры (rx,ry) →
устойчиво к перемещению/масштабу. Esc — отмена секции, S — пропустить точку.

Запуск (видимое окно):
  .\.venv\Scripts\python.exe calibrate_records.py            (всё: лог + сундук)
  .\.venv\Scripts\python.exe calibrate_records.py records    (только лог RECORDS)
  .\.venv\Scripts\python.exe calibrate_records.py chest       (только сундук)

Результат: records_calibration.json, chest_calibration.json.
Панели (инвентарь/куб/тайник) — отдельно баннер-методом: calibrate_all.py → offsets.json.
"""
import json
import os
import sys
import time

import logwatch

HERE = os.path.dirname(os.path.abspath(__file__))


def _win():
    w = logwatch.find_game_window()
    if not w:
        print("❌ Окно игры не найдено. Запусти игру и выведи на экран."); sys.exit(1)
    return w


def _wait_key():
    import keyboard
    while True:
        ev = keyboard.read_event()
        if ev.event_type == "down":
            if ev.name == "esc":
                return "cancel"
            if ev.name == "s":
                return "skip"
            if ev.name == "enter":
                return "done"
            if ev.name == "f8":
                time.sleep(0.12); return "ok"


def _frac(w, prompt):
    import pyautogui
    print(f"  ▸ {prompt}\n      [F8 снять | S пропустить | Esc отмена секции]")
    a = _wait_key()
    if a == "cancel":
        return "cancel"
    if a == "skip":
        print("      (пропущено)"); return None
    x, y = pyautogui.position()
    rx, ry = (x - w.left) / w.width, (y - w.top) / w.height
    print(f"      ✓ ({rx:.4f}, {ry:.4f})  экран=({x},{y})")
    return [round(rx, 4), round(ry, 4)]


def _load(path):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(path, data):
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  💾 {os.path.basename(path)}")


def section_records(w):
    print("\n" + "=" * 64 + "\nСЕКЦИЯ: ЛОГ RECORDS (для 100% точного счёта сундуков/дропа)\n" + "=" * 64)
    print("СОСТОЯНИЯ лога (калибруем в ПОЛНОМ): 0 не видно · 1 строка · ~5 средний · ~17 РАЗВЁРНУТ+ЗАКРЕПЛЁН.")
    print("Подготовь игру В ПОЛНОМ СОСТОЯНИИ:")
    print("  1) ОТКРОЙ лог RECORDS (игровая шестерёнка Settings → Pin Log Window).")
    print("  2) РАЗВЕРНИ его кнопкой ⛶ до МАКСИМУМА строк (~17).")
    print("  3) HERO/инвентарь ЗАКРОЙ (при открытом HERO рамки RECORDS нет!).")
    input("Лог развёрнут на максимум + закреплён + HERO закрыт? Enter...")
    path = os.path.join(HERE, "records_calibration.json")
    cal = _load(path)
    # контролы пути (как ДОВЕСТИ лог до полного состояния — бот будет их жать сам)
    for key, prompt in [
        ("game_settings", "ИГРОВАЯ шестерёнка Settings (верх-право игры) — открывает Настройки"),
        ("log_open", "тумблер «Pin Log Window» внутри Настроек — открыть/закрепить лог"),
        ("rec_expand", "кнопка ⛶ РАЗМЕРА лога в шапке RECORDS — ОДНА кнопка-тоггл (свернуть/развернуть). "
                       "Сейчас лог развёрнут → на ней «Свернуть» — её и снимай. (Наведись на лог — шапка появится)"),
        ("rec_gear", "шестерёнка ⚙ самого RECORDS — можно S-пропустить"),
    ]:
        p = _frac(w, prompt)
        if p == "cancel":
            print("  ⏹ отмена секции."); _save(path, cal); return
        if p:
            cal[key] = {"rx": p[0], "ry": p[1]}
    # КАЖДАЯ СТРОКА развёрнутого лога — точный регион (ты просил прокликать все)
    print("\n  Теперь прокликай КАЖДУЮ строку развёрнутого лога СВЕРХУ ВНИЗ:")
    print("  F8 на центр каждой строки. Когда все сняты — Enter. (Esc — отмена)")
    rows = []
    while True:
        import pyautogui
        a = _wait_key()
        if a == "cancel":
            print("  ⏹ отмена строк."); break
        if a == "done":
            break
        x, y = pyautogui.position()
        rx, ry = round((x - w.left) / w.width, 4), round((y - w.top) / w.height, 4)
        rows.append({"rx": rx, "ry": ry})
        print(f"    строка {len(rows)}: ({rx},{ry})")
    if rows:
        cal["rows"] = rows
        cal["check_first"] = rows[0]
        cal["check_last"] = rows[-1]
        cal["log_rows_n"] = len(rows)
        print(f"  снято строк: {len(rows)}")
    _save(path, cal)
    print("\n  Проверка: считаю видимые строки лога…")
    try:
        import log_setup
        n = log_setup.find_log().get("n", 0)
        print(f"  → строк лога: {n}  ({'МНОГОСТРОЧНЫЙ ✓ — счёт будет точным' if n >= 4 else 'мало: проверь разворот/HERO закрыт'})")
    except Exception as e:
        print(f"  (проверку пропустил: {e!r})")


def section_chest(w):
    print("\n" + "=" * 64 + "\nСЕКЦИЯ: СУНДУК (детект авто-открытия «A»)\n" + "=" * 64)
    print("В стоке должен быть СУНДУК (значок «A» вылазит при наведении на иконку).")
    input("Готово? Enter...")
    path = os.path.join(HERE, "chest_calibration.json")
    cal = _load(path)
    p = _frac(w, "ЦЕНТР иконки СУНДУКА (ховер — будит «A»)")
    if p and p != "cancel":
        cal["chest_hover"] = p
    p = _frac(w, "ЦЕНТР значка «A» (золотой/серый)")
    if p and p != "cancel":
        cal["a_click"] = p
        cal["a_box"] = [round(p[0] - 0.026, 4), round(p[1] - 0.018, 4),
                        round(p[0] + 0.026, 4), round(p[1] + 0.018, 4)]
    _save(path, cal)


SECTIONS = {"records": section_records, "chest": section_chest}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    w = _win()
    print(f"Окно игры: left={w.left} top={w.top} w={w.width} h={w.height}\n")
    which = [a for a in sys.argv[1:] if a in SECTIONS]
    for name in (which or ["records", "chest"]):
        try:
            SECTIONS[name](w)
        except SystemExit:
            raise
        except Exception as e:
            print(f"  [секция {name}] ошибка: {e!r}")
    # размер окна → гейт калибровки (calibration.py) валидирует, что доли окна сняты на ЭТОМ окне
    for fn in ("records_calibration.json", "chest_calibration.json"):
        p = os.path.join(HERE, fn)
        if os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
                d["calib_window"] = {"w": int(w.width), "h": int(w.height)}
                _save(p, d)
            except Exception:
                pass
    print("\n✅ Калибровка завершена. Панели (инвентарь/куб/тайник) — calibrate_all.py.")
    try:
        input("\nEnter — закрыть окно.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
