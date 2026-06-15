"""test_burst.py — сдвиг-счёт при ПАЧКЕ событий в одну секунду (баг бёрст-дропа).
Раньше контент-дедуп `_seen` схлопывал одинаковые ключи → 3 одинаковых сундука считались как 1.
Проверяем: observe() считает ВСЕ новые строки по сдвигу, включая идентичные.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from logwatch import LogWatcher

STAGE = "Этап 2-9 пройдено. (12с) [10:30]"
ITEM = "Получено Сияющая Броня. [10:35]"
CHEST = "Получено Обычный сундук с сокровищами. (Goblin) [10:38]"
BOSS = "Получено Сундук с сокровищами этапа. (Boss) [10:38]"

fails = []


def check(name, cond):
    print(("OK  " if cond else "FAIL") + " " + name)
    if not cond:
        fails.append(name)


# 1) ПАЧКА: 3 одинаковых сундука в одну секунду = 3
w = LogWatcher()
w.observe([STAGE, ITEM])                       # базлайн (0)
new = w.observe([ITEM, CHEST, CHEST, CHEST])   # сдвиг на 3 одинаковых
check("3 одинаковых сундука = 3 события", len(new) == 3)
check("chests_total == 3", w.chests_total == 3)
check("normal == 3", w.chests.get("normal") == 3)

# 2) Смешанная пачка: normal + boss + normal в одну секунду = 3 (2 normal, 1 stage_boss)
w = LogWatcher()
w.observe([STAGE, ITEM])
new = w.observe([ITEM, CHEST, BOSS, CHEST])
check("смешанная пачка = 3", len(new) == 3)
check("normal == 2 в смеси", w.chests.get("normal") == 2)
check("stage_boss == 1 в смеси", w.chests.get("stage_boss") == 1)

# 3) Базлайн не считается (история до сессии = 0)
w = LogWatcher()
w.observe([CHEST, CHEST, CHEST])               # первый снимок = базлайн
check("базлайн = 0 (история не в счёт)", w.chests_total == 0)

# 4) Один сундук за опрос — без двойного счёта (boundary-гард не ломает обычный кейс)
w = LogWatcher()
w.observe([STAGE, ITEM])
w.observe([ITEM, CHEST])                        # +1
w.observe([CHEST, BOSS])                        # сдвиг: overlap=CHEST, new=BOSS → +1 (не +2)
check("последовательно по 1 = 2 всего", w.chests_total == 2)
check("без двойного счёта границы", w.chests.get("normal") == 1 and w.chests.get("stage_boss") == 1)

# 5) Повтор того же снимка (нет сдвига) = 0 новых
w = LogWatcher()
w.observe([STAGE, ITEM, CHEST])
new = w.observe([STAGE, ITEM, CHEST])           # идентичный снимок → сдвига нет
check("идентичный снимок = 0 новых", len(new) == 0 and w.chests_total == 0)

# 5b) РЕГРЕССИЯ РЕВЬЮ: prev КОНЧАЕТСЯ тем же сундуком, что и пачка (overshoot _align ранее → недосчёт)
w = LogWatcher()
w.observe([STAGE, CHEST])                        # базлайн кончается сундуком CHEST (история)
new = w.observe([CHEST, CHEST, CHEST])          # +2 НОВЫХ одинаковых (overlap=1, не 2!)
check("prev кончается тем же сундуком: +2", w.chests_total == 2 and len(new) == 2)
# и одиночный новый одинаковый сундук
w = LogWatcher()
w.observe([STAGE, CHEST])
new = w.observe([CHEST, CHEST])                  # +1 новый одинаковый
check("одиночный новый одинаковый сундук: +1", w.chests_total == 1 and len(new) == 1)

# 6) ВОССТАНОВЛЕНИЕ ПО ВРЕМЕНИ: большой скролл без перекрытия → считаем свежее водяного знака
C40 = "Получено Обычный сундук с сокровищами. (Goblin) [10:40]"
B41 = "Получено Сундук с сокровищами этапа. (Boss) [10:41]"
C42 = "Получено Обычный сундук с сокровищами. (Orc) [10:42]"
w = LogWatcher()
w.observe([STAGE, ITEM])                        # базлайн, водяной знак = 10:35
new = w.observe([C40, B41, C42])                # НЕТ перекрытия (O=0) → восстановление по времени
check("восстановление: 3 события свежее знака", len(new) == 3)
check("восстановление chests_total == 3", w.chests_total == 3)
check("восстановление normal==2 boss==1", w.chests.get("normal") == 2 and w.chests.get("stage_boss") == 1)

# 7) РОВНО ПОЙМАННЫЙ ЖИВЬЁМ БАГ: 1-строчный лог, stage(с ts) → chest БЕЗ ts (хвост-время не
#    прокрутилось) → сундук ДОЛЖЕН считаться (раньше терялся: O==0 + нет ts → 0).
w = LogWatcher()
w.observe(["Cleared Stage 3-4. (359s) [22:40]"])           # 1-строчный базлайн
new = w.observe(["Obtained Common Treasure Chest. (5п"])    # строка сменилась на сундук БЕЗ ts
check("1-строка: chest без ts СОСЧИТАН (пойманный баг)", w.chests.get("normal") == 1 and len(new) == 1)
new2 = w.observe(["Obtained Common Treasure Chest. (5п"])   # та же строка ВИСИТ (повторный опрос)
check("висящая строка не дублируется", len(new2) == 0 and w.chests_total == 1)

# 8) 1-строчный лог ЦИКЛ stage→chest→stage→chest = 2 сундука (реальный поток пилюли)
w = LogWatcher()
w.observe(["Cleared Stage 1-1. (30s) [10:00]"])
w.observe(["Obtained Common Treasure Chest. (Goblin)"])     # +1 (без ts)
w.observe(["Cleared Stage 1-2. (40s) [10:01]"])             # стейдж — не сундук
w.observe(["Obtained Common Treasure Chest. (Orc)"])        # +1 (без ts)
check("1-строка цикл stage/chest → 2 сундука", w.chests_total == 2)

# 9) ⛔ ПЕРЕЩЁТ (баг 135): висящая пилюля сундука при OCR-вариации головы → счёт 1, НЕ много
w = LogWatcher()
w.observe(["Cleared Stage 3-4. (300s) [10:00]"])             # базлайн-пилюля
w.observe(["Obtained Common Treasure Chest. (Goblin)"])      # сменилась на сундук → +1
w.observe(["Obtained Common Treasure Chest. (Gobl"])         # та же висит → 0
w.observe(["ото Treasure Chest. (5п"])                       # OCR-мусор той же пилюли → 0
w.observe(["Obtained Common Treasure Chest"])                # та же → 0
check("висящая пилюля при OCR-шуме = счёт 1 (нет перещёта)", w.chests_total == 1)
# а РЕАЛЬНАЯ смена (сундук → этап → сундук) считается заново
w.observe(["Cleared Stage 3-5. (300s) [10:05]"])             # этап (не сундук)
w.observe(["Obtained Common Treasure Chest. (Orc)"])         # НОВЫЙ сундук после этапа → +1
check("сундук после смены пилюли — считается заново", w.chests_total == 2)

print("\n" + ("ВСЕ ОК" if not fails else f"ПРОВАЛЫ: {fails}"))
sys.exit(1 if fails else 0)
