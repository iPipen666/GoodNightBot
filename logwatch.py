"""logwatch.py — чтение игрового лога RECORDS через OCR → структурные события.

Надёжнее пиксельного матча спрайтов: игра САМА пишет в панель RECORDS строки вида
  'Obtained Common Treasure Chest. (...)'   — получен сундук (грейд)
  'Obtained Vengeance Sword.'               — получен предмет
  'Cleared Stage 2-9. (409s)'               — пройдена стадия (время)
  'Failed to clear Stage 3-9. (2/28)'       — провал стадии
  'Knight has been defeated. (...)'         — герой пал
  'Knight has revived.'                     — герой воскрес
каждая строка с тегом времени [mm:ss] от старта игровой сессии.

OCR делается по окну игры (RECORDS должен быть открыт и поверх). Парсер — построчно,
устойчив к шуму (соседние окна/символы отсекаются регэкспами). LogWatcher накапливает
УНИКАЛЬНЫЕ события (ключ = тег времени + тип + значение), чтобы считать за сессию без
двойного счёта, пока панель скроллится.
"""
import re
import threading

import numpy as np
import mss
import pygetwindow as gw
from PIL import Image

import items  # noqa: F401 — сайд-эффект: настраивает pytesseract.tesseract_cmd
import pytesseract
import log_templates  # матчеры лог-событий из словаря игры (16 языков)

# ── регэкспы событий (строгие — режут OCR-шум) ──
_TS = re.compile(r"\[?(\d{1,2}[:.]\d{2})\]?")           # [00:18] / 00:18
# ── английские паттерны (язык игры EN) ──
_CHEST = re.compile(r"Obtained\s+([A-Za-z]+)\s+Treasure\s+Chest", re.I)
_ITEM = re.compile(r"Obtained\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\s*\.", re.I)
_STAGE_OK = re.compile(r"Cleared\s+Stage\s+(\d+-\d+)\.?\s*\(?\s*(\d+)\s*s", re.I)
_STAGE_FAIL = re.compile(r"Fail(?:ed)?\s+to\s+clear\s+Stage\s+(\d+-\d+)", re.I)
_DEFEAT = re.compile(r"([A-Z][a-z]+)\s+has\s+been\s+defeat", re.I)
_REVIVE = re.compile(r"([A-Z][a-z]+)\s+has\s+revived", re.I)
# ── русские паттерны (язык игры RU): 'Получено … сундук' / 'Получено <Предмет>.' /
#    'Этап 2-9 пройдено. (378с)' / 'Не удалось пройти Этап 3-9.' / '<Герой> повержен/воскрес' ──
_CHEST_RU = re.compile(r"Получ\w*\s+(\w+)\s+сундук", re.I | re.U)
_ITEM_RU = re.compile(r"Получ\w*\s+([А-ЯЁ][\w'\- ]+?)\s*\.", re.U)
_STAGE_OK_RU = re.compile(r"Этап\s+(\d+-\d+)\s+пройден\w*.*?\(\s*(\d+)\s*[сcs]", re.I | re.U)
_STAGE_FAIL_RU = re.compile(r"Не\s+удалось\s+пройти\s+Этап\s+(\d+-\d+)", re.I | re.U)
_DEFEAT_RU = re.compile(r"(\w+)\s+поверж\w*", re.I | re.U)
_REVIVE_RU = re.compile(r"(\w+)\s+воскрес", re.I | re.U)
# Моб-источник в скобках: '(Fire Elemental)' / '(Ядовитое насекомое)'. Должен НАЧИНАТЬСЯ с буквы
# (лат/кир) — так отсекаются служебные '(409с)' (время стадии) и '(2/28)' (счётчик провала).
_MOB = re.compile(r"\(\s*([A-Za-zА-ЯЁа-яё][\w '\-]{1,38}?)\s*\)", re.U)


def _mob_of(s):
    """Текстовый источник дропа из скобок (моб) или '' если только число/время."""
    m = _MOB.search(s or "")
    return m.group(1).strip() if m else ""

