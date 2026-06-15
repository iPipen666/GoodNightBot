"""log_templates.py — матчеры лог-событий, собранные из game_strings_i18n.json (авторитет игры).

Вместо ручных регэкспов берём ШАБЛОНЫ игры (`LogMessage_*`, значения = {lang: 'Получено {0}.'})
и превращаем их в regex: rich-теги (<color>/<br>) убираем, литералы экранируем, `{N}` → группы
захвата. Делаем это для ВСЕХ языков → строка лога матчится независимо от языка игры.

Источник: d:/FOR_MYSELF/TBH_BOT/game_strings_i18n.json (16 языков). Если игра обновит строки —
переэкстрактить файл, код не трогать.
"""
import os
import re
import json

HERE = os.path.dirname(os.path.abspath(__file__))
_STRINGS = os.path.join(HERE, "game_strings_i18n.json")

_TAG = re.compile(r"<[^>]+>")            # <color=#..>, </color>, <br> — в OCR их нет
_PH = re.compile(r"\{(\d+)\}")           # плейсхолдеры {0},{1},{2}

# Ключ LogMessage_* -> наш тип события. 'obtained'/'getbox' = «Получено {0}» (сундук ИЛИ предмет —
# разводим по ключевому слову «сундук»). Остальные однозначны.
_EVENT_KEYS = {
    "LogMessage_StageClear": "stage_clear",
    "LogMessage_StageFailed": "stage_fail",
    "LogMessage_HeroDie": "defeat",
    "LogMessage_HeroResurrection": "revive",
    "LogMessage_HeroLevelUp": "levelup",
    "LogMessage_SynthesisResult": "synthesis",
    "LogMessage_CraftingResult": "craft",
    "LogMessage_AlchemyResult": "alchemy",
    "LogMessage_GetBox": "getbox",                  # 'Получено {0}. ({1})' — сундук с мобом
    "LogMessage_GetItemWithBoxOpen": "obtained",    # 'Получено {0}.' — предмет из сундука
}
_CHEST_KEYS = {
    "TreasureChest_Normal": "normal",
    "TreasureChest_StageBoss": "stage_boss",
    "TreasureChest_ActBoss": "act_boss",
}


def _tpl_to_regex(tpl):
    """Шаблон игры → строка-regex, ТОЛЕРАНТНЫЙ к OCR-обрезке хвоста (маркиза режет конец длинной
    строки). Стратегия: каждый плейсхолдер non-greedy '.+?'; конец якорим '\\s*$' → финальное поле
    тянется до терминатора ИЛИ до обрыва. Литерал-хвост ПОСЛЕ последнего {N}:
      • чистая пунктуация/скобки (')' '.') → опционален (OCR не дочитывает: 'defeated. (Frozen Hell');
      • с буквами (' has revived.') → ОБЯЗАТЕЛЕН (отличающий литерал; иначе матчер ловит любую строку).
    Примеры: 'Obtained {0}.'→ имя целиком даже без точки; 'X has been defeated. ({1})'→ ловит обрезку."""
    s = _TAG.sub("", tpl).strip()
    toks = re.split(r"(\{\d+\})", s)
    ph_idx = [i for i, t in enumerate(toks) if re.fullmatch(r"\{\d+\}", t)]
    last_ph = ph_idx[-1] if ph_idx else -1
    out = []
    for i, t in enumerate(toks):
        m = re.fullmatch(r"\{(\d+)\}", t)
        if m:
            out.append(r"(?P<f%s>.+?)" % m.group(1))
        else:
            esc = re.escape(t)
            if last_ph >= 0 and i > last_ph and t and not re.search(r"[^\W\d_]", t):
                esc = "(?:%s)?" % esc            # пунктуация-хвост опциональна (OCR режет)
            out.append(esc)
    rx = "".join(out)
    if last_ph >= 0:
        rx += r"\s*$"                            # якорь конца → последнее поле захватывает всё до обрыва
    return rx


def _lcs(a, b):
    """Наибольшая общая подстрока (lower)."""
    a, b = a.lower(), b.lower()
    best = ""
    for i in range(len(a)):
        for j in range(i + 1, len(a) + 1):
            sub = a[i:j]
            if len(sub) > len(best) and sub in b:
                best = sub
    return best


_CACHE = None


