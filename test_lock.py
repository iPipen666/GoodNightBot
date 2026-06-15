r"""test_lock.py — СИНТЕТИК-ТЕСТ F11: бот РАЗОВО лочит один предмет (Alt+клик при ЗАКРЫТОМ кубе)
и печатает, какой именно. Юзер смотрит в игре и подтверждает, появился ли значок замка.
Реверсивно: повторный запуск снимет лок (Alt+клик — это переключатель).

Запуск:  $env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe test_lock.py
Стоп:    F12 / курсор в левый-верхний угол (failsafe). Окно игры должно быть видимым.
"""
import time

import numpy as np
import mss

import farm
import items
import human


def main():
    print("→ вывожу игру вперёд…")
    if not farm.ensure_game_foreground(force=True):
        print("✖ окно игры не найдено / не вышло вперёд. Открой игру и повтори.")
        return

    with mss.mss() as sct:
        farm.ensure_inventory_tab(sct)                 # HERO → вкладка Inventory (не Formation)
        win, panels = farm.detect(sct)

        if "cube" in panels:
            print("✖ КУБ ОТКРЫТ — при открытом кубе Alt+клик кладёт предмет В куб, а не лочит.")
            print("  Закрой куб (Синтез) и запусти снова.")
            return
        hero = panels.get("hero")
        if not hero:
            print("✖ панель HERO/инвентарь не открыта. Открой инвентарь героя и повтори.")
            return

        cells = farm.grid_centers(hero, "hero", "inv_tl", "inv_br", farm.INV["cols"], farm.HERO_ROWS)
        s = farm.CFG.get("grid_cell_capture_size", 44)
        target = None
        for r, c, x, y in cells:
            crop = np.array(sct.grab({"left": int(x - s / 2), "top": int(y - s / 2),
                                      "width": s, "height": s}))[:, :, :3]
            if float(crop.mean()) >= farm.SLOT_FILL_THR:
                target = (r, c, x, y)
                break
        if not target:
            print("✖ занятых слотов в инвентаре не найдено (инвентарь пуст?).")
            return

        r, c, x, y = target
        print(f"→ цель: первый занятый слот r{r}c{c} @ ({x},{y}). Читаю тултип…")
        item = items.read_item(sct, (x, y), flip="left")    # HERO → тултип влево
        name = item.get("db_name") or item.get("name") or "(имя не распозналось)"
        rank = item.get("rank") or "(грейд не прочитан)"
        typ = item.get("type") or "?"
        part = item.get("part_ru")
        tdesc = typ + (f"/{part}" if part else "")

        print(f"→ предмет: «{name}» | грейд: {rank} | тип: {tdesc}")
        print("→ Alt+клик по слоту (ЛОК)…")
        human.click(x, y, farm.CFG, button="left", mod="alt")
        time.sleep(0.4)
        human.park()

        print()
        print("=" * 56)
        print(f"✅ ГОТОВО. Кликнул Alt+ЛКМ по «{name}»")
        print(f"   слот r{r}c{c}, грейд {rank}, тип {tdesc}")
        print("   → Посмотри в игре: на этом предмете должен появиться ЗНАЧОК ЗАМКА.")
        print("   (если он уже был залочен — замок СНИМЕТСЯ; запусти ещё раз — вернётся)")
        print("=" * 56)


if __name__ == "__main__":
    main()