# нормализованные грейды сундуков (OCR может дать регистр/опечатку)
_GRADES = ("common", "uncommon", "rare", "legendary", "immortal", "arcana",
           "transcendent", "celestial", "divine", "cosmic")


_NOT_GAME = ("discord", "chrome", "visual studio", "code", "telegram", "obs", " - ", "@")


def find_game_window():
    """Окно игры (Unity-заголовок ровно 'TaskBarHero'). Исключаем Discord/Chrome/VSCode и т.п.,
    которые тоже содержат 'Task Bar Hero' в заголовке. None если не найдено."""
    cands = []
    for w in gw.getAllWindows():
        t = (w.title or "")
        tl = t.lower()
        if w.width < 300 or w.height < 300:
            continue
        if any(m in tl for m in _NOT_GAME):
            continue
        ts = tl.replace(" ", "")
        if "taskbarhero" in ts:
            cands.append(w)
    if not cands:
        return None
    exact = [w for w in cands if w.title.lower().replace(" ", "") == "taskbarhero"]
    pool = exact or cands
    return max(pool, key=lambda x: x.width * x.height)


def grab(win):
    """BGR→RGB numpy кадр окна игры (через mss по экранным координатам)."""
    with mss.mss() as sct:
        raw = np.array(sct.grab({"left": int(win.left), "top": int(win.top),
                                 "width": int(win.width), "height": int(win.height)}))
    return raw[:, :, :3][:, :, ::-1]            # BGRA → RGB


def ocr(frame, scale=1.4):
    """OCR кадра (апскейл для чёткости пиксель-шрифта). lang=rus+eng — игра может быть на любом
    из языков (лог: EN 'Obtained…' / RU 'Получено…'); оба читаются одной моделью."""
    im = Image.fromarray(frame)
    if scale and scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)))
    return pytesseract.image_to_string(im, lang="rus+eng", config="--psm 6")


def _chest_kind(word):
    """Тип сундука по слову-грейду перед 'Treasure Chest'/'сундук':
    EN 'Stage…'->stage_boss, 'Act…'->act_boss; RU 'этап…'->stage_boss, 'акт…'->act_boss;
    рарность (Common/Обычный/…) -> normal (монстр-боксы)."""
    w = (word or "").lower()
    if w.startswith("stage") or "этап" in w:
        return "stage_boss"
    if w.startswith("act") or "акт" in w:
        return "act_boss"
    return "normal"


def _norm_grade(g):
    g = (g or "").lower()
    if g in _GRADES:
        return g
    # ближайший по префиксу (OCR-опечатки)
    for k in _GRADES:
        if g[:4] and k.startswith(g[:4]):
            return k
    return "common"


def _int(x):
    m = re.search(r"\d+", x or "")
    return int(m.group(0)) if m else 0


def _stage_num(name):
    """Из имени этапа ('Этап 3-4' / 'Stage 3-4') достать '3-4'."""
    m = re.search(r"\d+-\d+", name or "")
    return m.group(0) if m else (name or "").strip()


_TRAIL_TS = re.compile(r"\s*\[?\s*\d{1,2}\s*[:.]\s*\d{2}\s*\]?[^\wА-Яа-яЁё]*$")


