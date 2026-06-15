# items.py — OCR-ридер тултипов предметов (Волна 1)
# Наводит курсор БЕЗ клика, снимает область тултипа, распознаёт Tesseract rus,
# парсит структуру предмета: имя, ранг, тип, требование уровня, торгуемость.

import os
import json
import re
import time

import numpy as np
import cv2
import pytesseract

import human
import idle
import vision

# ─── константы модуля ───
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
TOOLTIP = CFG.get("tooltip", {})
DB_PATH = os.path.join(HERE, "items_db.json")

# ─── инициализация Tesseract (при импорте) ───
def _resolve_tesseract():
    """Путь к tesseract.exe: из конфига -> локальный .tesseract -> Program Files."""
    cand = [CFG.get("ocr", {}).get("tesseract_cmd"),
            os.path.join(HERE, ".tesseract", "tesseract.exe"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]
    for p in cand:
        if p and os.path.exists(p):
            return p
    return cand[0] or r"C:\Program Files\Tesseract-OCR\tesseract.exe"


pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract()
OCR_LANG = CFG.get("ocr", {}).get("lang", "rus")

# ─── карта ранг-слово → индекс тира (0..9). Канон — русский (для логов/цветов/ключей). ───
RANK_TIERS = [
    "обычный", "необычный", "редкий", "легендарный", "бессмертный",
    "аркана", "запредельный", "celestial", "божественный", "космический"
]
# английские эквиваленты (игра может быть на English) — тот же порядок тиров
RANK_TIERS_EN = [
    "common", "uncommon", "rare", "legendary", "immortal",
    "arcana", "beyond", "celestial", "divine", "cosmic"
]
# слово (ru/en) -> tier; для поиска вхождения в OCR-тексте
_RANK_WORD2TIER = {}
for _i, (_ru, _en) in enumerate(zip(RANK_TIERS, RANK_TIERS_EN)):
    _RANK_WORD2TIER[_ru] = _i
    _RANK_WORD2TIER[_en] = _i


def rank_to_tier(word):
    """Слово ранга (ru или en, любой регистр, возможен OCR-мусор по краям) -> тир 0..9 / -1."""
    if not word:
        return -1
    w = word.lower().strip()
    for t, i in _RANK_WORD2TIER.items():
        if w == t or w in t or t in w:
            return i
    return -1


# ─── категории типов для маршрутизации в policy ───
ACCESSORY_WORDS = ["кольцо", "амулет", "браслет", "наруч", "серьга", "серьги"]

# ─── АВТОРИТЕТНЫЙ справочник items_db.json (собран build_db.py из файлов игры) ───
# Формат: {"meta":..., "by_name": {norm_name: {type,parts,part_ru,geartype,accessory,
#          grades,grades_ru,min_level,max_level,...}}, "by_key": {...}}
# by_name даёт надёжный ТИП/СЛОТ/бижутерию по имени (имя→тип консистентно, 0 конфликтов).
import difflib

_DB = {}
BY_NAME = {}
BY_KEY = {}
if os.path.exists(DB_PATH):
    try:
        with open(DB_PATH, encoding="utf-8") as _f:
            _DB = json.load(_f)
        BY_NAME = _DB.get("by_name", {})
        BY_KEY = _DB.get("by_key", {})
    except Exception:
        _DB, BY_NAME, BY_KEY = {}, {}, {}
# обратная совместимость: старый код мог дергать ITEMS_DB
ITEMS_DB = BY_NAME
_NAME_KEYS = list(BY_NAME.keys())


def db_norm(s):
    """Нормализация имени для матчинга OCR: lower, ё->е, только буквы/цифры/пробел (ru+en)."""
    if not s:
        return ""
    s = s.lower().replace("ё", "е").strip()
    s = re.sub(r"[^а-я0-9a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ─── английский индекс имён (игра может быть на English): norm(en) -> запись с типом/слотом ───
EN_BY_NAME = {}
_I18N_PATH = os.path.join(HERE, "item_names_i18n.json")
if os.path.exists(_I18N_PATH) and BY_KEY:
    try:
        _i18n = json.load(open(_I18N_PATH, encoding="utf-8")).get("by_key", {})
        for _ik, _rec in BY_KEY.items():
            _en = _i18n.get(_ik, {}).get("en-US")
            if not _en:
                continue
            _n = db_norm(_en)
            if _n and _n not in EN_BY_NAME:
                EN_BY_NAME[_n] = {"name": _en, "type": _rec.get("type"),
                                  "accessory": _rec.get("accessory", False),
                                  "part_ru": _rec.get("part_ru"), "geartype": _rec.get("geartype"),
                                  "grades_ru": None,
                                  "min_level": _rec.get("level"), "max_level": _rec.get("level")}
    except Exception:
        EN_BY_NAME = {}
_EN_KEYS = list(EN_BY_NAME.keys())


def classify(name, fuzzy_cutoff=0.82):
    """Имя предмета (OCR, ru ИЛИ en) -> запись с типом/слотом/каноничным именем, или None.
    Порядок: точное ru -> точное en -> подстрока/нечётко ru -> нечётко en."""
    if not name:
        return None
    n = db_norm(name)
    if not n:
        return None
    if n in BY_NAME:
        return BY_NAME[n]
    if n in EN_BY_NAME:
        return EN_BY_NAME[n]
    for k in _NAME_KEYS:        # подстрока по ru (OCR мог дочитать частично)
        if (n in k or k in n) and abs(len(n) - len(k)) <= max(4, len(k) // 3):
            return BY_NAME[k]
    m = difflib.get_close_matches(n, _NAME_KEYS, n=1, cutoff=fuzzy_cutoff)
    if m:
        return BY_NAME[m[0]]
    m = difflib.get_close_matches(n, _EN_KEYS, n=1, cutoff=fuzzy_cutoff)
    return EN_BY_NAME[m[0]] if m else None


def db_lookup(name):
    """Совместимость: вернуть запись by_name по имени (точно/нечётко) или None."""
    return classify(name)


def db_learn(name, type=None, rank=None):
    """No-op: справочник авторитетный (build_db.py из файлов игры). Оставлено для
    обратной совместимости со старыми вызовами."""
    return


# ─── внутренние хелперы ───

def _preprocess(img):
    """BGR ndarray → grayscale → upscale × TOOLTIP.upscale. БЕЗ Otsu-порога:
    тултип = светлый текст на тёмном фоне, Otsu его убивает (проверено: чистый
    grayscale читается «Ранг Обычный...», а Otsu даёт пусто)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scale = float(TOOLTIP.get("upscale", 2.0))
    if scale != 1.0:
        h, w = gray.shape
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    return gray


def _read_name(img):
    """Имя предмета из орнаментального заголовка тултипа (верхняя полоса бокса).
    Отдельный OCR: psm 6 + ×4 апскейл; чистим токены (орнамент-рамка даёт мусор
    слева — короткие/повторяющиеся фрагменты). None если не прочиталось."""
    h, w = img.shape[:2]
    strip = img[18:72, 55:max(56, w - 55)]
    g = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    txt = pytesseract.image_to_string(g, lang=OCR_LANG, config="--psm 6")
    words = []
    for tok in re.findall(r"[A-Za-zА-Яа-яЁё]{3,}", txt):   # ru И en (игра может быть на English)
        if re.search(r"(.)\1\1", tok):   # 3+ одинаковых подряд = мусор орнамента
            continue
        words.append(tok)
    return " ".join(words) if words else None


def _tooltip_box(slot_xy, flip=None):
    """Бокс тултипа относительно базы. flip: 'right' (СТЭШ) / 'left' (HERO) —
    куда игра отрисовывает тултип; None -> default_flip из конфига.
    База = idle.cursor_pos() если anchor=='cursor', иначе slot_xy.
    Вернуть dict {left, top, width, height}, зажав left>=0, top>=0."""
    flip = flip or TOOLTIP.get("default_flip", "right")
    box = TOOLTIP.get("boxes", {}).get(flip, {})
    dx = int(box.get("dx", 25))
    dy = int(box.get("dy", -110))
    w = int(box.get("w", 370))
    h = int(box.get("h", 470))
    if TOOLTIP.get("anchor", "cursor") == "cursor":
        base_x, base_y = idle.cursor_pos()
    else:
        base_x, base_y = slot_xy
    left = max(0, base_x + dx)
    top = max(0, base_y + dy)
    return {"left": left, "top": top, "width": w, "height": h}


# ─── публичные сигнатуры ───

_GAME_HWND = None


def _ensure_focus():
    """Гарантировать, что окно игры в фокусе (Unity рисует тултипы только в
    foreground-окне). Дёшево: alt-трюк-фокус только если окно ещё не foreground.
    hwnd кэшируется."""
    global _GAME_HWND
    if _GAME_HWND is None:
        _GAME_HWND = human.find_hwnd(CFG["window_title_contains"])
    if not _GAME_HWND:
        return False
    if human._user32.GetForegroundWindow() == _GAME_HWND:
        return True
    return human.focus_window(_GAME_HWND)


def hover(slot_xy, settle=None):
    """Навести курсор для появления тултипа Unity. КРИТИЧНО: окно должно быть в
    фокусе (raw-input), а движение — через SendInput (human.move_abs), иначе без
    физической мыши тултип не обновляется. settle-пауза. Без grab/OCR.
    settle: переопределить паузу появления тултипа (для быстрого скана)."""
    _ensure_focus()
    human.move_abs(slot_xy[0], slot_xy[1],
                   nudge=int(TOOLTIP.get("nudge", 14)),
                   settle=float(TOOLTIP.get("nudge_settle", 0.08)))
    s = float(TOOLTIP.get("hover_settle", 0.45)) if settle is None else float(settle)
    time.sleep(s)


def _ocr_box(sct, slot_xy, flip):
    """Снять+OCR один бокс тултипа для заданного flip. Вернуть (result_dict, img)."""
    box = _tooltip_box(slot_xy, flip)
    img = np.array(sct.grab(box))[:, :, :3]   # mss BGRA -> BGR
    txt = pytesseract.image_to_string(_preprocess(img), lang=OCR_LANG)
    return parse_tooltip(txt), img


def _ocr_box_at(sct, box):
    """OCR произвольного бокса {left,top,width,height} -> (result, img)."""
    img = np.array(sct.grab(box))[:, :, :3]
    txt = pytesseract.image_to_string(_preprocess(img), lang=OCR_LANG)
    return parse_tooltip(txt), img


def read_item(sct, slot_xy, flip=None, settle=None):
    """Навести на слот (без клика), снять тултип, OCR, вернуть распарсенный dict.
    Игра рисует тултип в РАЗНУЮ сторону (влево/вправо И вверх/вниз) в зависимости от места
    слота, чтобы не уехать за экран. Пробуем до 4 боксов (один ховер, несколько кропов):
    {лево,право} × {вниз,вверх} — берём первый, где прочитался грейд. Резко поднимает
    читаемость на правых/нижних слотах. flip — какую горизонталь пробовать ПЕРВОЙ.
    settle — пауза появления тултипа (мал. для быстрого скана, ~0.25; None=из конфига)."""
    hover(slot_xy, settle=settle)
    first = flip or TOOLTIP.get("default_flip", "right")
    other = "left" if first == "right" else "right"
    result, img = None, None
    for fl in (first, other):
        base = _tooltip_box(slot_xy, fl)
        h = base["height"]
        # вниз (как настроено) и вверх (top сдвинут на высоту вверх, нахлёст 24px)
        for top in (base["top"], max(0, base["top"] - h + 24)):
            box = dict(base, top=top)
            r, im = _ocr_box_at(sct, box)
            if result is None:
                result, img = r, im       # запомним первый как дефолт (хотя бы имя/уровень)
            if r.get("rank"):
                result, img = r, im
                break
        if result and result.get("rank"):
            break
    nm = _read_name(img)
    if nm:
        result["name"] = nm
    # обогащение из АВТОРИТЕТНОЙ БД: тип/слот/бижутерия по имени (надёжнее OCR-эвристик).
    # Имя→тип в БД консистентно (0 конфликтов), поэтому это безопасно для решения о локе.
    rec = classify(result.get("name"))
    if rec:
        result["type"] = rec["type"]              # gear / accessory / material / box
        result["accessory"] = rec["accessory"]
        result["part_ru"] = rec.get("part_ru") or None
        result["geartype"] = rec.get("geartype") or None
        result["db_name"] = rec["name"]           # каноничное имя из игры
        result["db_grades_ru"] = rec.get("grades_ru")
        if result.get("level_req") is None and rec.get("min_level") == rec.get("max_level"):
            result["level_req"] = rec.get("min_level")
    elif result.get("type") is None and result.get("name") \
            and any(a in result["name"].lower() for a in ACCESSORY_WORDS):
        result["type"] = "accessory"              # запасная эвристика, если имя не нашли
        result["accessory"] = True
    return result


def _rank_in(txt):
    """Найти слово-ранг (ru или en) в тексте -> (рус-канон слово, tier) или (None, -1)."""
    low = (txt or "").lower()
    best_pos, tier = len(low) + 1, -1
    for words in (RANK_TIERS, RANK_TIERS_EN):
        for i, t in enumerate(words):
            p = low.find(t)
            if p != -1 and p < best_pos:
                best_pos, tier = p, i
    return (RANK_TIERS[tier], tier) if tier >= 0 else (None, -1)


def read_grade(sct, slot_xy, flip=None, settle=None):
    """Ридер грейда для скана: наводим, OCR'им ПОЛНЫЙ бокс тултипа (как дроп-фид read_item,
    который читает надёжно) и ищем слово-ранг. Имя НЕ читаем (быстрее read_item). Кропы
    {flip}×{вниз,вверх} с early-exit. Вернуть rank-слово или None.

    Почему полный бокс, а не узкая полоска: вёрстка/масштаб тултипа варьируются, строка
    «Ранг» уезжала за пределы узкой полоски → весь скан читался «неизв». Полный бокс надёжен."""
    hover(slot_xy, settle=settle)
    first = flip or TOOLTIP.get("default_flip", "right")
    other = "left" if first == "right" else "right"
    for fl in (first, other):
        base = _tooltip_box(slot_xy, fl)
        for top in (base["top"], max(0, base["top"] - base["height"] + 24)):
            box = dict(base, top=top)
            img = np.array(sct.grab(box))[:, :, :3]
            txt = pytesseract.image_to_string(_preprocess(img), lang=OCR_LANG)
            word, _ = _rank_in(txt)
            if word:
                return word
    return None


def parse_tooltip(txt):
    """Чистый парсер OCR-текста тултипа.
    Возвращает dict с полями: name, rank, rank_tier, type, level_req, tradeable, class_lock, raw."""
    raw = txt
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    lower = txt.lower()

    # имя = строка прямо НАД строкой "Ранг X" (заголовок тултипа); если ранг на
    # строке 0 (имя не попало в OCR) -> None, честнее чем выдать "Ранг ..." за имя
    rank_line = None
    for idx, ln in enumerate(lines):
        lnl = ln.lower()
        if any(t in lnl for t in RANK_TIERS) or any(t in lnl for t in RANK_TIERS_EN):
            rank_line = idx
            break
    if rank_line is not None and rank_line > 0:
        name = lines[rank_line - 1]
    elif lines:
        name = lines[0]
    else:
        name = None
    if name and ("ранг" in name.lower() or "grade" in name.lower()):
        name = None

    # ранг: двуязычный поиск (ru/en) -> рус-канон слово
    rank, rank_tier = _rank_in(txt)

    # тип: accessory по ключевому слову, иначе lookup в db, иначе None
    type_ = None
    for aw in ACCESSORY_WORDS:
        if aw in lower:
            type_ = "accessory"
            break
    if type_ is None and name:
        db = db_lookup(name)
        if db:
            t = db.get("type")
            if t in ("gear", "accessory", "material"):
                type_ = t

    # требование уровня
    level_req = None
    m = re.search(r"ур\.?\s*(\d+)|уровень\s*(\d+)", raw, re.IGNORECASE)
    if m:
        level_req = int(m.group(1) if m.group(1) is not None else m.group(2))

    # торгуемость
    tradeable = None
    if "неторгуем" in lower:
        tradeable = False

    # класс-лок — пока не реализуем надёжно, оставляем None
    class_lock = None

    return {
        "name": name,
        "rank": rank,
        "rank_tier": rank_tier,
        "type": type_,
        "accessory": type_ == "accessory",
        "part_ru": None,
        "geartype": None,
        "level_req": level_req,
        "tradeable": tradeable,
        "class_lock": class_lock,
        "raw": raw,
    }
