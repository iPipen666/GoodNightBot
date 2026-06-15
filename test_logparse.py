# -*- coding: utf-8 -*-
"""Тест template-driven парсера логов (log_templates → logwatch.parse). ASCII-вывод PASS/FAIL."""
import logwatch as L

# (строка, ожидаемый type, доп.проверка(ev)->bool или None)
CASES = [
    ("Этап 3-4 пройдено. (366с) [11:19]", "stage_clear", lambda e: e["stage"] == "3-4" and e["sec"] == 366),
    ("Не удалось пройти Этап 3-9. (1/28) [11:13]", "stage_fail", lambda e: e["stage"] == "3-9"),
    ("Рыцарь повержен. (Маг снежной горы) [11:13]", "defeat", lambda e: "Маг" in e.get("mob", "")),
    ("Рыцарь воскрес. [11:00]", "revive", None),
    ("Колдун достиг уровня 76. [11:00]", "levelup", lambda e: e["level"] == 76),
    ("Потрачен ранг Обычный, получен ранг Необычный [11:30]", "synthesis", lambda e: e["spent"] and e["got"]),
    ("Результат создания: получено Рунный Меч [11:16]", "craft", lambda e: "Рунный" in e["name"]),
    ("Получено Обычный сундук с сокровищами. (Goblin) [10:38]", "chest", lambda e: e["kind"] == "normal" and "Goblin" in e.get("mob", "")),
    ("Получено Сундук с сокровищами этапа. (Boss) [10:28]", "chest", lambda e: e["kind"] == "stage_boss"),
    # ОБРЕЗАННЫЙ маркизой boss-сундук ('этапа'→'эта') — ловился живьём как normal (stage_boss=0). Фикс
    # chest_kind_for: префикс маркера в хвосте после ядра имени. НЕ должен падать в normal.
    ("Получено Сундук с сокровищами эта!", "chest", lambda e: e["kind"] == "stage_boss"),
    ("Получено Сундук с сокровищами босса акта. (X) [10:28]", "chest", lambda e: e["kind"] == "act_boss"),
    ("Получено Сияющая Броня. [11:29]", "item", lambda e: "Сияющая" in e["name"]),
    ("oe Получено Обычный сундук с сокрови", "chest", lambda e: e["kind"] == "normal"),  # обрезан, фолбэк
    # английский (язык игры EN)
    ("Cleared Stage 3-4. (366s) [11:19]", "stage_clear", lambda e: e["stage"] == "3-4"),
    ("Obtained Common Treasure Chest. (Goblin)", "chest", lambda e: e["kind"] == "normal"),
    ("Knight has been defeated. (Slime)", "defeat", lambda e: "Slime" in e.get("mob", "")),
    ("Obtained Vengeance Sword.", "item", None),
    # десктоп-шум — НЕ событие
    ("Blender 5.1 Расценки SHANN v2.pptx", None, None),
    ("Eurocara Grp Поиск", None, None),
]

ok = 0
for s, exp_type, check in CASES:
    evs = L.parse(s)
    got = evs[0]["type"] if evs else None
    type_ok = (got == exp_type)
    chk_ok = True
    if type_ok and exp_type and check:
        try:
            chk_ok = bool(check(evs[0]))
        except Exception as ex:
            chk_ok = False
    p = type_ok and chk_ok
    ok += p
    print(f"[{'PASS' if p else 'FAIL'}] exp={exp_type!s:12} got={got!s:12} chk={chk_ok}  | {s[:40].encode('ascii','replace').decode()}")
print(f"\n{ok}/{len(CASES)} passed")
