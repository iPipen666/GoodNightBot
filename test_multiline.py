"""test_multiline.py — счёт на РАЗВЁРНУТОМ многострочном окне RECORDS (новый частый случай после
авторазворота). Окно показывает N строк, каждый опрос прокручивается на k новых событий снизу.
Проверяем: observe считает РОВНО k новых (не перещёт от OCR-шума головы, не недосчёт)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from logwatch import LogWatcher

fails = []
def check(name, cond):
    print(("OK  " if cond else "FAIL") + " " + name)
    if not cond: fails.append(name)

# поток событий (как в реальном логе 3-3): этапы + случайные сундуки/дроп
STREAM = [
    "Cleared Stage 3-3. (253s) [00:01]",
    "Cleared Stage 3-3. (233s) [00:02]",
    "Obtained Common Treasure Chest. (Goblin) [00:03]",
    "Cleared Stage 3-3. (241s) [00:04]",
    "Knight has been defeated. (Frozen Hell) [00:05]",
    "Obtained Common Treasure Chest. (Orc) [00:06]",
    "Cleared Stage 3-3. (239s) [00:07]",
    "Cleared Stage 3-3. (248s) [00:08]",
    "Obtained Common Treasure Chest. (Slime) [00:09]",
    "Cleared Stage 3-3. (236s) [00:10]",
    "Hunter reached level 41. [00:11]",
    "Obtained Common Treasure Chest. (Bat) [00:12]",
]
WIN = 6  # развёрнутое окно показывает 6 строк (как в логе: «строк 6»)

def window_at(i):
    """6-строчное окно, newest снизу: события [i-6 .. i)."""
    lo = max(0, i - WIN)
    return STREAM[lo:i]

# 1) Прокрутка ПО ОДНОМУ событию за опрос — счётчик ровно по факту (3 сундука всего)
w = LogWatcher()
w.observe(window_at(WIN))                 # базлайн (первые 6 = история, 0)
for i in range(WIN + 1, len(STREAM) + 1):
    w.observe(window_at(i))
chests_expected = sum(1 for s in STREAM[WIN:] if "Treasure Chest" in s)
check(f"по 1 событию: сундуков {w.chests_total} == {chests_expected}", w.chests_total == chests_expected)
clears_expected = sum(1 for s in STREAM[WIN:] if "Cleared Stage" in s)
check(f"этапы ✓ {w.stages_cleared} == {clears_expected}", w.stages_cleared == clears_expected)

# 2) ВИСЯЩЕЕ окно (опрос без новых событий, OCR-шум головы) — НЕ пересчитывает
w = LogWatcher()
w.observe(window_at(8))                    # базлайн
base = w.chests_total
noisy = list(window_at(8))
noisy[0] = "Cleared Stage 3-3. (24Is)"     # OCR-шум на верхней строке (та же, искажена)
w.observe(noisy)                            # та же прокрутка, шум головы → 0 новых
w.observe(window_at(8))                     # снова та же → 0
check("висящее окно + OCR-шум = 0 новых (нет перещёта)", w.chests_total == base)

# 3) Прокрутка СРАЗУ на 3 события (пропущенные опросы) — посчитать все 3
w = LogWatcher()
w.observe(window_at(6))                     # базлайн (события 0..5)
w.observe(window_at(9))                     # прыжок на 3 (события 6,7,8 новые: chest@2? нет — индексы 6,7,8)
new3 = STREAM[6:9]
exp3 = sum(1 for s in new3 if "Treasure Chest" in s)
check(f"скачок на 3: +{exp3} сунд", w.chests.get("normal", 0) == exp3)

print("\n" + ("ВСЕ ОК" if not fails else f"ПРОВАЛЫ: {fails}"))
sys.exit(1 if fails else 0)
