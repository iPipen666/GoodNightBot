"""dismiss_offline.py — закрыть попап OFFLINE REWARDS / награды за офлайн, который игра показывает
ПОСЛЕ запуска (в т.ч. после авто-перезапуска watchdog'ом). Если попап висит — бот не может
перелить инвентарь в тайник и зацикливается. Детект по OCR (только если попап реально есть —
иначе НЕ кликаем, чтоб не тыкать в игровой мир). Кнопка «Закрыть» ~по центру окна, ~68% высоты.
Вызывается watchdog'ом в StartGame ДО старта панели (без гонки с фарм-петлёй)."""
import json
import time
import sys

try:
    import human
    import logwatch
except Exception as e:
    print("import err:", e); sys.exit(0)

KW = ("offline", "reward", "офлайн", "закрыть", "rewards", "награ")


def main():
    try:
        cfg = json.load(open("config.json", encoding="utf-8"))
    except Exception:
        cfg = {}
    w = logwatch.find_game_window()
    if not w:
        print("no game window"); return
    # до 3 попыток (попап может проявиться с задержкой после загрузки)
    for attempt in range(3):
        try:
            txt = (logwatch.ocr(logwatch.grab(w)) or "").lower()
        except Exception:
            txt = ""
        if any(k in txt for k in KW):
            cx = int(w.left + 0.50 * w.width)
            cy = int(w.top + 0.676 * w.height)
            try:
                human.move_abs(cx, cy); time.sleep(0.3)
                human.click(cx, cy, cfg)
                print("dismissed offline popup @%d,%d (attempt %d)" % (cx, cy, attempt + 1))
            except Exception as e:
                print("click err:", e)
            time.sleep(2.0)
            w = logwatch.find_game_window() or w
        else:
            print("no offline popup (attempt %d)" % (attempt + 1))
            return
    print("done")


if __name__ == "__main__":
    main()