def _classify(s, tk):
    """ОДНА строка → event-dict или None. Через матчеры словаря игры (log_templates, 16 языков).
    getbox/obtained ('Получено {0}') разводятся: имя=сундук → chest, иначе → item. Обрезанный
    сундук без точки ловит фолбэк detect_chest. Хвостовой таймстемп срезаем (иначе greedy-поле
    финального плейсхолдера схватит '[11:16]')."""
    s = _TRAIL_TS.sub("", s).rstrip()
    for etype, rx, lang in log_templates.matchers():
        m = rx.search(s)
        if not m:
            continue
        g = m.groupdict()
        f0 = (g.get("f0") or "").strip()
        f1 = (g.get("f1") or "").strip()
        if etype in ("getbox", "obtained"):
            if log_templates.is_chest_name(f0, lang):
                kind = log_templates.chest_kind_for(f0, lang)
                key = f"{tk}|chest|{kind}" if tk else f"nots|chest|{kind}|{s}"
                mob = f1 if (etype == "getbox" and f1) else _mob_of(s)
                return {"type": "chest", "kind": kind, "word": f0, "k": key, "ts": tk, "mob": mob}
            # ОБРЕЗАННЫЙ сундук: с end-anchor матчер obtained теперь ловит «Получено Обычный сундук
            # с сокрови…» (ядро имени неполное → is_chest_name=False). detect_chest по значимому слову
            # (≥6 букв) ловит обрезку ДО того, как примем строку за обычный предмет.
            kind, _kl = log_templates.detect_chest(s)
            if kind:
                key = f"{tk}|chest|{kind}" if tk else f"nots|chest|{kind}|{s}"
                return {"type": "chest", "kind": kind, "word": kind, "k": key,
                        "ts": tk, "mob": _mob_of(s)}
            if etype == "getbox":
                continue                 # 'Получено X (Y)' без сундука — пусть obtained поймает имя
            return {"type": "item", "name": f0, "ts": tk, "mob": _mob_of(s),
                    "k": f"{tk}|item|{f0}"}
        if etype == "stage_clear":
            st = _stage_num(f0)
            return {"type": "stage_clear", "stage": st, "sec": _int(f1), "k": f"{tk}|stage|{st}|{f1}"}
        if etype == "stage_fail":
            st = _stage_num(f0)
            return {"type": "stage_fail", "stage": st, "k": f"{tk}|fail|{st}"}
        if etype == "defeat":
            return {"type": "defeat", "hero": f0, "mob": f1, "k": f"{tk}|defeat|{f0}|{s[:18]}"}
        if etype == "revive":
            return {"type": "revive", "hero": f0, "k": f"{tk}|revive|{f0}|{s[:18]}"}
        if etype == "levelup":
            return {"type": "levelup", "hero": f0, "level": _int(f1), "k": f"{tk}|lvl|{f0}|{f1}"}
        if etype == "synthesis":
            return {"type": "synthesis", "spent": f0, "got": f1, "k": f"{tk}|syn|{f0}|{f1}|{s[:12]}"}
        if etype == "craft":
            return {"type": "craft", "name": f0, "k": f"{tk}|craft|{f0}|{s[:12]}"}
        if etype == "alchemy":
            return {"type": "alchemy", "spent": f0, "got": f1, "k": f"{tk}|alch|{s[:20]}"}
    # фолбэк: обрезанная строка сундука (без точки/моба) — по ядру имени
    kind, _lang = log_templates.detect_chest(s)
    if kind:
        key = f"{tk}|chest|{kind}" if tk else f"nots|chest|{kind}|{s}"
        return {"type": "chest", "kind": kind, "word": kind, "k": key, "ts": tk, "mob": _mob_of(s)}
    return None


