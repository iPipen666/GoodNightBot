"""test_logflow.py — ЛОГ-DRIVEN поток (как просил юзер): бот ЧИТАЕТ лог → извлекает ВСЮ инфу
(сундук/дроп/имя/моб/этап) → отдаёт триггеры (что открыть, что упало, что оценить на мерж).
Это оффлайн-тест ИЗВЛЕЧЕНИЯ и накопления; живой OCR-прогон — отдельно на экране.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from logwatch import LogWatcher

fails = []


def ok(name, cond):
    print(("OK  " if cond else "FAIL") + " " + name)
    if not cond:
        fails.append(name)


# ── 1) ВИЖУ СУНДУК В ЛОГЕ → счёт по типу (триггер «открыть») ──
w = LogWatcher()
w.observe(["Получено Старый Меч. [09:59]"])                           # базлайн (валидная строка-история)
new = w.observe(["Получено Старый Меч. [09:59]",
                 "Этап 3-3 пройдено. (120с) [10:00]",
                 "Получено Обычный сундук с сокровищами. (Goblin) [10:01]"])
ok("сундук из лога → событие chest", any(e["type"] == "chest" for e in new))
ok("сундук тип normal", w.chests.get("normal") == 1)
ok("этап извлечён 3-3", w.stage == "3-3")

# ── 2) ОТКРЫЛ СУНДУК → ВИЖУ ЧТО ВЫПАЛО (имя дропа) ──
new = w.observe(["Получено Обычный сундук с сокровищами. (Goblin) [10:01]",
                 "Получено Сияющая Броня. (Goblin) [10:02]"])
ok("дроп из лога → item", any(e["type"] == "item" for e in new))
ok("имя дропа извлечено", "Сияющая Броня" in " ".join(w.items))

# ── 3) ЗНАЮ ЧТО ВЫПАЛО → триггер «оценить на мерж» (drain новых дропов) ──
drained = w.drain_new_items()
ok("drain отдаёт новый дроп (→ форс скан/мерж-оценка)", "Сияющая Броня" in " ".join(drained))
ok("drain очистил буфер", w.drain_new_items() == [])

# ── 4) ИНТЕЛ: что и С КОГО упало (имя+моб) — для лут-лога ──
intel = w.drain_new_intel()
ok("интел дропа: имя+моб собраны", any("Сияющая" in (r.get("name") or "") and r.get("mob") for r in intel))

# ── 5) ПАЧКА сундуков разных типов в логе → все типы посчитаны ──
w2 = LogWatcher()
w2.observe(["Этап 1-1 пройдено. (30с) [10:59]"])                      # валидный базлайн
w2.observe(["Этап 1-1 пройдено. (30с) [10:59]",
            "Получено Обычный сундук с сокровищами. (A) [11:01]",
            "Получено Сундук с сокровищами этапа. (Boss) [11:01]",
            "Получено Сундук с сокровищами босса акта. (Act) [11:01]"])
ok("пачка: normal+stage+act = 3 типа",
   w2.chests.get("normal") == 1 and w2.chests.get("stage_boss") == 1 and w2.chests.get("act_boss") == 1)
ok("chests_total == 3 в пачке", w2.chests_total == 3)

# ── 6) EN-лог тоже читается (16 языков через словарь игры) ──
w3 = LogWatcher()
w3.observe(["Cleared Stage 1-1. (30s) [12:00]"])
new = w3.observe(["Cleared Stage 1-1. (30s) [12:00]",
                  "Obtained Common Treasure Chest. (Goblin) [12:01]"])
ok("EN сундук читается", w3.chests.get("normal") == 1)

print("\n" + ("ВСЕ ОК" if not fails else f"ПРОВАЛЫ: {fails}"))
sys.exit(1 if fails else 0)
