"""setup_log.py — самопроверочная подготовка лога RECORDS к работе. Делает то, что юзер требует:
бот стартует → проверяет открыт/развёрнут ли лог → нет? → выводит игру вперёд → идёт в Настройки →
закрепляет лог → наводится на область лога → проявляет рамку RECORDS → жмёт ⛶ разворот до максимума →
проверяет что максимум → готово. Каждый шаг логируется и (в inspect) снимает скриншот с маркерами.

Запуск:
  venv python setup_log.py            # боевой: реально кликает, доводит лог до развёрнутого
  venv python setup_log.py --inspect  # без кликов: фокус+скриншот+маркеры калибровки, для сверки
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

import logwatch
import log_setup
import records_ctl
import farm

INSPECT = "--inspect" in sys.argv


def cfg():
    try:
        return json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    except Exception:
        return {}


def shot(name, marks=None):
    """Снять кадр игры, нарисовать маркеры (screen-точки) и сохранить _attic/<name>.png."""
    from PIL import Image, ImageDraw
    w = logwatch.find_game_window()
    if not w:
        print("  [shot] нет окна"); return
    fr = logwatch.grab(w)
    import numpy as np
    im = Image.fromarray(np.asarray(fr)).convert("RGB")
    d = ImageDraw.Draw(im)
    for label, (sx, sy) in (marks or {}).items():
        fx, fy = sx - w.left, sy - w.top
        d.ellipse([fx - 12, fy - 12, fx + 12, fy + 12], outline=(255, 0, 0), width=3)
        d.text((fx + 14, fy - 6), label, fill=(255, 0, 0))
    p = os.path.join(HERE, "_attic", name)
    im.save(p)
    print(f"  [shot] {p}")


def main():
    c = cfg()
    w = logwatch.find_game_window()
    print("окно игры:", None if not w else (w.left, w.top, w.width, w.height))
    if not w:
        sys.exit("игра не запущена")

    # ── ШАГ 1: вывести игру вперёд (UI игры виден только в foreground) ───────────────────────
    print("\n[1] focus_game…")
    farm.focus_game()
    time.sleep(0.8)
    print("    foreground:", logwatch.is_game_foreground())

    # калиброванные точки настроек/лога (для маркеров и кликов)
    cal = records_ctl._cal()
    gs = records_ctl._screen("game_settings", cal)
    lo = records_ctl._screen("log_open", cal)
    print("    game_settings →", gs, "| log_open →", lo)

    # ── ШАГ 2: проверить текущее состояние лога ──────────────────────────────────────────────
    print("\n[2] состояние лога ДО:")
    r0 = log_setup.find_log()
    n0 = r0.get("n", 0)
    print(f"    find_log n={n0}  ({log_setup.state_name(n0)})")

    if INSPECT:
        shot("focused.png", marks={"GEAR": gs, "LOG_TOGGLE": lo} if (gs and lo) else None)
        print("\n[inspect] клики НЕ делались. Сверь focused.png: красные кружки = калиброванные точки.")
        return

    # ── ШАГ 3: если лог не виден достаточно — открыть через Настройки ─────────────────────────
    if n0 < 1:
        print("\n[3] лог закрыт → открываю через Настройки (focus+gear+toggle+esc)…")
        ok, opened = records_ctl.ensure_ready(c, log=lambda m: print("    ", m), expand=False)
        time.sleep(0.6)
        n1 = log_setup.find_log().get("n", 0)
        print(f"    после открытия: n={n1}")
    else:
        print("\n[3] лог уже виден (n>=1) — Настройки не трогаю")

    # ── ШАГ 4: развернуть на максимум (hover → ⛶ ×N с проверкой роста) ────────────────────────
    print("\n[4] разворот до максимума (pin_and_expand, до 4 проходов с проверкой роста)…")
    prev = -1
    for i in range(4):
        farm.focus_game(); time.sleep(0.3)
        records_ctl.pin_and_expand(c, log=lambda m: print(f"    [{i}]", m))
        n = log_setup.find_log().get("n", 0)
        print(f"    проход {i}: n={n}")
        if n <= prev:                 # рост остановился → максимум достигнут (или не растёт)
            break
        prev = n

    # ── ШАГ 5: финальная проверка ────────────────────────────────────────────────────────────
    nf = log_setup.find_log().get("n", 0)
    print(f"\n[5] ИТОГ: n={nf}  ({log_setup.state_name(nf)})")
    print("    " + ("✅ лог развёрнут, можно работать" if nf >= 8 else
                    "⚠ лог НЕ развёрнут до максимума — см. expand_diag.log"))
    shot("after_setup.png")


if __name__ == "__main__":
    main()