def chest_kind_by_color(arr, box):
    """Тип сундука по ЦВЕТУ ТЕКСТА строки (надёжнее обрезаемого маркизой текста — юзер подтвердил
    палитру): СЕРЫЙ/белый=normal, СИНИЙ=stage_boss(этапа), КРАСНЫЙ=act_boss(акта).
    🔴 ПРОБЛЕМА ПРОЗРАЧНОГО ОВЕРЛЕЯ: пилюля полупрозрачна → СИНИЙ ФОН (страница SHANN) просвечивает
    как СРЕДНЕ-ЯРКИЙ синий тинт (~lum 137) и красит обычный сундук в ложно-синий. Замер живьём:
    реальный текст-штрих ЯРКИЙ (lum>180), а тинт-просвет средний. Решение ДВУХ-ПОЛОСНОЕ:
    • ЯДРО текста (lum>180, исключает тинт) → серый=normal / синий=stage_boss (надёжно);
    • КРАСНЫЙ (act) текст тусклее (lum~139, в полосе тинта) — но красного просвета нет → ловим
      красную доминанту в средней полосе.
    Возврат 'normal'/'stage_boss'/'act_boss' ИЛИ None (неуверенно → вызывающий оставит текст-класс.)."""
    try:
        x0, y0, x1, y1 = box
        sub = arr[max(0, y0):y1 + 1, max(0, x0):x1 + 1].reshape(-1, 3)
        if sub.size == 0:
            return None
        lum = sub.mean(axis=1)
        core = sub[lum > 180]                      # ЯДРО текста — без полупрозрачного тинта-просвета
        if len(core) >= 20:
            R, G, B = float(core[:, 0].mean()), float(core[:, 1].mean()), float(core[:, 2].mean())
            if B - R > 20 and B - G > 8:           # яркий синий → этапа (норм=15, boss=29..64 живьём)
                return "stage_boss"
            if R - B > 20 and R - G > 15:          # яркий красный → акта
                return "act_boss"
            if abs(R - G) < 20 and abs(G - B) < 20 and abs(R - B) < 20:
                # ядро СЕРОЕ → обычный. Но красный act-текст тусклее ядра → проверим среднюю полосу.
                mid = sub[(lum > 110) & (lum <= 180)]
                if len(mid) >= 40:
                    mR, mG, mB = float(mid[:, 0].mean()), float(mid[:, 1].mean()), float(mid[:, 2].mean())
                    if mR - mB > 30 and mR - mG > 25:    # красная доминанта в средней полосе → акта
                        return "act_boss"
                return "normal"
            return None                             # ядро не серое/не сине/красное — неясно
        # мало яркого ядра: текст тусклый (возможно красный act). Решаем по доминанте средних.
        mid = sub[lum > 110]
        if len(mid) >= 20:
            R, G, B = float(mid[:, 0].mean()), float(mid[:, 1].mean()), float(mid[:, 2].mean())
            if R - B > 30 and R - G > 25:          # уверенно красный → акта
                return "act_boss"
            # синий в средней полосе = тинт-просвет, НЕ доверяем (вернём None → текст-класс.)
        return None
    except Exception:
        return None


def parse(txt):
    """OCR-текст → события. Через шаблоны игры (log_templates) — точно, 16 языков."""
    events = []
    for ln in (txt or "").splitlines():
        s = ln.strip()
        if len(s) < 6:
            continue
        ts = _TS.search(s)
        ev = _classify(s, ts.group(1) if ts else "")
        if ev:
            events.append(ev)
    return events


def is_game_foreground():
    """Игра — активное (foreground) окно? Если нет — OCR грабит чужие окна (VSCode/Claude),
    и в лог-парсер лезет мусор → ложные/дублирующие события. Поллер должен это пропускать."""
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        return buf.value.lower().replace(" ", "") == "taskbarhero"
    except Exception:
        return False


def records_signal(txt=None):
    """Сколько событийных строк лога видно СЕЙЧАС (индикатор готовности: RECORDS открыт + галки вкл).
    0 → панель закрыта / события не пишутся / игра не поверх. Используется на старте сессии."""
    if txt is None:
        win = find_game_window()
        if not win:
            return 0
        try:
            txt = ocr(grab(win))
        except Exception:
            return 0
    return len(parse(txt))


_CODEISH = re.compile(r"\.\s*(py|js|json|bat|log|md|exe|spec|txt|ini|cfg|png|jpe?g|html?|csv|ya?ml)\b", re.I)


_LOG_TS = re.compile(r"[\(\[]\s*\d{1,2}\s*[:.]\s*\d{2}\s*[\)\]]"     # (09:53)/[09:38] — таймстамп строки
                     r"|\(\s*\d{1,3}\s*/\s*\d{1,3}\s*\)")           # (9/31) — прогресс волны (stage_fail/clear)