def _load():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    bk = json.load(open(_STRINGS, encoding="utf-8")).get("by_key", {})
    langs = list(next(iter(bk.values())).keys()) if bk else []

    matchers = []                 # (event_type, compiled_regex)
    chest_core = {}               # lang -> общая подстрока имён сундуков ('сундук с сокровищами')
    chest_kind_words = {}         # lang -> {'stage_boss': 'этапа', 'act_boss': 'акта'}

    # имена сундуков по языкам -> ядро + отличающие слова для kind
    for lang in langs:
        names = {}
        for key, kind in _CHEST_KEYS.items():
            v = bk.get(key, {})
            nm = v.get(lang) if isinstance(v, dict) else None
            if nm:
                names[kind] = _TAG.sub("", nm).strip()
        if "normal" in names and "stage_boss" in names:
            core = _lcs(names["normal"], names["stage_boss"])
            if "act_boss" in names:
                core = _lcs(core, names["act_boss"]) or core
            chest_core[lang] = core.strip()
            kw = {}
            for kind in ("stage_boss", "act_boss"):
                if kind in names and core:
                    extra = names[kind].lower().replace(core, " ").strip()
                    if extra:
                        kw[kind] = extra
            chest_kind_words[lang] = kw

    # матчеры событий из LogMessage_* для всех языков
    for key, etype in _EVENT_KEYS.items():
        v = bk.get(key, {})
        if not isinstance(v, dict):
            continue
        for lang, tpl in v.items():
            if not tpl:
                continue
            try:
                rx = re.compile(_tpl_to_regex(tpl), re.I | re.U)
            except re.error:
                continue
            matchers.append((etype, rx, lang))

    _CACHE = {"matchers": matchers, "chest_core": chest_core,
              "chest_kind_words": chest_kind_words, "langs": langs}
    return _CACHE


def chest_kind_for(text, lang):
    """Тип сундука по тексту имени ({0}) и языку: stage_boss/act_boss/normal.
    🔴 ФИКС обрезки: слово-маркер ('этапа'/'акта' / EN 'stage'/'act') идёт ПОСЛЕ ядра имени
    («сундук с сокровищами …»), и маркиза часто режет ему ХВОСТ ('этапа'→'эта') → boss-сундук
    ошибочно падал в normal (живьём: 'Получено Сундук с сокровищами эта!' считался normal,
    stage_boss=0). Решение: матчим ПРЕФИКС маркера (≥3) в ХВОСТЕ после ядра имени."""
    low = (text or "").lower()
    c = _load()
    kw = c["chest_kind_words"].get(lang, {})
    core = c["chest_core"].get(lang, "")
    tail = low.split(core, 1)[1] if core and core in low else low   # хвост после «…сокровищами»
    for kind in ("stage_boss", "act_boss"):
        m = kw.get(kind)
        if not m:
            continue
        pref = m[: max(3, len(m) - 2)]                              # 'этапа'→'эта', 'акта'→'акт'
        if m in low or (len(pref) >= 3 and pref in tail):
            return kind
    return "normal"


def is_chest_name(text, lang):
    """Это имя сундука (содержит ядро 'сундук с сокровищ…')?"""
    core = _load()["chest_core"].get(lang, "")
    return bool(core) and core in (text or "").lower()


def detect_chest(text):
    """Фолбэк для ОБРЕЗАННЫХ строк сундука (без точки/мобa, матчер не сработал): ядро имени сундука
    есть в строке? → (kind, lang) или (None, None). Ловит «…Получено Обычный сундук с сокрови…»."""
    low = (text or "").lower()
    for lang, core in _load()["chest_core"].items():
        # ядро ('сундук с сокровищами'/'treasure chest') может быть обрезано → ищем значимое слово.
        # len≥6 (не ≥5): голое англ. 'chest'(5) ложно ловило имена файлов (chest_calibration.json,
        # chest_stock.py) через ПРОЗРАЧНЫЙ оверлей; 'treasure'(8)/'сундук'(6)/'сокровищами'(11) проходят.
        words = [w for w in re.split(r"\s+", core) if len(w) >= 6]
        if words and any(w in low for w in words):
            return chest_kind_for(text, lang), lang
    return None, None


def matchers():
    """Список (event_type, compiled_regex, lang) по всем языкам."""
    return _load()["matchers"]


def langs():
    return _load()["langs"]


if __name__ == "__main__":
    import sys
    c = _load()
    sys.stdout.reconfigure(encoding="utf-8")
    print("langs:", len(c["langs"]), "| matchers:", len(c["matchers"]))
    print("chest_core[ru-RU]:", repr(c["chest_core"].get("ru-RU")))
    print("chest_kind_words[ru-RU]:", c["chest_kind_words"].get("ru-RU"))
    print("chest_core[en-US]:", repr(c["chest_core"].get("en-US")))
