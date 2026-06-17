r"""calibrate_logfield.py — снять ОДНУ точку: место КЛИКА для проявления окна RECORDS (поле лога).
Бот кликает сюда после закрытия HERO, чтобы Unity показал лог (ховер Unity не ловит).

Запуск (RECORDS должен быть виден на экране):
  .\.venv\Scripts\python.exe calibrate_logfield.py
Наведи курсор на НИЖНЮЮ строку лога RECORDS → F8. Esc — отмена.
Пишет records_calibration.json: log_field (rx,ry окна игры).
"""
import json
import os
import sys
import time

import logwatch

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "records_calibration.json")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    w = logwatch.find_game_window()
    if not w:
        print("❌ Окно игры не найдено."); sys.exit(1)
    print(f"Окно игры: left={w.left} top={w.top} {w.width}x{w.height}")
    print("\nНаведи курсор на НИЖНЮЮ строку лога RECORDS (или место, где она появляется) → F8.")
    print("[F8 — снять | Esc — отмена]")
    import keyboard
    import pyautogui
    while True:
        ev = keyboard.read_event()
        if ev.event_type != "down":
            continue
        if ev.name == "esc":
            print("отмена."); return
        if ev.name == "f8":
            time.sleep(0.12)
            x, y = pyautogui.position()
            rx, ry = round((x - w.left) / w.width, 4), round((y - w.top) / w.height, 4)
            cal = {}
            if os.path.exists(PATH):
                try:
                    cal = json.load(open(PATH, encoding="utf-8"))
                except Exception:
                    cal = {}
            cal["log_field"] = {"rx": rx, "ry": ry}
            json.dump(cal, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"✓ log_field = ({rx}, {ry})  экран=({x},{y}) → records_calibration.json")
            input("\nГотово. Enter — закрыть.")
            return


if __name__ == "__main__":
    main()
