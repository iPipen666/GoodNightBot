"""db_browser.py — браузер игровой БД внутри GoodNightBot (pixel-art).
Вкладки: Предметы (поиск/фильтр/карточка со статами), Персонажи, Грейды.
Источник: items_db.json (by_key/by_name) + game_textassets/*.csv (статы/герои/грейды).

Запуск отдельно для теста:  python db_browser.py
Из панели: db_browser.open(root)  — модальное окно поверх.
"""
import os
import re
import csv
import io
import glob
import json
import webbrowser
import threading
import urllib.parse
import urllib.request
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import theme as T
import i18n
from i18n import t
try:
    from PIL import Image, ImageEnhance, ImageTk
    _PIL = True
except Exception:
    _PIL = False

STEAM_APPID = "3678970"
KEYCLR = "#ff00dc"   # ключ-цвет прозрачности: фон-контейнеры этого цвета -> сквозь них видна сцена   # TBH: Task Bar Hero — у игры ЕСТЬ Steam Community Market


def steam_search_url(en_name):
    """ПОИСК на торговой площадке Steam ПО ИМЕНИ предмета (без грейда!). В Steam грейд —
    это ФИЛЬТР (Ранг), а НЕ часть market-имени: 'Healing Herb (Uncommon)' не находится,
    'Healing Herb' находится. Поэтому ищем по чистому имени — юзер сам выберет грейд/уровень
    фильтрами на странице Steam."""
    if not en_name:
        return None
    return ("https://steamcommunity.com/market/search?appid=" + STEAM_APPID
            + "&q=" + urllib.parse.quote(en_name))


# грейд в Steam-имени TBH: "{Имя} ({Grade}) A" для шмота/бижу; материалы — просто имя.
# на маркете только высокие грейды (Legendary+), низкие не торгуются.
STEAM_GRADE = {"легендарный": "Legendary", "аркана": "Arcana", "бессмертный": "Immortal",
               "запредельный": "Beyond", "celestial": "Celestial", "божественный": "Divine",
               "космический": "Cosmic"}


def market_hash_name(it):
    """Точное market_hash_name предмета на Steam (с учётом грейда) или None."""
    en = name_in(it["key"], "en-US")
    if not en:
        return None
    if it.get("type") in ("gear", "accessory"):
        g = STEAM_GRADE.get((it.get("grade_ru") or "").lower())
        if g:
            return f"{en} ({g}) A"
    return en   # материалы/боксы — простое имя


def steam_listing_url(hash_name):
    """Прямая страница КОНКРЕТНОГО предмета (а не поиск)."""
    if not hash_name:
        return None
    return ("https://steamcommunity.com/market/listings/" + STEAM_APPID + "/"
            + urllib.parse.quote(hash_name))


def steam_price(en_name, timeout=8):
    """Live-цена с Steam Community Market (priceoverview API, RUB). dict|None.
    market_hash_name = английское имя (грейд в TBH — фильтр, не часть имени). Если лотов
    нет / имя не совпало — None."""
    if not en_name:
        return None
    try:
        url = ("https://steamcommunity.com/market/priceoverview/?country=RU&currency=5&appid="
               + STEAM_APPID + "&market_hash_name=" + urllib.parse.quote(en_name))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        if not d.get("success"):
            return None
        return {"low": d.get("lowest_price"), "median": d.get("median_price"),
                "vol": d.get("volume")}
    except Exception:
        return None

HERE = os.path.dirname(os.path.abspath(__file__))
TA = os.path.join(HERE, "game_textassets")

# ─── загрузка данных ───
_DB = json.load(open(os.path.join(HERE, "items_db.json"), encoding="utf-8"))
BY_KEY = _DB["by_key"]
BY_NAME = _DB["by_name"]

# ─── мультиязычные названия (item_names_i18n.json: {itemkey: {locale: name}}) ───
_I18N_PATH = os.path.join(HERE, "item_names_i18n.json")
I18N = {}
LOCALES = ["ru-RU"]
LANG_LABELS = {"ru-RU": "Русский"}
if os.path.exists(_I18N_PATH):
    try:
        _i = json.load(open(_I18N_PATH, encoding="utf-8"))
        I18N = _i.get("by_key", {})
        LOCALES = _i.get("meta", {}).get("locales", LOCALES)
        LANG_LABELS = _i.get("meta", {}).get("labels", LANG_LABELS)
    except Exception:
        I18N = {}

# ─── общие строки игры (скиллы/герои/статы/уник-моды) на все языки ───
_STRINGS_PATH = os.path.join(HERE, "game_strings_i18n.json")
STRINGS = {}
if os.path.exists(_STRINGS_PATH):
    try:
        STRINGS = json.load(open(_STRINGS_PATH, encoding="utf-8")).get("by_key", {})
    except Exception:
        STRINGS = {}


def gstr(key, locale, fallback=None):
    """Игровая строка по ключу на локали. Фолбэк: запрошенная -> en-US -> ru-RU -> любая -> fallback."""
    d = STRINGS.get(key)
    if not d:
        return fallback
    return d.get(locale) or d.get("en-US") or d.get("ru-RU") or next(iter(d.values()), fallback)


# ─── настройки языка (в config.json) ───
_CFG_PATH = os.path.join(HERE, "config.json")


def _load_cfg():
    try:
        return json.load(open(_CFG_PATH, encoding="utf-8"))
    except Exception:
        return {}


