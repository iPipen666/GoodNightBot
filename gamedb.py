"""
gamedb.py — loader for gamedb/ normalized datasets.
stdlib + json only.  Import-safe: no side effects at module level beyond populating _cache.

Usage:
    import gamedb
    all_stages  = gamedb.stages()            # list of 120 merged stage records
    en_name     = gamedb.name_in(gamedb.stages()[0], 'en-US')   # "Pasture"
    sources     = gamedb.drop_sources('310001')                  # list or []
"""

import json
import os
import functools
import urllib.request

_HERE  = os.path.dirname(os.path.abspath(__file__))
_GDIR  = os.path.join(_HERE, "gamedb")
# gamedb/ тяжёлый (drop_map/box_index) и в установщик НЕ идёт → у юзеров тянем датасеты с GitHub raw
# при первом обращении и кэшируем в LOCALAPPDATA. Dev-машина использует локальный gamedb/ напрямую.
_CACHE = os.path.join(os.environ.get("LOCALAPPDATA", _HERE), "GoodNightBot", "gamedb_cache")
_RAW   = "https://raw.githubusercontent.com/iPipen666/GoodNightBot/main/gamedb"

# Locale preference order for name_in fallback
_LOCALE_FALLBACK = ("en-US", "ru-RU")

# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

_cache: dict = {}


def _read_json(fp):
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _fetch(fn: str):
    """Скачать gamedb/<fn> с GitHub raw в локальный кэш. Вернуть данные или None (оффлайн/ошибка)."""
    try:
        req = urllib.request.Request(f"{_RAW}/{fn}", headers={"User-Agent": "GoodNightBot"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
        os.makedirs(_CACHE, exist_ok=True)
        with open(os.path.join(_CACHE, fn), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data
    except Exception:
        return None


def load(name: str):
    """gamedb/<name>.json: локальный gamedb/ (dev) → кэш → GitHub raw (fetch+cache).
    Оффлайн при первом обращении → {} (браузер покажет пусто, без падения)."""
    if name in _cache:
        return _cache[name]
    fn = name if name.endswith(".json") else name + ".json"
    data = _read_json(os.path.join(_GDIR, fn))          # dev-машина: локальные файлы
    if data is None:
        data = _read_json(os.path.join(_CACHE, fn))     # ранее скачанный кэш
    if data is None:
        data = _fetch(fn)                               # скачать с GitHub raw
    _cache[name] = data if data is not None else {}
    return _cache[name]


# ---------------------------------------------------------------------------
# name_in — unified name resolver for any record shape
# ---------------------------------------------------------------------------

def name_in(rec: dict, locale: str, fallback=None) -> str:
    """
    Return the display name of a record in the requested locale.

    Tries these field names in order (all are i18n dicts mapping locale→str):
        name, name_i18n, NameKey_i18n, MonsterNameStringKey_i18n,
        CurrencyNameStringKey_i18n, SkillNameKey_i18n, TooltipStringKey_i18n

    Fallback order: locale → en-US → ru-RU → first non-empty value → fallback
    """
    _NAME_FIELDS = (
        "name", "name_i18n", "NameKey_i18n",
        "MonsterNameStringKey_i18n", "CurrencyNameStringKey_i18n",
        "SkillNameKey_i18n", "TooltipStringKey_i18n",
    )
    d = None
    for field in _NAME_FIELDS:
        v = rec.get(field)
        if isinstance(v, dict) and v:
            d = v
            break
    if d is None:
        return fallback
    # locale chain
    result = d.get(locale)
    if result:
        return result
    for fb in _LOCALE_FALLBACK:
        result = d.get(fb)
        if result:
            return result
    # first non-empty value
    for v in d.values():
        if v:
            return v
    return fallback


# ---------------------------------------------------------------------------
# Dataset accessors (list returns — add more as needed)
# ---------------------------------------------------------------------------

def stages():
    """All 120 merged stage records (stages.json + farm_stages fields)."""
    return load("stages")


def monsters():
    """61 monster records."""
    return load("monsters")


def runes():
    """197 rune records."""
    return load("runes")


def rune_tree():
    """Dict with keys: startNodes, bounds, nodes, edges."""
    return load("rune_tree")


def skills():
    """106 active skill records."""
    return load("skills")


def passive_skills():
    """108 passive skill records."""
    return load("passive_skills")


def buffs():
    """29 buff records."""
    return load("buffs")


def status_effects():
    """6 status effect records (each embeds its buff list)."""
    return load("status_effects")


def pets():
    """8 pet records (each embeds its stats list)."""
    return load("pets")


def materials():
    """125 material records (with name/grade from items.json)."""
    return load("materials")


def currencies():
    """1 currency record."""
    return load("currencies")


def cube_recipes():
    """8 cube recipe records."""
    return load("cube_recipes")


def mechanics():
    """Dict of mechanic enumerations (statTypes, modTypes, damageElements…)."""
    return load("mechanics")


def stat_strings():
    """117 stat label i18n records."""
    return load("stat_strings")


def drop_map_all():
    """Full drop_map dict: {itemId_str|'group:<id>': [{box, boxName, pct, stages}]}."""
    return load("drop_map")


def box_index_all():
    """Full box_index dict: {boxId_str: {name_i18n, entries, stages}}."""
    return load("box_index")


def drop_sources(item_id) -> list:
    """
    Return drop sources for a given item id (int or str).
    Returns list of {box, boxName, pct, stages} or [] if not found.
    Unresolved item groups are keyed as 'group:<groupId>' in drop_map.
    """
    return drop_map_all().get(str(item_id), [])


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _stages_by_key():
    return {s["key"]: s for s in stages()}


def stage_by_key(key: int):
    """Look up a single stage by its integer key."""
    return _stages_by_key().get(key)


@functools.lru_cache(maxsize=None)
def _monsters_by_key():
    return {m["MonsterKey"]: m for m in monsters()}


def monster_by_key(key: int):
    return _monsters_by_key().get(key)


@functools.lru_cache(maxsize=None)
def _runes_by_key():
    return {r["RuneKey"]: r for r in runes()}


def rune_by_key(key: int):
    return _runes_by_key().get(key)


# ---------------------------------------------------------------------------
# Self-test (run via: python -c "import gamedb; gamedb._selftest()")
# ---------------------------------------------------------------------------

def _selftest():
    print(f"stages:         {len(stages())} records")
    print(f"monsters:       {len(monsters())} records")
    print(f"runes:          {len(runes())} records")
    print(f"skills:         {len(skills())} records")
    print(f"passive_skills: {len(passive_skills())} records")
    print(f"buffs:          {len(buffs())} records")
    print(f"status_effects: {len(status_effects())} records")
    print(f"pets:           {len(pets())} records")
    print(f"materials:      {len(materials())} records")
    print(f"currencies:     {len(currencies())} records")
    print(f"cube_recipes:   {len(cube_recipes())} records")
    print(f"stat_strings:   {len(stat_strings())} records")
    print(f"drop_map keys:  {len(drop_map_all())}")
    print(f"box_index keys: {len(box_index_all())}")

    stage0 = stages()[0]
    n = name_in(stage0, "en-US")
    print(f"stages()[0] en-US name: {n!r}")
    assert n == "Pasture", f"Expected 'Pasture', got {n!r}"

    src = drop_sources(310001)
    assert len(src) > 0, "drop_sources(310001) returned []"
    boxes = [e["box"] for e in src]
    assert 920002 in boxes, f"920002 not in boxes for 310001: {boxes}"
    print(f"drop_sources(310001): boxes={boxes}  pct={src[0]['pct']}")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    _selftest()
