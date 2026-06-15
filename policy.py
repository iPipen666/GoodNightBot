import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))

MERGE = "MERGE"
LOCK = "LOCK"
KEEP = "KEEP"


def decide(item, cfg):
    """
    Вернуть решение MERGE / LOCK / KEEP для предмета по config-правилам.
    Правила проверяются в строгом порядке; первое сработавшее определяет результат.
    """
    name = item.get("name", "")
    item_type = item.get("type")
    tier = item.get("rank_tier", -1)
    legendary_tier = cfg.get("legendary_tier", 3)
    hoard_names = cfg.get("hoard_names", [])

    # 1) Hoard-лист: имя входит в список копимых (вхождение подстроки, регистронезависимо) -> KEEP
    if hoard_names:
        name_lower = name.lower()
        for hoard in hoard_names:
            if hoard.lower() in name_lower:
                return KEEP

    # 2) Бижутерия — всегда LOCK (если не отключено явно)
    if item_type == "accessory" and cfg.get("lock_accessory", True) != False:
        return LOCK

    # 3) Материалы — свободно MERGE
    if item_type == "material":
        return MERGE

    # 4) Шмот по тиру
    if item_type == "gear":
        if tier == -1:
            return LOCK
        if tier <= legendary_tier:
            return MERGE
        if tier >= legendary_tier + 1:
            return LOCK

    # 5) Безопасный дефолт: нераспознанный тип -> LOCK
    if item_type is None:
        return LOCK

    # Неизвестный type, не покрытый правилами — безопасный дефолт
    return LOCK