def _save_lang(main, translate_on, translate):
    c = _load_cfg()
    c["lang_main"] = main
    c["translate_enabled"] = bool(translate_on)
    c["lang_translate"] = translate
    json.dump(c, open(_CFG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def name_in(itemkey, locale, fallback=None):
    """Название предмета на локали (item_names_i18n). Фолбэк: ru-RU -> любой -> fallback."""
    d = I18N.get(str(itemkey))
    if d:
        if locale in d:
            return d[locale]
        if "ru-RU" in d:
            return d["ru-RU"]
        for v in d.values():
            return v
    return fallback


def _csv(name):
    for f in os.listdir(TA):
        if name.lower() in f.lower():
            data = open(os.path.join(TA, f), "rb").read().decode("utf-8-sig", "ignore")
            return list(csv.DictReader(io.StringIO(data)))
    return []


_ITEM_INFO = {r["ItemKey"]: r for r in _csv("ItemInfoData")}
_GEAR_INFO = {r["GearKey"]: r for r in _csv("GearInfoData")}
_GEARTYPE = {r["GearType"]: r for r in _csv("GearTypeInfoData")}
_HEROES = _csv("HeroInfoData")
_GRADES = _csv("GradeInfoData")

# ─── камни (украшения): ItemKey → набор STATTYPE, которые даёт камень ───
#   MaterialInfoData(ItemKey→StatModGroupKey) ∘ StatModGroupInfoData(group→StatModKey)
#   ∘ StatModInfoData(StatModKey→STATTYPE). Нужно для поиска «камни на урон холодом».
_MATERIAL = {r["ItemKey"]: r for r in _csv("MaterialInfoData")}
_SM_ROWS = _csv("StatModInfoData")
_SM = {r["StatModKey"]: r.get("STATTYPE", "") for r in _SM_ROWS}
# точные значения мода по (ключ, тир): MinValue/MaxValue/MODTYPE/STATTYPE
_SM_VAL = {}
for _r in _SM_ROWS:
    try:
        _SM_VAL[(_r["StatModKey"], int(_r["Tier"]))] = _r
    except Exception:
        pass
# группа модов -> строки (GearGroup/StatModKey/MinTier/MaxTier) и набор STATTYPE (для поиска)
_SM_GROUP_ROWS = {}
_SM_GROUP = {}
for _r in _csv("StatModGroupInfoData"):
    g = _r["StatModGroupKey"]
    _SM_GROUP_ROWS.setdefault(g, []).append(_r)
    _SM_GROUP.setdefault(g, set()).add(_SM.get(_r.get("StatModKey", ""), ""))

GEARGROUP_RU = {"WEAPON": "оружие", "ARMOR": "броню", "ACCESSORY": "бижу",
                "COMMON": "любое снаряжение"}

# ─── алхимия (стоимость извлечения предмета в золото) ───
#   gold = BaseAlchemyGold(grade) × ItemTypeScale × [GearTypeScale] × LevelScale  (scale /1000)
_GRADE_GOLD = {r["GRADE"]: int(r.get("BaseAlchemyGold", 0) or 0) for r in _GRADES}
_GRADE_CUBEEXP = {r["GRADE"]: int(r.get("BaseCubeExp", 0) or 0) for r in _GRADES}
_GTSCALE = {r["GearType"]: int(r.get("AlchemyGoldScale", 1000) or 1000)
            for r in _csv("GearTypeScaleInfoData")}
_ITSCALE = {r["ItemType"]: int(r.get("AlchemyGoldScale", 1000) or 1000)
            for r in _csv("ItemTypeScaleInfoData")}
_LVLSCALE = {int(r["Level"]): int(r.get("AlchemyGoldScale", 1000) or 1000)
             for r in _csv("ItemLevelScaleInfoData")}
_LVL_KEYS = sorted(_LVLSCALE)

# STATTYPE -> человекочитаемо (полный список из StatModInfoData/GearInfoData)
STAT_RU = {
    "AttackDamage": "Урон атаки", "AttackSpeed": "Скорость атаки",
    "MaxHp": "Макс. HP", "MaxLife": "Макс. HP", "Armor": "Броня",
    "CriticalChance": "Шанс крита", "CriticalDamage": "Урон крита",
    "MovementSpeed": "Скор. движения", "CooldownReduction": "Перезарядка",
    "CastSpeed": "Скор. каста", "AllHeroAttackDamage": "Урон всех героев",
    "AdditionalAttackDamage": "Доп. урон атаки", "HpPerHit": "HP за удар",
    "AddHpPerHit": "HP за удар", "AddHpPerKill": "HP за убийство",
    "LifeSteal": "Вампиризм", "HpLeech": "Вампиризм HP", "GoldGain": "Золото",
    "ExpGain": "Опыт", "IncreaseExpAmount": "Больше опыта", "AdditionalExp": "Доп. опыт",
    "HpRegenPerSec": "Реген HP/сек", "DodgeChance": "Шанс уклонения",
    "MaxDodgeChance": "Макс. уклонение", "BlockChance": "Шанс блока",
    "MaxBlockChance": "Макс. блок", "Multistrike": "Мультиудар",
    "ProjectileCount": "Кол-во снарядов", "AreaOfEffect": "Радиус действия",
    "BaseAttackCountReduction": "−базовых атак", "SkillRangeExpansion": "Дальность умений",
    "DamageReduction": "Сниж. урона", "DamageAbsorption": "Поглощение урона",
    "DamageAddition": "Добавл. урон", "CooldownReductionPercent": "Перезарядка %",
    # стихии: процент урона / добавл. урон / снижение урона / сопротивление / макс. сопрот.
    "PhysicalDamagePercent": "% физ. урона", "FireDamagePercent": "% урона огнём",
    "ColdDamagePercent": "% урона холодом", "LightningDamagePercent": "% урона молнией",
    "ChaosDamagePercent": "% урона хаосом",
    "PhysicalDamageAddition": "+ физ. урон", "FireDamageAddition": "+ урон огнём",
    "ColdDamageAddition": "+ урон холодом", "LightningDamageAddition": "+ урон молнией",
    "ChaosDamageAddition": "+ урон хаосом",
    "PhysicalDamageReduction": "сниж. физ. урона", "FireDamageReduction": "сниж. урона огнём",
    "ColdDamageReduction": "сниж. урона холодом", "LightningDamageReduction": "сниж. урона молнией",
    "ChaosDamageReduction": "сниж. урона хаосом",
    "FireResistance": "сопрот. огню", "ColdResistance": "сопрот. холоду",
    "LightningResistance": "сопрот. молнии", "ChaosResistance": "сопрот. хаосу",
    "AllElementalResistance": "сопрот. всем стихиям",
    "MaxFireResistance": "макс. сопрот. огню", "MaxColdResistance": "макс. сопрот. холоду",
    "MaxLightningResistance": "макс. сопрот. молнии", "MaxChaosResistance": "макс. сопрот. хаосу",
    "IncreaseAreaOfEffectDamage": "+ урон по площади", "IncreaseMeleeDamage": "+ ближний урон",
    "IncreaseProjectileDamage": "+ урон снарядов", "IncreaseSummonDamage": "+ урон призывов",
    "SkillDurationIncrease": "длительность умений", "SkillHealIncrease": "+ лечение умений",
}


def stat_ru(st):
    return STAT_RU.get(st, st)


# краткие пояснения механики статов/терминов (что это значит на практике) — авторские
STAT_EXPLAIN = {
    "AttackDamage": "базовый урон одной атаки.",
    "AttackSpeed": "сколько атак в секунду — выше скорость = чаще бьёшь.",
    "CriticalChance": "шанс нанести критический удар (усиленный).",
    "CriticalDamage": "множитель урона при крите (насколько крит больнее обычного удара).",
    "AreaOfEffect": "радиус действия способностей по площади — больше радиус = задевает больше врагов.",
    "IncreaseAreaOfEffectDamage": "усиливает урон способностей по площади (AoE).",
    "CooldownReduction": "сокращает перезарядку умений — чаще применяешь скиллы.",
    "CooldownReductionPercent": "сокращает перезарядку умений в процентах.",
    "Multistrike": "шанс/количество дополнительных мгновенных ударов.",
    "ProjectileCount": "сколько снарядов выпускается за атаку.",
    "MovementSpeed": "скорость передвижения героя.",
    "CastSpeed": "скорость применения умений (каста).",
    "LifeSteal": "вампиризм: часть нанесённого урона возвращается как HP.",
    "HpLeech": "вампиризм HP с нанесённого урона.",
    "HpPerHit": "восстановление HP за каждый удар.",
    "HpRegenPerSec": "восстановление HP каждую секунду.",
    "DodgeChance": "шанс полностью уклониться от удара.",
    "BlockChance": "шанс заблокировать удар (снизить урон).",
    "DamageReduction": "снижает весь входящий урон.",
    "DamageAbsorption": "поглощает фиксированную часть входящего урона.",
    "GoldGain": "увеличивает получаемое золото.",
    "ExpGain": "увеличивает получаемый опыт.",
    "FireDamagePercent": "увеличивает урон огнём (в процентах).",
    "ColdDamagePercent": "увеличивает урон холодом (в процентах).",
    "LightningDamagePercent": "увеличивает урон молнией (в процентах).",
    "ChaosDamagePercent": "увеличивает урон хаосом (в процентах).",
    "PhysicalDamagePercent": "увеличивает физический урон (в процентах).",
    "FireResistance": "снижает получаемый урон огнём.",
    "ColdResistance": "снижает получаемый урон холодом.",
    "LightningResistance": "снижает получаемый урон молнией.",
    "ChaosResistance": "снижает получаемый урон хаосом.",
    "AllElementalResistance": "снижает урон от всех стихий сразу.",
}

_UNIQUE_MOD = {r["UniqueModKey"]: r.get("UniqueMod", "") for r in _csv("UniqueModInfoData")}

# ─── скиллы героев (механика; локализованного текста в извлечённых файлах нет) ───
_ATTRS = _csv("AttributeInfoData")
_PASSIVE = {r["PassiveSkillKey"]: r for r in _csv("PassiveSkillInfoData")}
_SKLVL = {}
for _r in _csv("SkillLevelInfoData"):
    _SKLVL.setdefault(_r.get("SkillLevelKey", ""), []).append(_r)


def hero_skills(hero_key):
    """{'passives':[{stat,val,sign,max}], 'actives':[{key,max,levels}]} для героя. Механика."""
    passives, actives = [], []
    for r in _ATTRS:
        if r.get("HeroKey") != str(hero_key):
            continue
        val = r.get("Value", "")
        mx = r.get("MaxLevel", "?")
        if r.get("ATTRIBUTETYPE") == "PASSIVESKILL":
            p = _PASSIVE.get(val)
            if not p:
                continue
            st = p.get("STATTYPE", ""); md = p.get("MODTYPE", "")
            sign = "%" if (md or "").upper() in ("MULTIPLICATIVE", "PERCENT") else ""
            passives.append({"stat": st, "ru": stat_ru(st), "val": p.get("Value", ""),
                             "sign": sign, "max": mx, "name_key": p.get("SkillNameKey", "")})
        elif r.get("ATTRIBUTETYPE") == "ACTIVESKILL":
            lv = sorted(_SKLVL.get(val, []), key=lambda x: int(x.get("Level", 0)))
            actives.append({"key": val, "max": mx,
                            "levels": [x.get("Value", "") for x in lv],
                            "name_key": f"SkillName_{val}", "desc_key": f"SkillDescription_{val}"})
    return {"passives": passives, "actives": actives}


def _split_code(s):
    """camelCase/PascalCase код → читаемые слова: 'IceOrbFreezeToCold' → 'Ice Orb Freeze To Cold'."""
    import re as _re
    return _re.sub(r"(?<!^)(?=[A-Z])", " ", s or "").strip()


def item_stattypes(itemkey):
    """Множество STATTYPE, которые есть у предмета (шмот: база+врождённые; материал: его стат-группа)."""
    out = set()
    info = _ITEM_INFO.get(itemkey)
    if not info:
        return out
    gi = _GEAR_INFO.get(info.get("GearKey") or "")
    gt = _GEARTYPE.get(info.get("GEARTYPE", ""))
    for src, keys in ((gt, ("BaseStat1_STATTYPE", "BaseStat2_STATTYPE")),
                      (gi, ("InherentStat1_STATTYPE", "InherentStat2_STATTYPE", "InherentStat3_STATTYPE"))):
        if src:
            for k in keys:
                v = src.get(k)
                if v and v != "NONE":
                    out.add(v)
    m = _MATERIAL.get(itemkey)
    if m and m.get("StatModGroupKey"):
        out |= {s for s in _SM_GROUP.get(m["StatModGroupKey"], set()) if s}
    return out


def item_note(it, info):
    """Примечание к предмету — кратко и по делу (клиентский тон: «синтез», не «мерж»)."""
    mk = it.get("mat_kind")
    t = it.get("type")
    if t == "material" and mk in MAT_NOTE:
        return MAT_NOTE[mk]
    if t == "accessory":
        return ("Украшения бот синтезирует так же, как шмот — до выбранного потолка грейда "
                "(по умолчанию низкие: зелёные/синие). Ценные и высокие грейды бережёт. "
                "Выпадают они реже оружия и брони, поэтому высокие лучше копить и синтезировать "
                "вручную (потолок грейда — в ⚙ настройках).")
    if t == "gear":
        return ("Грейд повышается синтезом в Кубе: 9 предметов одной редкости → 1 предмет "
                "редкостью выше. Бот синтезирует автоматически до выбранного потолка грейда.")
    if t == "box":
        return "Контейнер — открывается в игре и выдаёт содержимое."
    return ""


def gem_lines(itemkey):
    """Материал со стат-группой (украшение/гравировка/надпись) → строки «в <слот>: <стат>
    +<знач.>» (что и СКОЛЬКО даёт). Значение зависит от типа снаряжения (WEAPON/ARMOR/
    ACCESSORY) и тира мода. [] если у материала нет стат-группы (крафт/подношение/камень души)."""
    m = _MATERIAL.get(itemkey)
    if not m or not m.get("StatModGroupKey"):
        return []
    out = []
    for r in _SM_GROUP_ROWS.get(m.get("StatModGroupKey", ""), []):
        key = r.get("StatModKey", "")
        try:
            mn, mx = int(r.get("MinTier", 0)), int(r.get("MaxTier", 0))
        except Exception:
            continue
        lo_row = _SM_VAL.get((key, mn))
        if not lo_row:
            continue
        hi_row = _SM_VAL.get((key, mx), lo_row)
        st = lo_row.get("STATTYPE", ""); md = lo_row.get("MODTYPE", "")
        sign = _mod_sign(md)
        lo = lo_row.get("MinValue", ""); hi = hi_row.get("MaxValue", "")
        val = f"+{lo}{sign}" if lo == hi else f"+{lo}..{hi}{sign}"
        gg = GEARGROUP_RU.get(r.get("GearGroup", ""), r.get("GearGroup", "").lower())
        out.append(f"в {gg}: {stat_ru(st)} {val}")
    return out


def gem_terms(itemkey):
    """Названия статов материала (рус.) для поиска. [] если у материала нет стат-группы."""
    m = _MATERIAL.get(itemkey)
    if not m or not m.get("StatModGroupKey"):
        return []
    return [stat_ru(s) for s in _SM_GROUP.get(m.get("StatModGroupKey", ""), set()) if s]


def alchemy_gold(itemkey):
    """Стоимость предмета в алхимии (золото): BaseAlchemyGold(грейд) × scale-таблицы.
    None если нет данных. Значение приблизительное (≈) — точную формулу игра может
    докручивать, но порядок и относительная ценность верны (грейд = ×3 за тир)."""
    info = _ITEM_INFO.get(itemkey)
    if not info:
        return None
    base = _GRADE_GOLD.get(info.get("GRADE", ""), 0)
    if not base:
        return None
    g = float(base)
    g *= _ITSCALE.get(info.get("ITEMTYPE", ""), 1000) / 1000.0
    if info.get("ITEMTYPE") == "GEAR":
        g *= _GTSCALE.get(info.get("GEARTYPE", ""), 1000) / 1000.0
    lv = BY_KEY.get(itemkey, {}).get("level")
    if lv:
        if lv in _LVLSCALE:
            sc = _LVLSCALE[lv]
        else:
            below = [k for k in _LVL_KEYS if k <= lv]
            sc = _LVLSCALE[below[-1]] if below else _LVLSCALE[_LVL_KEYS[0]]
        g *= sc / 1000.0
    return int(round(g))


def _fmt_gold(n):
    return f"{n:,}".replace(",", " ")
CLASS_RU = {"Knight": "Рыцарь", "Ranger": "Рейнджер", "Sorcerer": "Колдун",
            "Priest": "Жрец", "Hunter": "Охотник", "Slayer": "Истребитель"}
GEARTYPE_RU = {"SWORD": "меч", "BOW": "лук", "STAFF": "посох", "SCEPTER": "скипетр",
               "CROSSBOW": "арбалет", "AXE": "топор", "SHIELD": "щит", "ARROW": "стрелы",
               "ORB": "сфера", "TOME": "том", "BOLT": "болты", "HATCHET": "топорик",
               "HELMET": "шлем", "ARMOR": "броня", "GLOVES": "перчатки", "BOOTS": "сапоги",
               "AMULET": "амулет", "EARING": "серьга", "RING": "кольцо", "BRACER": "наруч"}
GRADE_RU_ALL = ["обычный", "необычный", "редкий", "легендарный", "бессмертный",
                "аркана", "запредельный", "celestial", "божественный", "космический"]
TYPE_RU = {"gear": "снаряжение", "accessory": "бижутерия", "material": "материал", "box": "сундук"}
# подтип материала (в какой слот/для чего) — MaterialInfoData.MATERIALTYPE
MAT_RU = {"DECORATION": "украшение (камень в слот украшения)",
          "ENGRAVING": "гравировка (материал гравировки)",
          "INSCRIPTION": "надпись (материал надписи)",
          "CRAFTING": "крафт-материал", "OFFERING": "подношение",
          "SOULSTONE": "камень души"}
MAT_RU_SHORT = {"DECORATION": "украшение", "ENGRAVING": "гравировка",
                "INSCRIPTION": "надпись", "CRAFTING": "крафт",
                "OFFERING": "подношение", "SOULSTONE": "камень души"}
# подробное примечание по виду материала (что это и что даёт)
MAT_NOTE = {
    "OFFERING": "Подношение. Скармливается Кубу в режиме Offering (Подношение) — даёт опыт "
                "куба (прокачка уровня Куба, см. «опыт куба» выше). Статов не даёт и в "
                "снаряжение не вставляется. Можно продать на Steam.",
    "DECORATION": "Камень-украшение. Вставляется в слот «украшение» снаряжения и даёт статы "
                  "(см. блок выше). Конкретное значение зависит от типа снаряжения и тира камня.",
    "ENGRAVING": "Материал гравировки. Наносит гравировку на снаряжение → постоянный стат "
                 "(см. блок выше). Гравировку можно снять в Кубе (режим Removal).",
    "INSCRIPTION": "Материал надписи. Наносит надпись на снаряжение → стат, работает на любом "
                   "снаряжении (см. блок выше). Снимается в Кубе (режим Removal).",
    "CRAFTING": "Крафт-материал. Используется в рецептах Крафта (Crafting) для создания предметов.",
    "SOULSTONE": "Камень души. Особый материал прогресса — используется в системе душ/прокачки.",
}


def material_kind(itemkey):
    """RU-подтип материала (украшение/гравировка/…) или None если не материал."""
    m = _MATERIAL.get(itemkey)
    return m.get("MATERIALTYPE") if m else None


def _mod_sign(mod):
    return "%" if (mod or "").upper() in ("MULTIPLICATIVE", "PERCENT") else ""


def item_stats(itemkey):
    """Список строк-статов предмета: базовые (по GearType) + врождённые (GearInfoData)."""
    out = []
    info = _ITEM_INFO.get(itemkey)
    if not info:
        return out
    gk = info.get("GearKey") or ""
    gt = _GEARTYPE.get(info.get("GEARTYPE", ""))
    gi = _GEAR_INFO.get(gk)
    if gt and gi:
        for n in ("1", "2"):
            st = gt.get(f"BaseStat{n}_STATTYPE")
            md = gt.get(f"BaseStat{n}_MODTYPE")
            val = gi.get(f"BaseStat{n}_Value")
            if st and st != "NONE" and val and val not in ("0", ""):
                out.append(f"{STAT_RU.get(st, st)} +{val}{_mod_sign(md)}")
    if gi:
        for n in ("1", "2", "3"):
            st = gi.get(f"InherentStat{n}_STATTYPE")
            md = gi.get(f"InherentStat{n}_MODTYPE")
            val = gi.get(f"InherentStat{n}_Value")
            if st and st != "NONE" and val and val not in ("0", ""):
                out.append(f"{STAT_RU.get(st, st)} +{val}{_mod_sign(md)}  (врожд.)")
    return out


# ─── индекс предметов для поиска (по by_key) ───
def _build_index():
    items = []
    for ik, r in BY_KEY.items():
        nm = r.get("name") or f"#{ik}"
        gems = gem_lines(ik)                       # «в оружие: HP за удар +1..2» (показ)
        gterms = gem_terms(ik)                     # названия статов камня (поиск)
        gstats = [s.split("  ")[0] for s in item_stats(ik)]   # статы шмота без значений
        mk = material_kind(ik)                     # подтип материала (DECORATION/...)
        mk_ru = MAT_RU_SHORT.get(mk, "") if mk else ""
        i18n = I18N.get(ik, {})                     # {locale: name} — все языки
        # текст для поиска: имена на ВСЕХ языках + грейд + подтип + статы (камня и шмота)
        stxt = " ".join([nm, r.get("grade_ru", ""), mk_ru] + list(i18n.values())
                        + gterms + gstats).lower()
        items.append({
            "key": ik, "name": nm, "name_l": nm.lower(),
            "grade_ru": r.get("grade_ru", "?"), "tier": r.get("tier", -1),
            "type": r.get("type", "?"), "part_ru": r.get("part_ru", ""),
            "geartype": r.get("geartype", ""), "level": r.get("level"),
            "accessory": r.get("accessory", False),
            "gems": gems, "search_text": stxt, "mat_kind": mk,
        })
    items.sort(key=lambda x: (x["type"], x["tier"], x["name"]))
    return items


_INDEX = _build_index()


class DBBrowser:
    def __init__(self, root, embedded=False, height=None):
        self.root = root
        self.embedded = embedded
        self.win = root if embedded else tk.Toplevel(root)
        self._drag = (0, 0)
        if not embedded:
            # без системного заголовка (как сама панель) — рисуем свой хедер
            self.win.configure(bg=T.EDGE)
            self.win.overrideredirect(True)
            h = int(height) if height else 640
            # встать справа от панели (панель ~+40+40, ширина ~344)
            try:
                px, py = root.winfo_x(), root.winfo_y()
            except Exception:
                px, py = 40, 40
            x = (px + root.winfo_width() + 12) if px else 396
            self.win.geometry(f"900x{h}+{max(0, x)}+{max(0, py)}")
            # БД НЕ topmost (поверх всех — только таймер)
            # «прикреплена» к панели: едет за ней; смещение от левого-верха панели
            self.attached = True
            self._rel = (max(0, x) - (px or 40), max(0, py) - (py or 40))
        self._init_scroll_style()
        self.cur_tab = "items"
        self.flt_geartype = None   # фильтр по виду оружия (из клика по герою)
        self._suppress = False     # подавить авто-сброс фильтров при программной установке
        # язык: основной + перевод (из config.json)
        _c = _load_cfg()
        self.lang_main = _c.get("lang_main", "ru-RU")
        self.translate_on = bool(_c.get("translate_enabled", False))
        self.lang_tr = _c.get("lang_translate", "en-US")
        if self.lang_main not in LOCALES:
            self.lang_main = "ru-RU" if "ru-RU" in LOCALES else LOCALES[0]
        if self.lang_tr not in LOCALES:
            self.lang_tr = "en-US" if "en-US" in LOCALES else LOCALES[-1]
        self._build()
        self._refresh_items()
        if not embedded:
            self._add_resize_grip()

    def set_search(self, q):
        """Программно искать предмет (из клика по луту в логе): вкладка Предметы + запрос."""
        try:
            self._suppress = True
            self.flt_geartype = None
            self.type_var.set("all"); self.grade_var.set("all")
            if hasattr(self, "mat_var"):
                self.mat_var.set("all")
            if hasattr(self, "trade_var"):
                self.trade_var.set("all")
            self.search_var.set(q or "")
            self._suppress = False
            self._set_tab("items")
            self._refresh_items()
            self.win.deiconify(); self.win.lift()
        except Exception:
            pass

    def _disp_name(self, it):
        """Название на основном языке (с фолбэком на сохранённое ru-имя индекса)."""
        return name_in(it["key"], self.lang_main, it["name"])

    def _tr_name(self, it):
        """Перевод на язык перевода (или None, если выключено / совпадает с основным)."""
        if not self.translate_on or self.lang_tr == self.lang_main:
            return None
        return name_in(it["key"], self.lang_tr, None)

    def _init_scroll_style(self):
        """Тёмный скроллбар: ttk-тема clam позволяет перекрасить (нативный — белый)."""
        st = ttk.Style(self.win)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Night.Vertical.TScrollbar", troughcolor=T.NIGHT,
                     background=T.EDGE, bordercolor=T.NIGHT, arrowcolor=T.SUB,
                     darkcolor=T.EDGE, lightcolor=T.EDGE, relief="flat")
        st.map("Night.Vertical.TScrollbar",
               background=[("active", T.EDGE_HI), ("pressed", T.EDGE_HI)])

    def _press(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _move(self, e):
        self.attached = False   # юзер сам двигает БД → открепить (перестать ехать за панелью)
        self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def follow(self, px, py):
        """Поехать за панелью (если прикреплена): держать смещение относительно её левого-верха."""
        if not getattr(self, "attached", False):
            return
        try:
            self.win.geometry(f"+{int(px + self._rel[0])}+{int(py + self._rel[1])}")
        except Exception:
            pass

    def _add_resize_grip(self):
        """Полоска внизу окна для регулировки ВЫСОТЫ (ширина 900 фиксирована)."""
        grip = tk.Frame(self.win, bg=T.EDGE_HI, height=7, cursor="sb_v_double_arrow")
        grip.place(relx=0.0, rely=1.0, anchor="sw", relwidth=1.0, height=7)
        grip.bind("<Button-1>", self._rz_press)
        grip.bind("<B1-Motion>", self._rz_drag)

    def _rz_press(self, e):
        self._rz = (e.y_root, self.win.winfo_height())

    def _rz_drag(self, e):
        nh = max(360, self._rz[1] + (e.y_root - self._rz[0]))
        self.win.geometry(f"900x{int(nh)}+{self.win.winfo_x()}+{self.win.winfo_y()}")

    def _close(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        if getattr(self, "_own_root", False):
            try:
                self.root.destroy()
            except Exception:
                pass

    def _manual(self, *a):
        """Ручное изменение поиска/типа/грейда — сбрасывает geartype-фильтр (от клика героя)."""
        if self._suppress:
            return
        self.flt_geartype = None
        self._refresh_items()

    def _font(self, sz, bold=False):
        sz += 1                     # слегка крупнее везде — читабельнее (как просил юзер)
        fams = set(tkfont.families())
        fam = next((f for f in T.PIX_FONTS if f in fams), "Consolas")
        return (fam, sz, "bold" if bold else "normal")

    def _grade_color(self, ru):
        return T.GRADE.get((ru or "").lower(), T.SUB)

    # ---------- построение ----------
    def _load_dbbg(self):
        """Фон базы знаний — трейлер из одного mp4 (templates/db_anim/<loc>.mp4, упакован
        pack_dbbg.py: хвост-вспышка отрезан, шаг 3 вшит). Читаем кадры подряд через VideoCapture,
        кладём ОДНИМ кадром на ВСЁ окно; шапка/список/детали берут свой кроп → фон непрерывен."""
        self._cap = None
        self._vfull = None          # текущий затемнённый кадр на размер всего окна (PIL)
        self._vint = 50             # мс между тиками (лёгкий тик = только подмена кадра)
        self._lbi = 0
        self._lbtk = None
        if not _PIL:
            return
        adir = os.path.join(HERE, "templates", "db_anim")
        vids = sorted(glob.glob(os.path.join(adir, "*.mp4")))
        if not vids:
            return
        try:
            import cv2
        except Exception:
            return
        self._cv2 = cv2
        cap = cv2.VideoCapture(vids[0])
        if not cap.isOpened():
            return
        self._cap = cap
        self._dbmax = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))

    def _build_vidframe(self):
        """Один кадр трейлера CONTAIN на ВСЁ окно (весь кадр влезает, тёмные поля) + затемнение.
        BILINEAR (быстро, без рывков). PIL."""
        try:
            W, H = self.win.winfo_width(), self.win.winfo_height()
            if W < 2 or H < 2 or self._cap is None:
                return None
            ok, frame = self._cap.read()
            if not ok:                                        # EOF → петля с начала
                self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)
                self._lbi = 0
                ok, frame = self._cap.read()
                if not ok:
                    return None
            im = Image.fromarray(self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB))
            s = min(W / im.width, H / im.height)              # CONTAIN — весь видос влезает
            rw, rh = max(1, int(im.width * s)), max(1, int(im.height * s))
            rim = im.resize((rw, rh), Image.BILINEAR)
            cv = Image.new("RGB", (W, H), (8, 6, 12))
            cv.paste(rim, ((W - rw) // 2, H - rh))            # ПРИЖАТЬ К НИЗУ окна
            # плавное появление/затухание на стыке петли (к началу/концу гаснет в фон — без рывка)
            fl = min(30, self._dbmax // 3)
            i = self._lbi
            if i < fl:
                f = i / fl
            elif i > self._dbmax - fl:
                f = max(0.0, (self._dbmax - i) / fl)
            else:
                f = 1.0
            cv = ImageEnhance.Brightness(cv).enhance(0.34 * f)  # притушить + fade in/out
            tint = Image.new("RGB", (W, H), (26, 16, 44))       # тёмно-фиолетовая тонировка
            self._vfull = Image.blend(cv, tint, 0.34)           # ~34% — заметно тонирует, читабельнее
            return self._vfull
        except Exception:
            return None

    def _slice_for(self, canvas):
        """Кроп общего кадра под позицию canvas в окне → PhotoImage (фон сшивается без швов)."""
        if self._vfull is None:
            return None
        try:
            ox = canvas.winfo_rootx() - self.win.winfo_rootx()
            oy = canvas.winfo_rooty() - self.win.winfo_rooty()
            cw, ch = canvas.winfo_width(), canvas.winfo_height()
            if cw < 2 or ch < 2:
                return None
            return ImageTk.PhotoImage(self._vfull.crop((ox, oy, ox + cw, oy + ch)))
        except Exception:
            return None

    def _set_canvas_bg(self, canvas, attr):
        """Подменить ТОЛЬКО видео-слой канваса (тег vid), текст-элементы (fg) не трогаем."""
        tkimg = self._slice_for(canvas)
        if tkimg is None:
            return
        setattr(self, attr, tkimg)                 # держим ссылку (иначе GC съест картинку)
        canvas.delete("vid")
        canvas.create_image(0, 0, anchor="nw", image=tkimg, tags="vid")
        canvas.tag_lower("vid")

    def _animate_list(self):
        """Тик единого видео-фона: общий кадр окна → кроп в каждый канвас (МЕНЯЕМ только слой vid,
        текст/строки НЕ пересоздаём — иначе лагает). Нет второго окна, при сворачивании нечему остаться."""
        try:
            if self.win.winfo_exists() and self._cap is not None and self.win.winfo_viewable():
                self._lbi += 1          # счётчик кадра для fade; _build сбросит на петле (EOF)
                if self._build_vidframe() is not None:
                    if hasattr(self, "head_c"):
                        self._set_canvas_bg(self.head_c, "_htk")
                    if hasattr(self, "tabs_c"):
                        self._set_canvas_bg(self.tabs_c, "_ttk")
                    if getattr(self, "cur_tab", "items") == "items":   # список/детали видны только тут
                        if hasattr(self, "lb"):
                            self._set_canvas_bg(self.lb, "_lbtk")
                        if hasattr(self, "det"):
                            self._set_canvas_bg(self.det, "_dtk")
        except Exception:
            pass
        try:
            self.win.after(self._vint, self._animate_list)
        except Exception:
            pass

    def _redraw_list(self):
        """Перерисовать ТОЛЬКО строки (тег fg) — видео-слой (тег vid) не трогаем. Зовётся на
        скролл/выбор/refresh, НЕ каждый видео-тик."""
        if not hasattr(self, "lb") or not self.lb.winfo_exists():
            return
        c = self.lb
        c.delete("fg")
        W, H = c.winfo_width(), c.winfo_height()
        rh = self._row_h
        total = len(self._rows) * rh
        self._scroll = max(0, min(self._scroll, max(0, total - H)))
        first = self._scroll // rh
        last = min(len(self._rows), (self._scroll + H) // rh + 1)
        for idx in range(first, last):
            y = idx * rh - self._scroll
            if idx == self._sel:
                c.create_rectangle(0, y, W, y + rh, fill=T.PANEL2, outline="", stipple="gray50", tags="fg")
            txt, col = self._rows[idx]
            c.create_text(8, y + rh // 2, anchor="w", text=txt, fill=col, font=self._font(9), tags="fg")
        if total > 0 and hasattr(self, "_sb"):
            self._sb.set(self._scroll / total, min(1.0, (self._scroll + H) / total))
        c.tag_lower("vid")

    def _list_wheel(self, e):
        self._scroll -= int(e.delta / 120) * self._row_h * 3
        self._redraw_list()

    def _list_yview(self, *args):
        total = len(self._rows) * self._row_h
        if args and args[0] == "moveto":
            self._scroll = int(float(args[1]) * total)
        elif args and args[0] == "scroll":
            self._scroll += int(args[1]) * self._row_h * 3
        self._redraw_list()

    def _redraw_header(self):
        c = self.head_c
        c.delete("fg")
        W, H = c.winfo_width(), c.winfo_height()
        cy = H // 2 if H > 2 else 16
        tid = c.create_text(4, cy, anchor="w", text="🗄 " + t("db_hdr"), fill=T.MOON,
                            font=self._font(14, True), tags="fg")
        bb = c.bbox(tid)
        sx = (bb[2] + 10) if bb else 130
        c.create_text(sx, cy, anchor="w",
                      text=f"{len(_INDEX)} {t('db_items')} · 6 {t('db_heroes')} · 10 {t('db_grades')}",
                      fill=T.FAINT, font=self._font(8), tags="fg")
        c.create_text(W - 6, cy, anchor="e", text="✕", fill=T.STOPC,
                      font=self._font(13, True), tags=("fg", "close"))
        c.tag_lower("vid")

    def _redraw_tabs(self):
        c = self.tabs_c
        c.delete("fg")
        W, H = c.winfo_width(), c.winfo_height()
        n = len(self._tabkeys)
        seg = (W / n) if n else W
        cur = getattr(self, "cur_tab", "items")
        for i, (key, lblk) in enumerate(self._tabkeys):
            x0, x1 = i * seg + 1, (i + 1) * seg - 1
            on = cur == key
            c.create_rectangle(x0, 2, x1, H - 2, fill=(T.PANEL2 if on else T.PANEL),
                               outline="", tags="fg")
            c.create_text((x0 + x1) / 2, H / 2, text=t(lblk), fill=(T.MOON if on else T.SUB),
                          font=self._font(10, True), tags="fg")
        c.tag_lower("vid")

    def _tab_click(self, e):
        W, n = self.tabs_c.winfo_width(), len(self._tabkeys)
        i = int(e.x // (W / n)) if W > 0 else 0
        self._set_tab(self._tabkeys[max(0, min(n - 1, i))][0])

    def _build(self):
        # рамка-кант + внутренний фон (overrideredirect → бордер рисуем сами, как панель)
        outer = tk.Frame(self.win, bg=T.EDGE)
        outer.pack(fill="both", expand=True)
        root = tk.Frame(outer, bg=T.NIGHT)
        root.pack(fill="both", expand=True, padx=2, pady=2)

        # ── свой заголовок (Canvas: видео-фон + текст) — перетаскивание + закрытие ──
        self.head_c = tk.Canvas(root, height=32, bg=T.NIGHT, highlightthickness=0, bd=0)
        self.head_c.pack(fill="x", padx=10, pady=(9, 4))
        self.head_c.bind("<Button-1>", self._press, add="+")
        self.head_c.bind("<B1-Motion>", self._move, add="+")
        self.head_c.bind("<Configure>", lambda e: self._redraw_header())
        self.head_c.tag_bind("close", "<Button-1>", lambda e: self._close())
        self._redraw_header()

        # ── вкладки (Canvas: видео-фон + сегмент-тоггл) ──
        self._tabkeys = [("items", "tab_items"), ("heroes", "tab_heroes"), ("grades", "tab_grades")]
        self.tabs_c = tk.Canvas(root, height=34, bg=T.EDGE, highlightthickness=0, bd=0)
        self.tabs_c.pack(fill="x", padx=10, pady=(2, 0))
        self.tabs_c.bind("<Configure>", lambda e: self._redraw_tabs())
        self.tabs_c.bind("<Button-1>", self._tab_click)
        # тело
        self.body = tk.Frame(root, bg=T.NIGHT)
        self.body.pack(fill="both", expand=True, padx=10, pady=6)
        self._build_items()
        self._build_heroes()
        self._build_grades()
        self._set_tab("items")
        if not self.embedded:
            self._animate_list()    # видео-фон трейлера вшит прямо в Canvas списка

    def _build_items(self):
        self.f_items = tk.Frame(self.body, bg=T.NIGHT)
        # панель фильтров
        bar = tk.Frame(self.f_items, bg=T.NIGHT)
        bar.pack(fill="x")
        tk.Label(bar, text=t("db_search"), bg=T.NIGHT,
                 fg=T.FAINT, font=self._font(8)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._manual)
        entwrap = tk.Frame(bar, bg=T.EDGE)
        entwrap.pack(side="left", padx=6)
        ent = tk.Entry(entwrap, textvariable=self.search_var, width=20, bg=T.PANEL, fg=T.INK,
                       insertbackground=T.MOON, relief="flat", font=self._font(10), bd=0)
        ent.pack(padx=1, pady=1, ipady=3, ipadx=4)

        def _styled_om(parent, var, choices, width, cmd=None):
            wrap = tk.Frame(parent, bg=T.EDGE)
            wrap.pack(side="left", padx=4)
            om = tk.OptionMenu(wrap, var, *choices, command=(cmd or self._manual))
            om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                      relief="flat", bd=0, highlightthickness=0, font=self._font(9),
                      width=width, anchor="w", padx=6, pady=2, cursor="hand2")
            om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2,
                              activeforeground=T.MOON, font=self._font(9), bd=0,
                              relief="flat", activeborderwidth=0)
            om.pack(padx=1, pady=1)
            return om
        self._styled_om = _styled_om

        self.count_lbl = tk.Label(bar, text="", bg=T.NIGHT, fg=T.FAINT, font=self._font(8))
        self.count_lbl.pack(side="right")
        # фильтры — ОТДЕЛЬНЫЙ ряд (в один ряд с поиском не влезали: бар требовал ~1258px при окне
        # 900px, поэтому market/счётчик и панель деталей со ссылкой Steam уезжали за правый край).
        bar2 = tk.Frame(self.f_items, bg=T.NIGHT)
        bar2.pack(fill="x", pady=(3, 0))
        # фильтр тип
        tk.Label(bar2, text=t("f_type"), bg=T.NIGHT, fg=T.FAINT, font=self._font(8)).pack(side="left", padx=(0, 0))
        self.type_var = tk.StringVar(value="all")
        _styled_om(bar2, self.type_var, ["all", "gear", "accessory", "material", "box"], 8)
        # фильтр вид материала (украшение/гравировка/надпись/…)
        tk.Label(bar2, text=t("f_view"), bg=T.NIGHT, fg=T.FAINT, font=self._font(8)).pack(side="left", padx=(4, 0))
        self.mat_var = tk.StringVar(value="all")
        _styled_om(bar2, self.mat_var, ["all"] + list(dict.fromkeys(MAT_RU_SHORT.values())), 12)
        # фильтр грейд
        tk.Label(bar2, text=t("f_grade"), bg=T.NIGHT, fg=T.FAINT, font=self._font(8)).pack(side="left", padx=(4, 0))
        self.grade_var = tk.StringVar(value="all")
        _styled_om(bar2, self.grade_var, ["all"] + GRADE_RU_ALL, 11)
        # фильтр торгуемости (рынок)
        tk.Label(bar2, text=t("f_market"), bg=T.NIGHT, fg=T.FAINT, font=self._font(8)).pack(side="left", padx=(4, 0))
        self.trade_var = tk.StringVar(value="all")
        _styled_om(bar2, self.trade_var, ["all", "торгуется", "не торгуется"], 12)

        # (язык/перевод теперь настраиваются в ⚙ панели бота, не здесь — читаются из config)
        self.lang_lbl = tk.Label(self.f_items, text="", bg=T.NIGHT, fg=T.FAINT, font=self._font(8))
        self.lang_lbl.pack(anchor="w", pady=(4, 0))
        self._update_lang_lbl()
        # список + детали
        split = tk.Frame(self.f_items, bg=T.NIGHT)
        split.pack(fill="both", expand=True, pady=(6, 0))
        lwrap = tk.Frame(split, bg=T.EDGE)
        lwrap.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lwrap, style="Night.Vertical.TScrollbar")
        sb.pack(side="right", fill="y", padx=(0, 1), pady=1)
        # Canvas-список: видео-кадр трейлера = фон, строки рисуются текстом поверх (прозрачно).
        # Не Listbox (тот непрозрачен) — иначе видео за списком не видно.
        self.lb = tk.Canvas(lwrap, bg="#0c0a16", highlightthickness=0, bd=0)
        self.lb.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        self._sb = sb
        self._rows = []                                  # (текст, цвет) видимых строк
        self._scroll = 0
        self._sel = -1
        self._lbtk = None
        self._lbi = 0
        fnt = tkfont.Font(font=self._font(9))
        self._row_h = fnt.metrics("linespace") + 6
        self._load_dbbg()
        sb.config(command=self._list_yview)
        self.lb.bind("<MouseWheel>", self._list_wheel)
        self.lb.bind("<Button-1>", self._on_select)
        self.lb.bind("<Configure>", lambda e: self._redraw_list())
        # детали (Canvas: тот же видео-фон, текст поверх) — «единый фон» до правого края
        self.det = tk.Canvas(split, bg=T.NIGHT, width=300, highlightthickness=0, bd=0)
        self.det.pack(side="right", fill="both", padx=(6, 0))
        self._cur_detail = None
        self._price_id = None
        self._det_url = None
        self.det.tag_bind("mkt", "<Button-1>",
                          lambda e: self._det_url and webbrowser.open(self._det_url))
        self.det.bind("<Configure>", lambda e: self._show_detail(self._cur_detail))
        self._show_detail(None)

    def _build_heroes(self):
        self.f_heroes = tk.Frame(self.body, bg=T.NIGHT)
        wrap = tk.Frame(self.f_heroes, bg=T.NIGHT)
        wrap.pack(fill="both", expand=True)
        tk.Label(wrap, text="клик по герою → оружие его типа", bg=T.NIGHT,
                 fg=T.FAINT, font=self._font(8)).grid(row=0, column=0, columnspan=2,
                                                      sticky="w", pady=(0, 4))
        for i, h in enumerate(_HEROES):
            cls = h.get("ClassType", "?")
            mwk = h.get("MainWeaponGearType", "")
            card = tk.Frame(wrap, bg=T.PANEL, padx=10, pady=8, cursor="hand2")
            card.grid(row=1 + i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
            ttl = tk.Label(card, text=CLASS_RU.get(cls, cls), bg=T.PANEL, fg=T.MOON,
                           font=self._font(12, True))
            ttl.pack(anchor="w")
            mw = GEARTYPE_RU.get(mwk, mwk)
            sw = GEARTYPE_RU.get(h.get("SubWeaponGearType", ""), h.get("SubWeaponGearType", ""))
            sub = tk.Label(card, text=f"оружие: {mw} / {sw}", bg=T.PANEL, fg=T.SUB,
                           font=self._font(9))
            sub.pack(anchor="w")
            stats = (f"⚔ {h.get('AttackDamage','?')}  "
                     f"⚡ {h.get('AttackSpeed','?')}  "
                     f"❤ {h.get('MaxHp','?')}  "
                     f"🛡 {h.get('Armor','?')}  "
                     f"✷ крит {h.get('CriticalChance','?')}")
            st = tk.Label(card, text=stats, bg=T.PANEL, fg=T.FAINT, font=self._font(8))
            st.pack(anchor="w", pady=(3, 0))
            desc = gstr(f"HeroDescription_{h.get('HeroKey','')}", self.lang_main)
            dlbl = None
            if desc:
                dlbl = tk.Label(card, text=" ".join(desc.split()), bg=T.PANEL,
                                fg=T.SUB, font=self._font(8), wraplength=150, justify="left")
                dlbl.pack(anchor="w", pady=(2, 0))
            sk = hero_skills(h.get("HeroKey", ""))
            ns = len(sk["passives"]) + len(sk["actives"])
            skl = tk.Label(card, text=f"🎯 умения и пассивки ({ns}) →", bg=T.PANEL2, fg=T.MOON,
                           font=self._font(8, True), cursor="hand2", padx=6, pady=3)
            skl.pack(anchor="w", pady=(4, 1), fill="x")
            gear = tk.Label(card, text="🗡 предметы этого героя", bg=T.PANEL, fg=T.SUB,
                            font=self._font(7), cursor="hand2")
            gear.pack(anchor="w")
            # клик по карточке героя -> его УМЕНИЯ (главное действие в «Персонажах»)
            for w in (card, ttl, sub, st, skl) + ((dlbl,) if dlbl else ()):
                w.bind("<Button-1>", lambda e, hh=h: self._show_skills(hh))
            gear.bind("<Button-1>", lambda e, g=mwk: self._jump_geartype(g))
        for c in range(2):
            wrap.grid_columnconfigure(c, weight=1)

    def _show_skills(self, h):
        """Попап скиллов героя: аккордеон-дропдаун (клик по названию раскрывает описание).
        Активки — оранжевым (значения по уровням), пассивы — бирюзой (стат+значение)."""
        cls = CLASS_RU.get(h.get("ClassType", ""), h.get("ClassType", "?"))
        sk = hero_skills(h.get("HeroKey", ""))
        loc = self.lang_main
        top = tk.Toplevel(self.win)
        top.configure(bg=T.EDGE)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            px, py = self.win.winfo_rootx() + 40, self.win.winfo_rooty() + 40
        except Exception:
            px, py = 200, 120
        top.geometry(f"440x580+{px}+{py}")
        outer = tk.Frame(top, bg=T.EDGE); outer.pack(fill="both", expand=True)
        rootf = tk.Frame(outer, bg=T.NIGHT); rootf.pack(fill="both", expand=True, padx=2, pady=2)
        # заголовок + перетаскивание
        drag = {"d": (0, 0)}
        hd = tk.Frame(rootf, bg=T.NIGHT); hd.pack(fill="x")
        tl = tk.Label(hd, text=f"🎯 скиллы · {cls}", bg=T.NIGHT, fg=T.MOON, font=self._font(13, True))
        tl.pack(side="left", padx=10, pady=8)
        xb = tk.Label(hd, text="✕", bg=T.NIGHT, fg=T.STOPC, font=self._font(12, True), cursor="hand2")
        xb.pack(side="right", padx=10)
        xb.bind("<Button-1>", lambda e: top.destroy())
        for w in (hd, tl):
            w.bind("<Button-1>", lambda e: drag.__setitem__("d", (e.x_root - top.winfo_x(), e.y_root - top.winfo_y())))
            w.bind("<B1-Motion>", lambda e: top.geometry(f"+{e.x_root - drag['d'][0]}+{e.y_root - drag['d'][1]}"))
        tk.Label(rootf, text="⚠ раздел в разработке — часть игровых описаний недоступна, данные могут быть неполными",
                 bg=T.NIGHT, fg="#f7a93c", font=self._font(8), wraplength=410,
                 justify="left").pack(anchor="w", padx=12, pady=(2, 2))
        # описание героя
        herod = gstr(f"HeroDescription_{h.get('HeroKey','')}", loc)
        if herod:
            tk.Label(rootf, text=" ".join(herod.split()), bg=T.NIGHT, fg=T.INK, font=self._font(9),
                     wraplength=410, justify="left").pack(anchor="w", padx=12, pady=(2, 6))
        # прокручиваемая область
        area = tk.Frame(rootf, bg=T.EDGE); area.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        canvas = tk.Canvas(area, bg=T.NIGHT, highlightthickness=0)
        sb = ttk.Scrollbar(area, orient="vertical", command=canvas.yview, style="Night.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        holder = tk.Frame(canvas, bg=T.NIGHT)
        cwin = canvas.create_window((0, 0), window=holder, anchor="nw")

        def _sr(_=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        holder.bind("<Configure>", _sr)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cwin, width=e.width))
        # колесо активно ТОЛЬКО пока курсор над этим попапом (Enter/Leave) — не нукает
        # глобальные биндинги и не ломает скролл при повторном открытии скиллов
        _wheel = lambda e: canvas.yview_scroll(int(-e.delta / 120), "units")
        top.bind("<Enter>", lambda e: top.bind_all("<MouseWheel>", _wheel))
        top.bind("<Leave>", lambda e: top.unbind_all("<MouseWheel>"))
        top.bind("<Destroy>", lambda e: top.unbind_all("<MouseWheel>"))

        def accordion(title, color, body_lines):
            wrapc = tk.Frame(holder, bg=T.PANEL); wrapc.pack(fill="x", pady=2)
            state = {"open": False}
            head = tk.Label(wrapc, text="▸ " + title, bg=T.PANEL, fg=color, font=self._font(10, True),
                            cursor="hand2", anchor="w", justify="left", wraplength=400, padx=8, pady=5)
            head.pack(fill="x")
            bodyf = tk.Frame(wrapc, bg=T.PANEL)
            for txt, col, sz in body_lines:
                tk.Label(bodyf, text=txt, bg=T.PANEL, fg=col, font=self._font(sz),
                         wraplength=390, justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0, 3))

            def toggle(_=None):
                state["open"] = not state["open"]
                head.config(text=("▾ " if state["open"] else "▸ ") + title)
                bodyf.pack(fill="x", pady=(0, 4)) if state["open"] else bodyf.pack_forget()
                top.after(10, _sr)
            head.bind("<Button-1>", toggle)

        if sk["actives"]:
            tk.Label(holder, text="АКТИВНЫЕ УМЕНИЯ", bg=T.NIGHT, fg=T.MOON,
                     font=self._font(9, True)).pack(anchor="w", pady=(4, 2))
            for a in sk["actives"]:
                nm = gstr(a["name_key"], loc) or f"умение #{a['key']}"
                lv = a["levels"]
                desc = gstr(a["desc_key"], loc) or "—"
                if lv and "{0}" in desc:
                    desc = desc.replace("{0}", str(lv[0]))
                lines = [(desc.strip(), T.INK, 9)]
                if lv:
                    lines.append((f"значение ур.1 → макс: {lv[0]} → {lv[-1]}", T.FAINT, 8))
                accordion(f"{nm}   ·   макс. ур. {a['max']}", "#f7a93c", lines)
        if sk["passives"]:
            tk.Label(holder, text="ПАССИВНЫЕ БОНУСЫ", bg=T.NIGHT, fg=T.MOON,
                     font=self._font(9, True)).pack(anchor="w", pady=(8, 2))
            for p in sk["passives"]:
                nm = gstr(p["name_key"], loc) or p["ru"]
                lines = [(f"{p['ru']} +{p['val']}{p['sign']}   (макс. ур. {p['max']})", "#5ff2e6", 9)]
                if p["stat"] in STAT_EXPLAIN:
                    lines.append((STAT_EXPLAIN[p["stat"]], T.FAINT, 8))
                accordion(nm, "#5ff2e6", lines)
        top.after(30, _sr)

    def _build_grades(self):
        self.f_grades = tk.Frame(self.body, bg=T.NIGHT)
        hdr = tk.Frame(self.f_grades, bg=T.NIGHT)
        hdr.pack(fill="x", pady=(0, 4))
        for txt, w in (("ГРЕЙД", 16), ("слотов укр.", 12), ("гравир.", 9), ("надпись", 9)):
            tk.Label(hdr, text=txt, bg=T.NIGHT, fg=T.FAINT, font=self._font(8, True),
                     width=w, anchor="w").pack(side="left")
        tk.Label(self.f_grades, text="клик по грейду → предметы этого грейда", bg=T.NIGHT,
                 fg=T.FAINT, font=self._font(8)).pack(anchor="w", pady=(0, 4))
        for i, g in enumerate(_GRADES):
            ru = GRADE_RU_ALL[i] if i < len(GRADE_RU_ALL) else g.get("GRADE", "?")
            row = tk.Frame(self.f_grades, bg=T.NIGHT, cursor="hand2")
            row.pack(fill="x", pady=1)
            cells = [
                tk.Label(row, text=ru, bg=T.NIGHT, fg=self._grade_color(ru),
                         font=self._font(10, True), width=16, anchor="w"),
                tk.Label(row, text=g.get("ExtraSlotAmount_Decoration", "0"), bg=T.NIGHT, fg=T.SUB,
                         font=self._font(9), width=12, anchor="w"),
                tk.Label(row, text=g.get("ExtraSlotAmount_Engraving", "0"), bg=T.NIGHT, fg=T.SUB,
                         font=self._font(9), width=9, anchor="w"),
                tk.Label(row, text=g.get("ExtraSlotAmount_Inscription", "0"), bg=T.NIGHT, fg=T.SUB,
                         font=self._font(9), width=9, anchor="w"),
            ]
            for c in cells:
                c.pack(side="left")
            for w in [row] + cells:
                w.bind("<Button-1>", lambda e, r=ru: self._jump_grade(r))

    # ---------- логика ----------
    def _set_tab(self, key):
        self.cur_tab = key
        for f in (self.f_items, self.f_heroes, self.f_grades):
            f.pack_forget()
        {"items": self.f_items, "heroes": self.f_heroes, "grades": self.f_grades}[key].pack(
            fill="both", expand=True)
        if hasattr(self, "tabs_c"):
            self._redraw_tabs()

    def _is_tradeable(self, it):
        return (_ITEM_INFO.get(it["key"], {}).get("IsCanExchangeMarketable", "") or "").lower() == "true"

    def _filtered(self):
        q = self.search_var.get().lower().strip()
        ft = self.type_var.get()
        fg = self.grade_var.get()
        fm = self.mat_var.get() if hasattr(self, "mat_var") else "all"
        ftr = self.trade_var.get() if hasattr(self, "trade_var") else "all"
        out = []
        fgt = self.flt_geartype
        # поиск по СЛОВАМ: каждое слово запроса должно встречаться (как подстрока) в тексте
        # предмета. Так «урон холодом» находит «% урона холодом» («урон»⊂«урона»).
        words = q.split()
        for it in _INDEX:
            txt = it.get("search_text", it["name_l"])
            if words and not all(w in txt for w in words):
                continue
            if ft != "all" and it["type"] != ft:
                continue
            if fm != "all" and MAT_RU_SHORT.get(it.get("mat_kind"), "") != fm:
                continue
            if fg != "all" and it["grade_ru"] != fg:
                continue
            if fgt and it["geartype"] != fgt:
                continue
            if ftr != "all":
                tr = self._is_tradeable(it)
                if (ftr == "торгуется") != tr:
                    continue
            out.append(it)
        return out

    def _jump_grade(self, ru):
        """Клик по грейду -> «Предметы» с фильтром этого грейда."""
        self._suppress = True
        self.flt_geartype = None
        self.search_var.set("")
        self.type_var.set("all")
        self.grade_var.set(ru)
        self._suppress = False
        self._set_tab("items")
        self._refresh_items()

    def _jump_geartype(self, gt, title=""):
        """Клик по герою -> «Предметы», отфильтрованные по виду оружия героя."""
        self._suppress = True
        self.search_var.set("")
        self.type_var.set("all")
        self.grade_var.set("all")
        self.flt_geartype = gt
        self._suppress = False
        self._set_tab("items")
        self._refresh_items()

    def _update_lang_lbl(self):
        cur = LANG_LABELS.get(self.lang_main, self.lang_main)
        if self.translate_on and self.lang_tr != self.lang_main:
            cur += f"  {t('translate')}: {LANG_LABELS.get(self.lang_tr, self.lang_tr)}"
        try:
            self.lang_lbl.config(text=f"{t('db_lang')} {cur}")
        except Exception:
            pass

    def set_language(self, locale):
        """Live-смена языка БД (имена предметов) без перезапуска — вызывается из панели."""
        if locale not in LOCALES:
            return
        self.lang_main = locale
        self._update_lang_lbl()
        try:
            self._refresh_items()        # перерисовать список с новыми именами
        except Exception:
            pass

    def _fetch_price(self, en, item_id):
        """Подтянуть цену Steam в фоне и обновить canvas-элемент (UI — только из главного потока)."""
        def work():
            p = steam_price(en)

            def upd():
                try:
                    if not self.det.winfo_exists():
                        return
                    if p and p.get("low"):
                        txt = f"💰 Steam: {p['low']}"
                        if p.get("median"):
                            txt += f" · ~{p['median']}"
                        if p.get("vol"):
                            txt += f" · {p['vol']}/24h"
                        self.det.itemconfigure(item_id, text=txt, fill=T.GO)
                    else:
                        self.det.itemconfigure(item_id, text=t("price_none"), fill=T.FAINT)
                except Exception:
                    pass
            try:
                self.win.after(0, upd)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def set_translate(self, locale):
        """Live-смена языка перевода-оверлея (имя в 〔скобках〕). None -> выключить."""
        if locale is None:
            self.translate_on = False
        elif locale in LOCALES:
            self.translate_on = True
            self.lang_tr = locale
        else:
            return
        self._update_lang_lbl()
        try:
            self._refresh_items()
        except Exception:
            pass

    def _refresh_items(self):
        self._cur = self._filtered()
        # Canvas-список виртуальный (рисует только видимые строки) → показываем ВЕСЬ результат,
        # без лимита 400. Иначе казалось, что БД неполная.
        self._rows = []
        for it in self._cur:
            lvl = f"Lv{it['level']:>3}" if it["level"] else "  — "   # заметный уровень-колонка слева
            gt = f" · {i18n.gtype(GEARTYPE_RU.get(it['geartype'], ''))}" if it["geartype"] else ""
            nm = self._disp_name(it)
            tr = self._tr_name(it)
            tr_s = f"  〔{tr}〕" if tr else ""        # перевод в скобках рядом
            txt = f"{lvl} │ {nm}{tr_s}  · {i18n.grade(it['grade_ru'])}{gt}"
            self._rows.append((txt, self._grade_color(it["grade_ru"])))
        self._sel = -1
        self._scroll = 0
        self._redraw_list()
        self.count_lbl.config(text=f"найдено ({len(self._cur)})")

    def _on_select(self, e):
        idx = (self._scroll + e.y) // self._row_h
        if idx < 0 or idx >= len(self._rows):
            return
        self._sel = idx
        self._redraw_list()
        self._show_detail(self._cur[idx])

    def _show_detail(self, it):
        """Детальная панель = Canvas: видео-кадр снизу (тег vid), факты = create_text поверх (тег fg)."""
        if not hasattr(self, "det") or not self.det.winfo_exists():
            return
        self._cur_detail = it
        c = self.det
        c.delete("fg")
        self._price_id = None
        self._det_url = None
        pad = 10
        W = c.winfo_width() or 300
        wrapw = max(120, W - 2 * pad)
        self._dy = 10

        def adv(*ids):
            b = 0
            for i in ids:
                bb = c.bbox(i)
                if bb:
                    b = max(b, bb[3])
            if b:
                self._dy = b

        def line(text, color, font, gap=2, wrap=wrapw):
            tid = c.create_text(pad, self._dy, anchor="nw", text=text, fill=color,
                                font=font, width=wrap, tags="fg")
            adv(tid)
            self._dy += gap
            return tid

        def row(label, val, color=None):
            a = c.create_text(pad, self._dy, anchor="nw", text=label, fill=T.FAINT,
                              font=self._font(8), width=84, tags="fg")
            b = c.create_text(pad + 90, self._dy, anchor="nw", text=str(val),
                              fill=color or T.INK, font=self._font(9), width=wrapw - 90, tags="fg")
            adv(a, b)
            self._dy += 2

        if it is None:
            c.create_text(pad, 14, anchor="nw", text=t("select_item"), fill=T.INK,
                          font=self._font(9), tags="fg")
            c.tag_lower("vid")
            return

        line(self._disp_name(it), self._grade_color(it["grade_ru"]), self._font(13, True), gap=1)
        tr = self._tr_name(it)
        if tr:
            line(tr, T.SUB, self._font(9), gap=2)
        # грейд + крупный уровень в одну строку
        gid = c.create_text(pad, self._dy, anchor="nw", text=i18n.grade(it["grade_ru"]).upper(),
                            fill=self._grade_color(it["grade_ru"]), font=self._font(9, True), tags="fg")
        ids = [gid]
        if it["level"]:
            ids.append(c.create_text(W - pad, self._dy, anchor="ne", text=f"Lv. {it['level']}",
                                     fill=T.MOON, font=self._font(14, True), tags="fg"))
        adv(*ids)
        self._dy += 3
        info = _ITEM_INFO.get(it["key"], {})
        row(t("r_type"), i18n.gtype(TYPE_RU.get(it["type"], it["type"])))
        if it.get("mat_kind"):
            row(t("r_view"), i18n.gtype(MAT_RU.get(it["mat_kind"], it["mat_kind"].lower())), "#5ff2e6")
        if it["part_ru"]:
            row(t("r_slot"), i18n.gtype(it["part_ru"]))
        if it["geartype"]:
            row(t("r_view"), i18n.gtype(GEARTYPE_RU.get(it["geartype"], it["geartype"].lower())))
        tradeable = (info.get("IsCanExchangeMarketable", "") or "").lower() == "true"
        row(t("r_market"), (t("tradeable") + " Steam") if tradeable else t("not_tradeable"),
            T.GO if tradeable else T.FAINT)
        if tradeable:
            hashn = market_hash_name(it)
            en = name_in(it["key"], "en-US")
            url = steam_listing_url(hashn) or steam_search_url(en)
            if url:
                self._det_url = url
                line("▸ " + t("market_btn"), T.MOON, self._font(9, True), gap=3)
                # тег mkt на последний элемент — клик открывает листинг
                last = c.find_withtag("fg")[-1]
                c.itemconfig(last, tags=("fg", "mkt"))
                self._price_id = line(t("price_loading"), T.SUB, self._font(8), gap=1)
                self._fetch_price(hashn or en, self._price_id)
                line(t("market_hint"), T.FAINT, self._font(7), gap=2)
        gold = alchemy_gold(it["key"])
        if gold:
            row(t("r_alch"), f"≈ {_fmt_gold(gold)} {t('gold')}", T.MOON)
        cexp = _GRADE_CUBEEXP.get(info.get("GRADE", ""))
        if cexp:
            row(t("r_cubexp"), f"+{_fmt_gold(cexp)}")
        if it.get("gems"):
            _give_hdr = {"DECORATION": "камень даёт (зависит от слота):",
                         "ENGRAVING": "гравировка даёт (зависит от слота):",
                         "INSCRIPTION": "надпись даёт (зависит от слота):"}.get(
                             it.get("mat_kind"), "даёт (зависит от слота):")
            self._dy += 4
            line(_give_hdr, T.FAINT, self._font(8, True), gap=1)
            for s in it["gems"]:
                line("• " + s, "#5ff2e6", self._font(9), gap=1)
        stats = item_stats(it["key"])
        if stats:
            self._dy += 4
            line(t("traits_hdr"), T.FAINT, self._font(8, True), gap=1)
            for s in stats:
                line("• " + s, T.INK, self._font(9), gap=1)
        gi = _GEAR_INFO.get(info.get("GearKey", ""))
        um = (gi or {}).get("UniqueModKey", "")
        if um:
            umname = _UNIQUE_MOD.get(um, "")
            umtext = gstr(f"UniqueMod_{umname}", self.lang_main) if umname else None
            self._dy += 4
            line("★ уникальный модификатор", T.MOON, self._font(8, True), gap=0)
            line(umtext or _split_code(umname) or f"#{um}", T.INK, self._font(8), gap=2)
        self._dy += 6
        line(f"id: {it['key']}", T.FAINT, self._font(7), gap=2)
        note = item_note(it, info)
        if note:
            self._dy += 4
            c.create_line(pad, self._dy, W - pad, self._dy, fill=T.EDGE, tags="fg")
            self._dy += 4
            line(t("note_hdr"), T.MOON, self._font(8, True), gap=1)
            line(note, T.SUB, self._font(8), gap=2)
        c.tag_lower("vid")


def open_browser(root, height=None, query=None):
    """Открыть браузер БД рядом с панелью. height — под высоту панели. query — сразу искать.
    (НЕ называть 'open' — перекрывало builtin open(), из-за чего _save_lang/_load_cfg падали.)"""
    b = DBBrowser(root, height=height)
    if query:
        b.set_search(query)
    return b


def main():
    root = tk.Tk()
    root.withdraw()
    b = DBBrowser(root)
    b._own_root = True   # ✕ закроет и скрытый root → выход из mainloop
    root.bind_all("<Escape>", lambda e: b._close())
    root.mainloop()


if __name__ == "__main__":
    main()