def _is_log_line(s):
    """Строка — событие лога (любой из 16 языков)? Фильтр отсекает не-логовый OCR-шум (стол/HUD/
    инвентарь/Telegram/просвет рабочего стола) ДО сдвиг-алайнмента. Через те же матчеры словаря, что parse.
    ДОП-ГАРД: имена файлов/код (chest_stock.py, config.json) — игра ПРОЗРАЧНА, за ней просвечивает
    VSCode/просвет → их текст ловился как «событие». Строки с расширением файла отсекаем.
    OCR-ФОЛБЭК: строгий матч шаблона ломается от OCR-шума (напр. «Не»→«Че» в «Не удалось пройти Этап»);
    но у КАЖДОЙ строки лога есть таймстамп в скобках (цифры OCR читает надёжно) → устойчивый признак
    строки лога для детекта/счёта (классификация СОБЫТИЙ в parse() остаётся строгой)."""
    if _CODEISH.search(s or ""):
        return False
    if _classify(s, "") is not None:
        return True
    return bool(_LOG_TS.search(s or ""))


def _norm(line):
    """Нормализация строки для сравнения снимков: lower, только буквы/цифры/двоеточие, схлоп пробелов."""
    s = re.sub(r"[^a-z0-9:]+", " ", (line or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _ts_token(line):
    m = _TS.search(line or "")
    return m.group(1) if m else ""


def _ts_secs(ts):
    """Таймстамп 'mm:ss' → целое секунд (для сравнения свежести). None если не распознан."""
    if not ts:
        return None
    m = re.match(r"(\d{1,2})[:.](\d{2})", ts)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _line_match(a, b):
    """Две OCR-строки — одна и та же логическая строка лога? Таймстамп + «головной» префикс ВМЕСТЕ
    (раньше — только таймстамп: 2-3 РАЗНЫХ события в одну секунду считались одной строкой → ломало
    выравнивание сдвига при пачке дропов). Хвост '(Моб)' бежит маркизой, OCR'ится по-разному — в
    сравнение его НЕ берём (первые ≤5 токенов). Таймстамп, если есть у обеих, ДОЛЖЕН совпасть."""
    ta, tb = _ts_token(a), _ts_token(b)
    if ta and tb and ta != tb:
        return False                              # разные секунды — точно разные строки
    an, bn = _norm(a).split(), _norm(b).split()
    if not an or not bn:
        return bool(ta and tb and ta == tb)       # текста нет, но секунды совпали — считаем совпадением
    k = min(5, len(an), len(bn))
    return an[:k] == bn[:k]                        # головной префикс совпал (тип+грейд события)


def _align(prev, cur):
    """Найти НАИБОЛЬШЕЕ перекрытие O: последние O строк prev совпадают с первыми O строк cur.
    Тогда новые события = cur[O:] (нижние строки), сдвиг = len(cur)-O. 0 → перекрытия нет.

    ПОРОГ совпадения зависит от O: для МАЛЫХ перекрытий (O≤2) требуем ПОЛНОЕ совпадение — иначе
    overshoot: при пачке одинаковых строк (prev кончается тем же сундуком, что в пачке) частичное
    50%-совпадение принимало O=2 и съедало новые строки → недосчёт бёрста (баг ревью 2026-06-10).
    Для O≥3 хватает 70% (контекста больше, off-by-one от OCR-шума не страшен)."""
    m, n = len(prev), len(cur)
    for O in range(min(m, n), 0, -1):
        pa, cb = prev[m - O:], cur[:O]
        match = sum(1 for i in range(O) if _line_match(pa[i], cb[i]))
        need = O if O <= 2 else int(round(0.7 * O))   # малое перекрытие → строго полное совпадение
        if match >= need:
            return O
    return 0


def _ev_key(e):
    """Стабильная сигнатура события — переживает OCR-шум в тексте (для дедупа висящей пилюли).
    Сундук по типу (одинаковые подряд на 1-строке неразличимы — это предел пилюли)."""
    t = e.get("type")
    if t == "chest":
        return "chest|" + str(e.get("kind"))
    if t == "item":
        return "item|" + _norm(e.get("name", ""))[:18]
    if t == "stage_clear":
        return "stage|" + str(e.get("stage"))
    if t == "stage_fail":
        return "fail|" + str(e.get("stage"))
    if t == "defeat":
        return "defeat|" + str(e.get("hero")) + "|" + str(e.get("mob"))
    if t == "revive":
        return "revive|" + str(e.get("hero"))
    if t == "levelup":
        return "lvl|" + str(e.get("hero")) + "|" + str(e.get("level"))
    return e.get("k", repr(e))


class LogWatcher:
    """Накопитель событий лога за сессию. Счёт — по СДВИГУ строк (observe): считаем ТОЛЬКО события,
    появившиеся ПОСЛЕ базлайна (первого снимка), историю до старта сессии не считаем. Это
    ограничивает счёт реальным скроллом → не раздувается от OCR-шума (как было с дедупом)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._lock = threading.Lock()     # observe зовётся из ФОНОВОГО потока-наблюдателя; drain — из main
        self._seen = set()
        self._prev_lines = None           # прошлый снимок строк лога (для сдвиг-алайнмента); None = базлайна ещё не было
        self._hw_secs = None              # ВОДЯНОЙ ЗНАК времени: макс. секунда виденного события (для восстановления при потере синхры)
        self._hw_count = 0                # сколько событий на этой секунде уже учтено (tie-handling одной секунды)
        self._showing = None              # КЛЮЧИ событий, видимых СЕЙЧАС (для 1-строчной пилюли: считаем событие
                                          # ТОЛЬКО когда ключ ВПЕРВЫЕ появился; висящую пилюлю НЕ пересчитываем → нет перещёта)
        self._rec = {}                    # k -> запись события (обогащается мобом по мере прокрутки маркизы)
        self.new_intel = []               # дропы, у которых ПОЯВИЛСЯ моб-источник (для сохранения интела)
        self.chests = {}                  # grade -> count
        self.chests_total = 0
        self.items = []                   # последние полученные предметы
        self.new_items = []               # НОВЫЕ дропы с прошлого drain (для лог-прелока)
        self.stage = None                 # последняя пройденная стадия "2-9"
        self.stage_fail = None
        self.stages_cleared = 0           # СЧЁТЧИК успешно пройденных этапов за сессию (лог-driven)
        self.stages_failed = 0            # СЧЁТЧИК проваленных этапов за сессию
        self.defeats = 0
        self.revives = 0

    def _apply(self, e):
        """Применить ОДНО новое событие к счётчикам/буферам (инкремент)."""
        t = e["type"]
        if t == "chest":
            self.chests[e["kind"]] = self.chests.get(e["kind"], 0) + 1       # normal/stage_boss/act_boss
            self.chests_total += 1
        elif t == "item":
            self.items.append(e["name"])
            self.items = self.items[-50:]
            self.new_items.append(e["name"])          # копим для лог-прелока (drain отдаёт и чистит)
            self.new_items = self.new_items[-50:]
        elif t == "stage_clear":
            self.stage = e["stage"]
            self.stages_cleared += 1
        elif t == "stage_fail":
            self.stage_fail = e["stage"]
            self.stages_failed += 1
        elif t == "defeat":
            self.defeats += 1
        elif t == "revive":
            self.revives += 1

    def _enrich(self, lines):
        """Обогащение мобом по всему снимку БЕЗ подсчёта: хвост '(Моб)' бежит маркизой и доезжает
        позже — дочитываем источник дропа и копим интел (имя+моб+время). Считать события НЕЛЬЗЯ
        (иначе посчитаем историю) — счёт только в observe по сдвигу."""
        for e in parse("\n".join(lines)):
            if e["type"] not in ("chest", "item"):
                continue
            r = self._rec.get(e["k"])
            if r is None:
                r = {"type": e["type"], "ts": e.get("ts", ""), "mob": "",
                     "name": e.get("name") or e.get("word", ""), "kind": e.get("kind")}
                self._rec[e["k"]] = r
            if e.get("mob") and not r["mob"]:
                r["mob"] = e["mob"]
                if e["type"] == "item":               # имя+моб+время собраны → на сохранение интела
                    self.new_intel.append(dict(r))
                    self.new_intel = self.new_intel[-50:]
        if len(self._rec) > 1000:
            self._rec = dict(list(self._rec.items())[-500:])

    def observe(self, lines):
        """СНИМОК строк лога (top→bottom, новейшее снизу). Считает события по СДВИГУ относительно
        прошлого снимка: новые строки внизу = новые события. Первый снимок = БАЗЛАЙН (история, 0).
        Возвращает список новых event-dict. Замена дедупа: счёт ограничен реальным скроллом."""
        with self._lock:
            return self._observe_locked(lines)

    def _observe_locked(self, lines):
        cur = [l for l in (lines or []) if len((l or "").strip()) >= 6 and _is_log_line(l)]
        prev = self._prev_lines
        if not prev:                                  # базлайн (None ИЛИ пустой прошлый снимок: лог был не
            if cur:                                   # виден → первый РЕАЛЬНЫЙ снимок = базлайн, не история).
                self._prev_lines = cur
                self._enrich(cur)
                self._update_watermark(cur)           # знак времени с базлайна → восстановление сможет сравнивать
            return []
        if not cur:                                   # лог закрыт/не виден — держим прошлый базлайн, ждём
            return []
        O = _align(prev, cur)
        self._prev_lines = cur
        if O == 0:                                    # НЕТ ПЕРЕКРЫТИЯ: 1-строчная пилюля СМЕНИЛА строку ИЛИ
            # большой скролл. Считаем событие, чей КЛЮЧ (_ev_key — переживает OCR-шум головы) НЕ был в ПРОШЛОМ
            # снимке. ⛔ ПЕРЕЩЁТ (баг 135): висящая пилюля при вариации OCR выглядела «новой строкой» и
            # пересчитывалась → теперь по ключу события она = та же → НЕ считаем. Реальная смена пилюли /
            # пачка РАЗНЫХ строк → ключей не было в prev → считаются. И сундук БЕЗ ts ловится (ключ chest|kind).
            prev_keys = {_ev_key(e) for e in parse("\n".join(prev))}
            new = []
            for e in parse("\n".join(cur)):
                if _ev_key(e) not in prev_keys:
                    self._seen.add(e["k"])
                    self._apply(e)
                    new.append(e)
            self._enrich(cur)
            self._update_watermark(cur)
            return new
        # СЧЁТ ПО СДВИГУ: новые строки = cur[O:] (ниже перекрытия). Считаем ИХ ВСЕ, включая
        # ОДИНАКОВЫЕ (3 одинаковых сундука в одну секунду = 3 события). Контент-дедуп `_seen` УБРАН
        # из счёта — он схлопывал идентичные ключи и недосчитывал пачки (баг бёрст-дропа).
        # Boundary-гард УБРАН: он ронял cur[O:][0] при совпадении с prev[-1], но это ЛОЖНО резало
        # легитимный новый ОДИНАКОВЫЙ сундук (pred=...C, new=C,C,C). Корректность перекрытия теперь
        # обеспечивает строгий _align (полное совпадение для O≤2) — boundary-band-aid больше не нужен.
        new_lines = cur[O:]
        new = []
        for e in parse("\n".join(new_lines)):
            self._seen.add(e["k"])                    # держим для совместимости/диагностики (не гейтим счёт)
            self._apply(e)
            new.append(e)
        if len(self._seen) > 4000:
            self._seen = set(list(self._seen)[-2000:])
        self._enrich(cur)                             # хвосты-мобы по всему окну
        self._update_watermark(cur)                   # обновить водяной знак времени = свежайшее виденное
        return new

    def _events_with_ts(self, cur):
        """События текущего снимка, у которых распознан таймстамп (с секундами), в визуальном порядке
        (сверху-вниз = старое→новое)."""
        out = []
        for e in parse("\n".join(cur)):
            s = _ts_secs(e.get("ts"))
            if s is not None:
                out.append((s, e))
        return out

    def _update_watermark(self, cur):
        """Запомнить свежайшее виденное время (макс. секунда) и сколько событий на ней — чтобы при
        следующей потере синхры считать только то, что НОВЕЕ этого."""
        evs = self._events_with_ts(cur)
        if not evs:
            return
        mx = max(s for s, _ in evs)
        self._hw_secs = mx
        self._hw_count = sum(1 for s, _ in evs if s == mx)

    def _recover_by_ts(self, cur):
        """Восстановление счёта при O==0: посчитать события СВЕЖЕЕ водяного знака времени. На равной
        секунде — только сверх уже учтённого `_hw_count`. Гарды: нет якоря/времени → 0 (просто базлайн);
        текущий максимум < знака (сброс/обёртка часов) → 0 (не считаем историю)."""
        evs = self._events_with_ts(cur)
        if not evs or self._hw_secs is None:
            return []
        cur_max = max(s for s, _ in evs)
        if cur_max < self._hw_secs:                   # время «откатилось» (ре-старт игры/обёртка) → не считаем
            return []
        new = []
        at_hw = 0
        for s, e in evs:                              # старое→новое
            if s > self._hw_secs:
                new.append(e)
            elif s == self._hw_secs:
                at_hw += 1
                if at_hw > self._hw_count:            # новые события на той же секунде, сверх учтённых
                    new.append(e)
        for e in new:
            self._seen.add(e["k"])
            self._apply(e)
        return new

    def ingest_text(self, txt):
        """Совместимость: текст → строки → observe (сдвиг-счёт). Возвращает число новых событий."""
        return len(self.observe((txt or "").splitlines()))

    def drain_new_items(self):
        """Отдать НОВЫЕ имена дропов с прошлого вызова и очистить буфер (для лог-прелока)."""
        with self._lock:
            out = self.new_items
            self.new_items = []
            return out

    def drain_new_intel(self):
        """Отдать дропы, у которых дочитался моб-источник (имя+моб+время), и очистить буфер.
        Для сохранения лут-интела: что с какого моба и когда выпало."""
        with self._lock:
            out = self.new_intel
            self.new_intel = []
            return out

    def poll(self):
        """Грабнуть окно игры, OCR, скормить. Вернуть число новых событий (0 если окна нет)."""
        return len(self.poll_events())

    def poll_events(self):
        """Прогнать видимые строки лога через observe. Вернуть список НОВЫХ событий.
        Читаем ПРИЦЕЛЬНО через find_log (psm6 по строкам-пилюлям) — полнокадровый ocr(grab) мелкую
        плашку «Obtained Chest» на сцене НЕ дочитывал → бот не считал сундуки (подтверждено живьём:
        standalone find_log+observe считал, бот на ocr(grab) — нет)."""
        try:
            import log_setup
            r = log_setup.find_log()
            if r.get("n") == -1:                  # игра не поверх — не трогаем состояние
                return []
            rows = [t for t, _b in r.get("rows", [])]
            return self.observe(rows)
        except Exception:
            return []


if __name__ == "__main__":
    import sys
    lw = LogWatcher()
    if len(sys.argv) > 1:                 # OCR сохранённого PNG (оффлайн-тест парсера)
        lw.ingest_text(ocr(np.array(Image.open(sys.argv[1]).convert("RGB"))))
    else:
        lw.poll()
    print("chests:", lw.chests, "total:", lw.chests_total)
    print("stage:", lw.stage, "| items:", lw.items[-6:])
    print("defeats:", lw.defeats, "revives:", lw.revives)
