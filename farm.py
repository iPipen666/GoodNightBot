"""TBH — FARM: динамический автопилот на vision (масштаб/панели определяются КАЖДЫЙ цикл).

Архитектура (north-star): никаких фиксированных долей окна. Каждый цикл:
  vision.detect -> какие панели открыты + масштаб; элементы кликаются ОТНОСИТЕЛЬНО
  баннера (offsets.json, нормировано на ширину баннера). Смена масштаба/макета/позиции
  окна бот переживает и не кликает вслепую.

Цикл:
  1) фокус; detect панелей.
  2) ensure CUBE открыт + режим «Синтез» (форсим mode->Синтез).
  3) ensure STASH открыт.
  4) save-all (очистить инвентарь -> в стэш) + сортировка стэша. (фикс: инвентарь не переполняется)
  5) МЕРЖ по типам РАЗДЕЛЬНО (Снаряжение/Материалы/Аксессуар — бижу не пересекается со шмотом):
       тип -> autofill -> считаем 9/9 -> confirm -> ВОЗВРАТ (return_btn) -> результат в инвентарь.
     <9 -> return, к следующему типу. Гейт 9/9.
  6) save-all (результаты мержа -> в стэш).
  7) сундуки: Space (сворачивает панели — ок, следующий цикл откроет заново).

Запуск: farm.py --once | --live | --dry   (стоп F12)
"""
import json
import os
import sys
import time
import random
import ctypes
from ctypes import wintypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import numpy as np
import cv2
import mss
import pygetwindow as gw
import human
import vision
import idle
import inv_probe as ip  # analyze() — классификация грейда по цвету плитки
import logx              # log_debug — диагностика в farm.debug.log (no-op без --debug)

# Детектор сундуков (boxes.py — спрайт-матч) — ЛЕГАСИ/фолбэк; ненадёжен (иконки вики != игровым).
# Основной счёт сундуков теперь из ИГРОВОГО ЛОГА RECORDS через logwatch (OCR событий — проверено
# живьём: 'Obtained Common Treasure Chest' и т.п.). Оба опциональны; ошибка импорта = None, пропуск.
try:
    import boxes as _boxes_mod
except Exception:
    _boxes_mod = None
try:
    import logwatch as _logwatch
    _LOG = _logwatch.LogWatcher()
except Exception:
    _logwatch = None
    _LOG = None

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
OFF = json.load(open(os.path.join(HERE, "offsets.json"), encoding="utf-8"))
_SYNTH_ICON = cv2.imread(os.path.join(HERE, "templates", "cube", "synthesis_icon.png"))
_POPUP_DIR = os.path.join(HERE, "templates", "popup")
_CONFIRM_ICONS = [im for im in
                  (cv2.imread(os.path.join(_POPUP_DIR, f))
                   for f in (sorted(os.listdir(_POPUP_DIR)) if os.path.isdir(_POPUP_DIR) else [])
                   if f.lower().endswith(".png"))
                  if im is not None]  # все варианты кнопки Confirm попапа валидации
INV = CFG["inventory"]
KKEY = CFG.get("kill_key", "f12")
DRY = "--dry" in sys.argv
SHOTS = "--shots" in sys.argv         # debug-скрины в crops/farm/
NOMERGE = "--nomerge" in sys.argv     # тест навигации: НЕ жать confirm (только autofill/return)
POLITE = "--rude" not in sys.argv     # вежливый режим (по умолч.): работать только когда юзер idle
IDLE_START = CFG.get("idle_start_seconds", 90)   # старт цикла только если простой >= стольких сек
CURSOR_TOL = CFG.get("cursor_grab_tol_px", 90)   # курсор уехал дальше -> юзер активен
RESUME_IDLE = CFG.get("resume_idle_seconds", 10) # вежл.: юзер активен -> ждать столько сек ПОКОЯ мыши/клавы, потом продолжить (НЕ обрывать цикл)

_bot_cursor = [None]  # куда бот последний раз поставил курсор (для детекта возврата юзера)
_ceding = [False]     # флаг: сейчас уступаем юзеру (чтобы не спамить лог)

# --- хуки для панели control.py (лог/статус/мягкий стоп) ---
_LOG_CB = None
_STAT_CB = None
_STOP_EVT = None
STATS = {"cycle": 0, "merges": 0, "phase": "—",
         "box_normal": 0, "box_stage": 0, "box_act": 0,
         "loot_valuable": 0, "loot_materials": 0}


def set_hooks(log_cb=None, stat_cb=None, stop_event=None):
    global _LOG_CB, _STAT_CB, _STOP_EVT
    _LOG_CB = log_cb
    _STAT_CB = stat_cb
    _STOP_EVT = stop_event
    human.set_stop_check(_hardstop)   # СТОП мгновенно рвёт human-паузы тоже


def _stat(**kw):
    STATS.update(kw)
    if _STAT_CB:
        try:
            _STAT_CB(dict(STATS))
        except Exception:
            pass


# ── Модалка «попроси юзера» (воркер ↔ панель): главный поток рисует, воркер ждёт Event ──
_MODAL_CB = None
_MODAL_EVT = None


def set_modal_hook(cb):
    """control.py регистрирует cb(text): показать модалку на панели (главный поток Tk)."""
    global _MODAL_CB
    _MODAL_CB = cb


def ask_user_modal(text, timeout=900):
    """Воркер: показать юзеру модалку (через панель) и ждать «Готово». True если подтвердил,
    False если хука нет / таймаут / СТОП. Ждём дробно, чтобы СТОП прерывал."""
    global _MODAL_EVT
    import threading as _th
    if _MODAL_CB is None:
        return False
    if _MODAL_EVT is None:
        _MODAL_EVT = _th.Event()
    _MODAL_EVT.clear()
    try:
        _MODAL_CB(text)
    except Exception:
        return False
    waited = 0.0
    while waited < timeout:
        if _hardstop():
            return False
        if _MODAL_EVT.wait(0.5):
            return True
        waited += 0.5
    return False


def modal_done():
    """Панель: юзер нажал «Готово» → разбудить воркер."""
    if _MODAL_EVT is not None:
        _MODAL_EVT.set()


def user_grabbed():
    """В вежливом режиме: курсор уехал от того места, где его оставил бот -> юзер вернулся."""
    if not POLITE or _bot_cursor[0] is None or DRY:
        return False
    try:
        return idle.dist(idle.cursor_pos(), _bot_cursor[0]) > CURSOR_TOL
    except Exception:
        return False
LOGF = os.path.join(HERE, "farm.log")
SHOTDIR = os.path.join(HERE, "crops", "farm")


def dbg_shot(name):
    if not SHOTS:
        return
    try:
        os.makedirs(SHOTDIR, exist_ok=True)
        w = fw()
        top = max(0, int(w.top))
        import cv2
        with mss.mss() as s:
            img = np.ascontiguousarray(np.array(s.grab({"left": int(w.left), "top": top,
                "width": int(w.width), "height": min(int(w.height), 1440 - top)}))[:, :, :3])
        cv2.imwrite(os.path.join(SHOTDIR, name), img)
        log(f"  [shot] {name}")
    except Exception as e:
        log(f"  [shot err] {e!r}")

CUBE_FILL_THR = CFG.get("cube_fill_threshold", 35.0)  # яркость ячейки куба: занято если выше
MERGE_TYPES = ["type_gear", "type_materials", "type_accessory"]  # раздельно и безопасно
MAX_MERGES_PER_TYPE = int(CFG.get("merge", {}).get("max_per_type", 5))
# ФОРБИД-лист (приоритет): запрещаем мерж ТОЛЬКО уверенно-высоких грейдов — epic(фиолет)/red(красный),
# это всё что классификатор умеет отличить выше Legendary. Любой ДРУГОЙ результат cube_grade —
# включая common/uncommon/rare/legendary И нечитаемый None/unknown — МЕРЖИМ.
# Почему forbid-, а не allow-лист: allow-лист запретил бы None -> непрочитанный белый мусор НЕ
# слился бы -> инвентарь переполняется (ровно прошлая ночная поломка). Autofill набирает низкие
# грейды первыми, поэтому None на практике почти всегда = низкий безопасный грейд.
FORBIDDEN_GRADES = set(CFG.get("forbidden_merge_grades", ["epic", "red"]))
# Грейды, РАЗРЕШЁННЫЕ к мержу — словами рус-тиров (10 тиров из items.RANK_TIERS). Авторитет — OCR.
# Дефолт: 4 низких (безопасно). Галки в настройках пишут сюда. FORBIDDEN_GRADES (рамочный
# первичный фильтр) выводится из этого набора в reload_config().
MERGE_GRADES_RU = set(CFG.get("merge_grades", ["обычный", "необычный", "редкий"]))
# Русские имена типов для понятного лога (без «type_gear»).
TYPE_RU = {"type_gear": "снаряжение", "type_materials": "материалы", "type_accessory": "бижутерия"}
# дроп-фид: OCR имени/уровня/грейда у НОВЫХ предметов (надёжнее рамки, имя из items_db).
_POLICY = CFG.get("policy", {})
OCR_DROPS = _POLICY.get("ocr_drops", True)
OCR_DROPS_MAX = int(_POLICY.get("ocr_drops_max", 6))   # макс. OCR-ховеров за один скан (анти-спам/время)
# быстрый скан: settle тултипа при грейд-скане (НЕ человекоподобно — машинная скорость).
# Маленький => быстро, но тултип Unity должен успеть отрисоваться. 0.25 — баланс.
SCAN_SETTLE = float(CFG.get("tooltip", {}).get("scan_hover_settle", 0.35))
# render-settle для БЫСТРОГО подсчёта занятости (фаза 1): пауза после клика по вкладке, пока
# игра дорисует содержимое. Юзер: картинка появляется ~мгновенно → 0.15с достаточно.
COUNT_SETTLE = float(CFG.get("count_settle", 0.15))
# скролл инвентаря HERO: сколько «рядов» прокручивает один щелчок колеса (0 = не скроллить,
# поведение как раньше). Калибруется живьём; >0 включает многостраничный скан инвентаря.
INV_SCROLL_ROWS = float(CFG.get("inventory", {}).get("scroll_rows_per_notch", 0))
INV_MAX_PAGES = int(CFG.get("inventory", {}).get("max_scroll_pages", 6))


def reload_config():
    """Перечитать config.json в рантайме — применить настройки панели без рестарта."""
    global CFG, FORBIDDEN_GRADES, MERGE_GRADES_RU, INV, SLOT_FILL_THR, CUBE_FILL_THR
    global OCR_DROPS, OCR_DROPS_MAX, RESUME_IDLE, MAX_MERGES_PER_TYPE
    global SCAN_SETTLE, COUNT_SETTLE, INV_SCROLL_ROWS, INV_MAX_PAGES, IDLE_START, CURSOR_TOL, HERO_ROWS, STASH_TABS, OFF
    CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    MERGE_GRADES_RU = set(CFG.get("merge_grades", ["обычный", "необычный", "редкий"]))
    # merge_grades (рус-тиры) — единственный источник правды; рамочный FORBIDDEN_GRADES выводим из него
    FORBIDDEN_GRADES = {en for en, ru in _RANK_RU.items() if ru not in MERGE_GRADES_RU}
    INV = CFG["inventory"]
    SLOT_FILL_THR = CFG.get("slot_fill_threshold", 48.0)
    CUBE_FILL_THR = CFG.get("cube_fill_threshold", 35.0)
    RESUME_IDLE = CFG.get("resume_idle_seconds", 10)
    IDLE_START = CFG.get("idle_start_seconds", 90)
    CURSOR_TOL = CFG.get("cursor_grab_tol_px", 90)
    MAX_MERGES_PER_TYPE = int(CFG.get("merge", {}).get("max_per_type", 5))
    SCAN_SETTLE = float(CFG.get("tooltip", {}).get("scan_hover_settle", 0.35))
    COUNT_SETTLE = float(CFG.get("count_settle", 0.15))
    INV_SCROLL_ROWS = float(CFG.get("inventory", {}).get("scroll_rows_per_notch", 0))
    INV_MAX_PAGES = int(CFG.get("inventory", {}).get("max_scroll_pages", 6))
    HERO_ROWS = int(CFG.get("inventory", {}).get("hero_inv_rows", 3))
    STASH_TABS = int(CFG.get("stash_tabs", 6))
    OFF = json.load(open(os.path.join(HERE, "offsets.json"), encoding="utf-8"))
    _extend_stash_tabs()
    pol = CFG.get("policy", {})
    OCR_DROPS = pol.get("ocr_drops", True)
    OCR_DROPS_MAX = int(pol.get("ocr_drops_max", 6))


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    try:
        sys.stdout.write(line + "\n"); sys.stdout.flush()
    except Exception:
        pass
    try:
        open(LOGF, "a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass
    if _LOG_CB:
        try:
            _LOG_CB(str(msg))
        except Exception:
            pass


def fw():
    for w in gw.getAllWindows():
        t = w.title or ""
        if t and any(s.lower() in t.lower() for s in CFG["window_title_contains"]) and w.width > 100:
            return w
    return None


def _hwnd():
    u = ctypes.windll.user32; res = []

    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h); b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1); c = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, c, 256)
            if any(s.lower() in (b.value or "").lower() for s in CFG["window_title_contains"]) \
                    and "unity" in c.value.lower():
                res.append(h)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return res[0] if res else None


def focus_game():
    h = _hwnd()
    if not h:
        return False
    # alt-трюк (human.focus_window): голый SetForegroundWindow из фонового процесса
    # молча не выводит окно вперёд -> клики уходят в неактивное Unity-окно и НЕ
    # регистрируются (панели не открываются, мерж=0). Доказано в сессии 2026-06-05.
    human.focus_window(h)
    return True


def _stopped():
    return _STOP_EVT is not None and _STOP_EVT.is_set()


def cede_if_user():
    """Вежливо УСТУПИТЬ, но НЕ обрывать: если юзер сейчас трогает мышь/клаву — встать на
    паузу и ждать, пока всё успокоится (нет ввода RESUME_IDLE сек), затем продолжить с того
    же места. Редкие одиночные клики просто проглатываются ожиданием. F12/СТОП прерывает.
    idle.idle_seconds() во время паузы меряет ТОЛЬКО юзера — бот в это время не кликает."""
    if not POLITE or DRY or _bot_cursor[0] is None:
        return
    if not user_grabbed():
        return
    if not _ceding[0]:
        _ceding[0] = True
        log(f"  ⏸ вижу твою активность — не мешаю, жду {RESUME_IDLE}с покоя мыши…")
    while not (human.kill_pressed(KKEY) or _stopped()):
        try:
            if idle.idle_seconds() >= RESUME_IDLE:
                _bot_cursor[0] = idle.cursor_pos()  # новая точка отсчёта
                log("  ▶ мышь в покое — продолжаю")
                _ceding[0] = False
                return
        except Exception:
            return
        time.sleep(0.5)
    _ceding[0] = False  # вышли по СТОП/F12


def k():
    """Стоп-сигнал: ТОЛЬКО F12 / кнопка СТОП. Активность юзера НЕ обрывает цикл — вместо
    этого cede_if_user() ставит паузу и ждёт покоя мыши, потом продолжаем с места."""
    if human.kill_pressed(KKEY) or _stopped():
        return True
    cede_if_user()
    return human.kill_pressed(KKEY) or _stopped()


def detect(sct, names=None):
    w = fw()
    return (w, vision.detect(w, sct, names=names)) if w else (None, {})


def isleep(sec):
    """Прерываемый сон: чанки по 0.1с с проверкой hardstop. False если прервали (СТОП/F12)."""
    slept = 0.0
    while slept < sec:
        if _hardstop():
            return False
        time.sleep(min(0.1, sec - slept))
        slept += 0.1
    return True


def click_el(panel, panel_name, elem, label=None, fast=False):
    """Клик по элементу elem панели panel_name (offsets, banner-relative).
    fast=True — мгновенный tap без гуманлайк-задержек (для быстрых скан-кликов по вкладкам)."""
    if _hardstop():            # СТОП/F12 -> мгновенно бросаем, не кликаем
        return False
    o = OFF.get(panel_name, {}).get(elem)
    if not o:
        log(f"  [нет offset {panel_name}.{elem}]"); return False
    x, y = vision.pt(panel, o[0], o[1])
    lbl = label or f"{panel_name}.{elem}"
    if DRY:
        log(f"  DRY click {lbl} @ ({x},{y})"); return True
    human.tap(x, y) if fast else human.click(x, y, CFG)
    _bot_cursor[0] = idle.cursor_pos()  # запомнить, где бот оставил курсор
    log(f"  click {lbl} @ ({x},{y})")
    return True


def grid_centers(panel, panel_name, tl_key, br_key, cols, rows):
    """Экранные центры сетки cols×rows по offsets tl/br (banner-relative -> screen)."""
    tl = OFF[panel_name][tl_key]; br = OFF[panel_name][br_key]
    x0, y0 = vision.pt(panel, tl[0], tl[1])
    x1, y1 = vision.pt(panel, br[0], br[1])
    out = []
    for r in range(rows):
        for c in range(cols):
            fx = c / (cols - 1) if cols > 1 else 0
            fy = r / (rows - 1) if rows > 1 else 0
            out.append((r, c, int(x0 + (x1 - x0) * fx), int(y0 + (y1 - y0) * fy)))
    return out


def cube_filled(sct, panel):
    """Сколько из 9 ячеек куба заняты (яркость)."""
    cells = grid_centers(panel, "cube", "grid_tl", "grid_br", 3, 3)
    s = max(int(0.20 * panel["w"]), 12)  # размер пробы ~доля баннера
    n = 0
    for (_, _, cx, cy) in cells:
        img = np.array(sct.grab({"left": int(cx - s / 2), "top": int(cy - s / 2),
                                 "width": s, "height": s}))[:, :, :3]
        if float(img.mean()) > CUBE_FILL_THR:
            n += 1
    return n


SLOT_FILL_THR = CFG.get("slot_fill_threshold", 48.0)  # яркость ячейки инв/стэш: занято если выше
# Инвентарь HERO = 7×3 (21 слот), а НЕ 7×6 как тайник! Раздельная сетка: иначе ряды считаются
# вдвое плотнее (шаг Y 24 вместо 60) и ОДИН предмет попадает в 2 ячейки => «2 вместо 1».
HERO_ROWS = int(CFG.get("inventory", {}).get("hero_inv_rows", 3))
STASH_TABS = int(CFG.get("stash_tabs", 6))  # сколько вкладок тайника (растёт по ходу игры)


def _extend_stash_tabs():
    """Достроить координаты вкладок tab(N+1)..STASH_TABS экстраполяцией шага между последними
    откалиброванными (offsets.json калибрует только первые ~5). Вкладки в ряд с равным шагом ->
    tabN = последняя + (последняя - предыдущая). Без этого 6-я+ вкладка не кликалась (нет
    offset) и не сканировалась/раскладывалась."""
    st = OFF.get("stash")
    if not st:
        return
    cal = []
    i = 1
    while f"tab{i}" in st:
        cal.append(st[f"tab{i}"]); i += 1
    if len(cal) < 2:
        return
    dx = cal[-1][0] - cal[-2][0]
    dy = cal[-1][1] - cal[-2][1]
    for n in range(len(cal) + 1, STASH_TABS + 1):
        prev = st[f"tab{n-1}"]
        st[f"tab{n}"] = [round(prev[0] + dx, 4), round(prev[1] + dy, 4)]


_extend_stash_tabs()


def count_filled(sct, panel, panel_name, tl_key, br_key, cols, rows, thr=None, park=True):
    """Сколько ячеек сетки cols×rows заняты (по яркости центра ячейки). Вернуть (n, total).
    park=True: УВЕСТИ КУРСОР перед подсчётом — иначе тултип от прошлого наведения перекрывает
    ячейки и они читаются как пустые (был баг «17 вместо 41»)."""
    if park and not DRY:
        human.park(); time.sleep(0.12)
    cells = grid_centers(panel, panel_name, tl_key, br_key, cols, rows)
    if len(cells) < 2:
        return 0, len(cells)
    xs = sorted(set(c[2] for c in cells)); ys = sorted(set(c[3] for c in cells))
    px = (xs[-1] - xs[0]) / max(cols - 1, 1); py = (ys[-1] - ys[0]) / max(rows - 1, 1)
    s = max(int(0.45 * min(px, py)), 8)
    t = SLOT_FILL_THR if thr is None else thr
    n = 0
    for (_, _, cx, cy) in cells:
        img = np.array(sct.grab({"left": int(cx - s / 2), "top": int(cy - s / 2),
                                 "width": s, "height": s}))[:, :, :3]
        if float(img.mean()) > t:
            n += 1
    return n, len(cells)


# ── ПАМЯТЬ ПОСАДОЧНОЙ ЯЧЕЙКИ ──────────────────────────────────────────────────────────
# Лут в TBH падает в ПЕРВУЮ свободную ячейку инвентаря (row-major: слева-направо, сверху-вниз).
# Запоминаем её после прескана/сейва → потом дёшево проверяем ОДНУ ячейку (не весь инвентарь):
# посветлела = прилетел новый предмет → точечный OCR/прелок + сдвиг указателя на следующую пустую.
# stale=True помечаем после ЛЮБОЙ мутации инвентаря (save-all/sort/merge) — точку надо пересчитать.
LANDING = {"rc": None, "empty_mean": None, "stale": True}
EMPTY_CELL_MARGIN = 6        # порог «пусто»: ниже SLOT_FILL_THR - margin считаем гарантированно пустой


def first_empty_cell(sct, panel, panel_name, tl_key, br_key, cols, rows, thr=None):
    """Первая ПУСТАЯ ячейка сетки (row-major). Вернуть (r, c, x, y, mean) или None если всё занято.
    Курсор паркуем (как в count_filled) — иначе тултип перекроет ячейку и она «занята»."""
    if not DRY:
        human.park(); time.sleep(0.1)
    cells = grid_centers(panel, panel_name, tl_key, br_key, cols, rows)
    t = SLOT_FILL_THR if thr is None else thr
    xs = sorted(set(c[2] for c in cells)); ys = sorted(set(c[3] for c in cells))
    px = (xs[-1] - xs[0]) / max(cols - 1, 1) if len(xs) > 1 else 20
    py = (ys[-1] - ys[0]) / max(rows - 1, 1) if len(ys) > 1 else 20
    s = max(int(0.45 * min(px, py)), 8)
    for (r, c, cx, cy) in cells:
        img = np.array(sct.grab({"left": int(cx - s / 2), "top": int(cy - s / 2),
                                 "width": s, "height": s}))[:, :, :3]
        m = float(img.mean())
        if m <= t:
            return r, c, cx, cy, m
    return None


def remember_landing_slot(sct, hero=None):
    """Запомнить первую пустую ячейку инвентаря HERO как «посадочную» (куда упадёт новый лут).
    Нужен открытый HERO на вкладке Inventory. Тихо no-op если инвентарь не виден/полон."""
    if hero is None:
        _, d = detect(sct); hero = d.get("hero")
    if not hero:
        return None
    fe = first_empty_cell(sct, hero, "hero", "inv_tl", "inv_br", INV["cols"], HERO_ROWS)
    if fe is None:
        LANDING.update(rc=None, empty_mean=None, stale=False)   # инвентарь полон → лут пойдёт в почту
        return None
    r, c, _x, _y, m = fe
    LANDING.update(rc=(r, c), empty_mean=m, stale=False)
    return (r, c)


def landing_filled(sct, hero=None):
    """Дёшево: посветлела ли посадочная ячейка (прилетел ли новый предмет)? Вернуть bool|None.
    None — посадка не запомнена/устарела/инвентарь не виден (надо remember_landing_slot)."""
    if LANDING.get("stale") or LANDING.get("rc") is None:
        return None
    if hero is None:
        _, d = detect(sct); hero = d.get("hero")
    if not hero:
        return None
    r, c = LANDING["rc"]
    cells = grid_centers(hero, "hero", "inv_tl", "inv_br", INV["cols"], HERO_ROWS)
    cell = next((cc for cc in cells if cc[0] == r and cc[1] == c), None)
    if not cell:
        return None
    _, _, cx, cy = cell
    s = CFG.get("grid_cell_capture_size", 44)
    img = np.array(sct.grab({"left": int(cx - s / 2), "top": int(cy - s / 2),
                             "width": s, "height": s}))[:, :, :3]
    return float(img.mean()) > SLOT_FILL_THR


def landing_mark_stale():
    """Пометить посадочную ячейку устаревшей (после save-all/sort/merge — инвентарь сдвинулся)."""
    LANDING["stale"] = True


def ensure_inventory_tab(sct):
    """Переключить HERO на вкладку Inventory (НЕ Formation/ростер) перед чтением инвентаря.
    КОРЕНЬ багов «8 вместо 10 / 0 / 16»: на вкладке Formation сетка инвентаря попадает на
    иконки персонажей/петов → мусорный счёт. Клик по вкладке идемпотентен (уже Inventory →
    остаётся). Курсор паркуется на кнопке (ниже сетки, не перекрывает ячейки). Вернуть hero|None."""
    w, d = detect(sct, names=["hero"])
    h = d.get("hero")
    if not h:
        h = ensure_open(sct, "hero")
    if not h:
        return None
    off = OFF.get("hero", {}).get("inv_tab")
    if off and not DRY:
        x, y = vision.pt(h, off[0], off[1])
        human.click(x, y, CFG)
        _bot_cursor[0] = idle.cursor_pos()
        time.sleep(COUNT_SETTLE)
        h = detect(sct, names=["hero"])[1].get("hero", h)
    return h


def inv_fill(sct):
    """Занятых ячеек в инвентаре HERO (нужен открытый HERO). -1 если не виден."""
    _, d = detect(sct)
    h = d.get("hero")
    if not h:
        return -1
    n, _ = count_filled(sct, h, "hero", "inv_tl", "inv_br", INV["cols"], HERO_ROWS)
    return n


_DROP_SNAP = {}   # (r,c) -> grade: что лежало в инвентаре в прошлый скан (для дроп-фида)
_RANK_RU = {"common": "обычный", "uncommon": "необычный", "rare": "редкий",
            "legendary": "легендарный", "epic": "аркана", "red": "бессмертный"}


_LOW_TIERS = {"common", "uncommon", "rare", "legendary"}   # рамка надёжна только для них


def count_mergeable(sct, hero):
    """Занятых ячеек инвентаря HERO с МЕРЖАБЕЛЬНЫМ грейдом (НЕ в FORBIDDEN_GRADES epic/red;
    нечитаемый None считаем мержабельным — forbid-логика). ЧИСТО по рамке (ip.analyze),
    БЕЗ наведения/OCR/движения курсора — иначе скан дёргает мышь, искажает занятость
    (тултип перекрывает соседнюю ячейку → счёт скачет 7→2), задваивает дроп-лог и ложно
    «уступает юзеру». Точные имя/уровень/грейд читает СТАРТОВЫЙ скан (prescan), не этот счёт.
    ПОБОЧНО: лёгкий дроп-фид по грейду рамки (без наведения)."""
    cells = grid_centers(hero, "hero", "inv_tl", "inv_br", INV["cols"], HERO_ROWS)
    s = CFG.get("grid_cell_capture_size", 44)
    n = 0
    cur = {}
    for r, c, x, y in cells:
        img = np.array(sct.grab({"left": int(x - s / 2), "top": int(y - s / 2),
                                 "width": s, "height": s}))[:, :, :3]
        if float(img.mean()) < SLOT_FILL_THR:
            continue
        rank = ip.analyze(img).get("rank")
        cur[(r, c)] = rank
        if rank not in FORBIDDEN_GRADES:
            n += 1
    # дроп-фид БЕЗ наведения: только новые/сменившиеся слоты, грейд от рамки.
    # Рамка путает высокие тиры → для не-низких не врём грейдом, помечаем нейтрально.
    new_slots = [sl for sl in cur if _DROP_SNAP.get(sl, "__") != cur[sl]]
    if 0 < len(new_slots) <= 12:        # >12 = после раскладки переснялось всё, не спамим
        for sl in new_slots:
            g = cur[sl]
            label = _RANK_RU.get(g, g) if g in _LOW_TIERS else "ценный предмет"
            log(f"  дроп: {label}")
    _DROP_SNAP.clear()
    _DROP_SNAP.update(cur)
    return n


def _ocr_read(sct, x, y, flip="right", settle=None):
    """items.read_item + ОБНОВИТЬ _bot_cursor. Критично: OCR-ховер двигает курсор, иначе
    POLITE-гейт user_grabbed() примет это за «юзер вернулся» и оборвёт цикл/скан.
    settle=None -> из конфига (медленно, надёжно); число -> быстрый скан."""
    import items
    d = items.read_item(sct, (x, y), flip=flip, settle=settle)
    try:
        _bot_cursor[0] = idle.cursor_pos()
    except Exception:
        pass
    return d


def _drop_line(sct, x, y):
    """OCR наведением на новый предмет HERO-инвентаря: '«Имя» ур.N · грейд'.
    Имя/тип берём из items_db (надёжно), грейд — словом из тултипа. None если не прочиталось."""
    try:
        d = _ocr_read(sct, x, y, flip="left")
    except Exception:
        return None
    import items
    name = d.get("db_name")        # ТОЛЬКО каноничное имя из БД (raw-OCR имя часто мусор)
    grade = d.get("rank")          # рус. слово тира из тултипа
    if grade and items.rank_to_tier(grade) >= 4:
        # высокий грейд (Бессмертный+) ПОДТВЕРЖДАЕМ модой из 3 — не врать (как в scan_grades)
        reads = [grade.lower()]
        for _ in range(2):
            r = items.read_grade(sct, (x, y), flip="left", settle=0.45)
            if r:
                reads.append(r.lower())
        from collections import Counter
        top, cnt = Counter(reads).most_common(1)[0]
        grade = top if cnt >= 2 else None   # нет согласия 2/3 -> грейд не показываем
    lvl = d.get("level_req")
    parts = []
    if name:
        parts.append(f"«{name}»")
    if lvl:
        parts.append(f"ур.{lvl}")
    if grade:
        parts.append(f"· {grade}")
    return " ".join(parts) if parts else None


# рамочные ранги, на которых классификатор НЕнадёжен (золото/красное + материалы с
# золотой рамкой): легендарный↔бессмертный↔аркана↔запредельный… — различимы только OCR.
_AMBIG_FRAME = {"legendary", "red", "epic", None}


def game_hwnd():
    """HWND окна игры (кэш в items._GAME_HWND)."""
    import items
    if items._GAME_HWND is None:
        items._GAME_HWND = human.find_hwnd(CFG["window_title_contains"])
    return items._GAME_HWND


def ensure_game_foreground(force=True, retries=3):
    """Игра должна быть foreground (иначе Unity не рисует тултипы). force=True — активно
    вывести вперёд (лесенка + реальный клик по безопасной зоне игры). Вернуть True/False."""
    hwnd = game_hwnd()
    if not hwnd:
        return False
    if not force:
        return human.is_foreground(hwnd)
    w = fw()
    click_xy = None
    if w:
        click_xy = (int(w.left + CFG.get("focus_click_rx", 0.40) * w.width),
                    int(w.top + CFG.get("focus_click_ry", 0.93) * w.height))
    ok = human.ensure_foreground(hwnd, click_xy, retries=retries)
    if ok:
        try:
            _bot_cursor[0] = idle.cursor_pos()
        except Exception:
            pass
    return ok


def scan_grades(sct, panel, panel_name, tl, br, cols, rows, ocr=False, flip="right"):
    """Грейд-разбивка занятых ячеек: {grade_ru|'неизв': count}. ДВА ПРОХОДА:
    A) ПАРКУЕМ курсор → снимаем занятость по всем ячейкам ЧИСТО (тултип не перекрывает) —
       так счёт верный (был баг «17 вместо 41», когда тултип закрывал половину).
    B) по каждой ЗАНЯТОЙ ячейке читаем грейд: OCR тултипа (сверка со словарём 10 грейдов в
       _rank_in, одно чтение надёжно) → не прочёл → рамка. Занятость уже снята, наведения её
       не портят. flip: 'right'=СТЭШ, 'left'=HERO."""
    can_ocr = ocr and human.is_foreground(game_hwnd())
    cells = grid_centers(panel, panel_name, tl, br, cols, rows)
    xs = sorted(set(c[2] for c in cells)); ys = sorted(set(c[3] for c in cells))
    px = (xs[-1] - xs[0]) / max(cols - 1, 1); py = (ys[-1] - ys[0]) / max(rows - 1, 1)
    s = max(int(0.45 * min(px, py)), 8)
    # ── проход A: занятость (курсор увели, чтобы тултип не закрывал ячейки) ──
    if not DRY:
        human.park(); time.sleep(0.12)
    occupied = []
    for r, c, x, y in cells:
        img = np.array(sct.grab({"left": int(x - s / 2), "top": int(y - s / 2),
                                 "width": s, "height": s}))[:, :, :3]
        if float(img.mean()) >= SLOT_FILL_THR:
            occupied.append((x, y, _RANK_RU.get(ip.analyze(img).get("rank"), None)))
    # ── проход B: грейд каждого занятого (OCR/рамка) ──
    out = {}
    for (x, y, frame_ru) in occupied:
        if _hardstop():
            break
        cede_if_user()
        if not ocr:
            g = frame_ru
        elif can_ocr:
            try:
                import items
                g = items.read_grade(sct, (x, y), flip=flip, settle=SCAN_SETTLE) or frame_ru
                try:
                    _bot_cursor[0] = idle.cursor_pos()
                except Exception:
                    pass
            except Exception as _e:
                logx.log_debug(f"scan_grades: OCR-грейд сорвался @{(x, y)} → фолбэк рамка: {_e!r}")
                g = frame_ru
        else:
            g = frame_ru
        key = g.lower() if g else "неизв"
        out[key] = out.get(key, 0) + 1
    return out


def _grid_mid(panel, panel_name, tl, br):
    """Центр сетки (точка, над которой крутим колесо для скролла списка)."""
    cells = grid_centers(panel, panel_name, tl, br, 1, 1) if False else \
        grid_centers(panel, panel_name, tl, br, 3, 3)
    mx = sum(c[2] for c in cells) // len(cells)
    my = sum(c[3] for c in cells) // len(cells)
    return mx, my


def scan_inv_full(sct, hero, ocr=True, flip="left"):
    """Грейд-разбивка ВСЕГО инвентаря HERO с учётом прокрутки (инвентарь расширен —
    в видимую сетку 7×6 влезает не всё). Скроллим колесом ровно на один экран сетки,
    чтобы страницы НЕ перекрывались, складываем грейды. INV_SCROLL_ROWS=0 -> одна
    страница (поведение как раньше, безопасно до калибровки колеса).
    Стоп: пустая страница, либо подпись страницы повторилась (доскроллили до низа)."""
    cols, rows = INV["cols"], HERO_ROWS
    if INV_SCROLL_ROWS <= 0:
        return scan_grades(sct, hero, "hero", "inv_tl", "inv_br", cols, rows, ocr=ocr, flip=flip)
    mx, my = _grid_mid(hero, "hero", "inv_tl", "inv_br")
    page_notches = max(1, round(rows / INV_SCROLL_ROWS))   # колёсиков на один экран сетки
    # к началу списка
    try:
        human.wheel(mx, my, page_notches * (INV_MAX_PAGES + 1), settle=0.25)
    except Exception as _e:
        logx.log_debug(f"scan_inv_full: скролл к началу сорвался: {_e!r}")
    total = {}
    prev_sig = None
    pages = 0
    for p in range(INV_MAX_PAGES):
        if _hardstop():
            break
        hero = detect(sct)[1].get("hero", hero)   # баннер мог чуть сместиться от анимации
        g = scan_grades(sct, hero, "hero", "inv_tl", "inv_br", cols, rows, ocr=ocr, flip=flip)
        sig = tuple(sorted(g.items()))
        if sum(g.values()) == 0:
            break                                  # пустая страница — дальше пусто
        if sig == prev_sig:
            break                                  # не сдвинулось = низ списка, не считаем дважды
        for k, v in g.items():
            total[k] = total.get(k, 0) + v
        prev_sig = sig
        pages += 1
        try:
            human.wheel(mx, my, -page_notches, settle=0.25)  # вниз на один экран
        except Exception:
            break
    if pages > 1:
        log(f"  инвентарь: просканировано страниц прокрутки: {pages}")
    return total


def cube_grade(sct, panel):
    """Грейд набранного в кубе — по цвету плитки ПЕРВОЙ занятой ячейки (autofill кладёт
    9 одного грейда). Вернуть rank (common/uncommon/rare/legendary/epic/red) или None."""
    cells = grid_centers(panel, "cube", "grid_tl", "grid_br", 3, 3)
    s = max(int(0.17 * panel["w"]), 14)  # ~одна ячейка: рамка-грейд + иконка
    ranks = []
    for (_, _, cx, cy) in cells:
        img = np.array(sct.grab({"left": int(cx - s / 2), "top": int(cy - s / 2),
                                 "width": s, "height": s}))[:, :, :3]
        if float(img.mean()) > CUBE_FILL_THR:
            ranks.append(ip.analyze(img)["rank"])
    if not ranks:
        return None
    return max(set(ranks), key=ranks.count)  # самый частый среди занятых


# ---------- шаги ----------

def dismiss_popups(sct, max_tries=3):
    """Закрыть серверный МОДАЛЬНЫЙ попап 'SERVER ITEM VALIDATION RESULTS' (и любой с красной
    кнопкой Confirm): matchTemplate кнопки по окну (мультимасштаб) -> клик по найденной точке.
    Без этого попап блокирует ВСЁ: бот вслепую жмёт Stash All в no-op, а inv_fill принимает
    яркий попап за полный инвентарь (42/42) — джем. Вызывать в начале цикла и после мержей."""
    if not _CONFIRM_ICONS or DRY:
        return 0
    w = fw()
    if not w:
        return 0
    thr = CFG.get("confirm_threshold", 0.70)
    dismissed = 0
    for _ in range(max_tries):
        top = max(0, int(w.top))
        img = np.ascontiguousarray(np.array(sct.grab({"left": int(w.left), "top": top,
            "width": int(w.width), "height": min(int(w.height), 1440 - top)}))[:, :, :3])
        best, bx, by = 0.0, 0, 0
        for icon in _CONFIRM_ICONS:
            for sc in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0]:
                th, tw = int(icon.shape[0] * sc), int(icon.shape[1] * sc)
                if th < 12 or tw < 24 or th > img.shape[0] or tw > img.shape[1]:
                    continue
                t = cv2.resize(icon, (tw, th), interpolation=cv2.INTER_AREA)
                res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
                _, mx, _, ml = cv2.minMaxLoc(res)
                if mx > best:
                    best, bx, by = mx, ml[0] + tw // 2, ml[1] + th // 2
        if best < thr:
            break
        sx, sy = int(w.left) + bx, top + by
        log(f"  ⚠ ПОПАП валидации — закрываю Confirm @ ({sx},{sy}) score={best:.2f}")
        human.click(sx, sy, CFG)
        _bot_cursor[0] = idle.cursor_pos()
        dismissed += 1
        time.sleep(1.2)
    return dismissed


def press_tab():
    """Меню [Tab] — открыть меню из свёрнутого/прозрачного вида (bootstrap/сброс)."""
    if DRY:
        log("  DRY Tab"); return
    human.key("tab", CFG)
    time.sleep(1.0)


def click_window_rel(rx, ry, label):
    """Клик по точке окна в долях (для свёрнутого вида, где баннера нет)."""
    w = fw()
    if not w:
        return
    x, y = int(w.left + rx * w.width), int(w.top + ry * w.height)
    if DRY:
        log(f"  DRY click {label} @ ({x},{y})"); return
    human.click(x, y, CFG)
    _bot_cursor[0] = idle.cursor_pos()
    logx.log_debug(f"click {label} @ ({x},{y})")   # координаты — debug, не спамим панель


def ensure_hero(sct):
    """Гарантировать HERO открытым. Свёрнуто/прозрачно: СНАЧАЛА клик по игре (область боя)
    — даёт фокус окну (Unity без реального клика Tab не примет), ПОТОМ Tab."""
    w, d = detect(sct)
    if "hero" in d:
        return d["hero"]
    if _hardstop():
        return None
    # МЕНЮ УЖЕ ОТКРЫТО (есть баннеры панелей), но HERO не считался — это ПРОМАХ детекта, а НЕ
    # свёрнутое меню. Tab тут ЗАКРОЕТ открытое меню (баг «нажал Tab при открытом инвентаре»).
    # Поэтому: дать дорисоваться и перечитать БЕЗ Tab.
    if d:
        time.sleep(0.3)
        w, d = detect(sct)
        return d.get("hero")   # есть hero — вернём; нет — None, но Tab НЕ жмём (меню открыто)
    # detect ПУСТ → меню реально свёрнуто/прозрачно → вот ТУТ Tab уместен
    logx.log_debug("меню свёрнуто — фокус(alt) + клик по бою + Tab")   # операционное → debug, не спамим панель
    focus_game()  # alt-трюк: НАДЁЖНО вывести игру вперёд (клик по прозрачному окну проходит
                  # насквозь и фокус не даёт; Tab без фокуса уходит в чужое окно)
    click_window_rel(CFG.get("focus_click_rx", 0.40), CFG.get("focus_click_ry", 0.93),
                     "фокус-клик по игре")
    time.sleep(0.3)
    press_tab()
    w, d = detect(sct)
    return d.get("hero")


def ensure_open(sct, name):
    """Гарантировать панель name открытой (Tab-bootstrap + тоггл в HERO). Вернуть dict|None.
    Клик-тоггл + ПОЛЛИНГ детекта (анимация открытия ~до 2.4с — без поллинга детект
    срабатывал слишком рано => «не открыт»). До 2 попыток клика."""
    w, d = detect(sct, names=[name, "hero"])
    if name in d:
        return d[name]
    hero = ensure_hero(sct)
    if not hero:
        log(f"  [ensure {name}] HERO не открылся даже после Tab"); return None
    if name == "hero":
        return hero
    toggle = "open_stash" if name == "stash" else ("open_cube" if name == "cube" else None)
    if not toggle:
        return None
    for attempt in range(2):
        if k():
            return None
        click_el(hero, "hero", toggle, f"открыть {name}")
        for _ in range(6):                  # поллинг (detect ~быстрый с names → больше запас по времени)
            if _hardstop():                 # СТОП — мгновенно выходим из поллинга
                return None
            time.sleep(0.3)
            w, d = detect(sct, names=[name, "hero"])
            if name in d:
                return d[name]
            hero = d.get("hero", hero)       # обновить ссылку на hero (мог сместиться)
        log(f"  [ensure {name}] не появился после клика (попытка {attempt+1}/2)")
    return None


def clear_panels(sct):
    """Закрыть лишние панели (RUNES/STATUS/SETTINGS/PORTAL/TRADE SHIP), которые перекрывают
    куб/стэш. ESC закрывает верхнюю открытую панель — проверено живьём 2026-06-07: диалога
    выхода НЕ открывает, на пустом экране ESC безвреден (no-op). Бьём короткую серию ESC (до 4),
    выходя, когда баннеров на экране не осталось (все 9 панелей зашаблонены в vision.PANELS)."""
    _BLK = ("runes", "status", "settings", "portal", "tradeship")
    _, d = detect(sct, names=_BLK)        # детектим ТОЛЬКО блокирующие (1-5 шаблонов, не все 9 — быстро)
    blk = [n for n in d if n in _BLK]
    if not blk:
        return                            # чистить нечего — НЕ бьём ESC вслепую (экономит ~7с старта)
    log(f"  лишние панели открыты: {blk} — закрываю (ESC)")
    for i in range(4):
        if k():
            return
        human.key("esc", CFG)
        time.sleep(0.45)
        _, d = detect(sct, names=_BLK)
        if not d:                         # блокирующих баннеров не осталось -> чисто
            break


_MAIL_ICON = os.path.join(HERE, "templates", "icons", "mail_icon.png")


def click_mail_icon(sct):
    """Открыть почту кликом по иконке конверта в тулбаре. ПЕРВИЧНО — template-матч иконки
    (vision.find_icon): надёжно и НЕ зависит от того, какая панель открыта и где окно
    (иконка тулбара не привязана к баннеру hero). Fallback — hero-offset open_mail.
    True если кликнули по чему-то."""
    win = fw()
    if win and os.path.exists(_MAIL_ICON):
        hit = vision.find_icon(win, sct, _MAIL_ICON, thr=0.6)
        if hit:
            human.click(hit[0], hit[1], CFG)
            try:
                _bot_cursor[0] = idle.cursor_pos()
            except Exception:
                pass
            return True
    _, d = detect(sct)
    hero = d.get("hero")
    if hero:
        click_el(hero, "hero", "open_mail", "открыть почту (offset)")
        return True
    return False


def close_dropdown(cube):
    """Закрыть открытый дропдаун кликом в НЕЙТРАЛЬНУЮ область (баннер куба — он НАД
    дропдауном, клик по нему ничего не задевает, но закрывает список).
    Без этого следующий клик может попасть в ещё открытый список (баг с Offering)."""
    if DRY:
        return
    x, y = vision.pt(cube, 0.0, 0.0)  # центр баннера куба = безопасная пустая точка
    human.click(x, y, CFG)
    _bot_cursor[0] = idle.cursor_pos()
    time.sleep(0.18)


def in_synthesis(cube, sct):
    """Подтвердить, что куб в режиме Synthesis — по иконке-кристаллу в заголовке режима
    (языконезависимо). Защита: НЕ жать autofill в Offering/Removal/Alchemy и т.п."""
    if _SYNTH_ICON is None:
        # fail-CLOSED (аудит F8): без шаблона режим не подтвердить -> НЕ мержим (безопаснее,
        # чем мерж в Offering/Alchemy). Раньше было return True (fail-open) = риск слить не там.
        log("  ⚠ нет шаблона synthesis_icon — режим не подтверждён, мерж пропускаю (защита)")
        return False
    mt = OFF["cube"]["mode_toggle"]
    cx, cy = vision.pt(cube, mt[0] - 0.15, mt[1])  # чуть левее центра пилюли — там иконка
    w = cube["w"]
    bw, bh = max(int(0.9 * w), 30), max(int(0.45 * w), 18)
    box = {"left": int(cx - bw / 2), "top": max(0, int(cy - bh / 2)), "width": bw, "height": bh}
    img = np.array(sct.grab(box))[:, :, :3]
    best = 0.0
    for s in [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]:
        th, tw = int(_SYNTH_ICON.shape[0] * s), int(_SYNTH_ICON.shape[1] * s)
        if th < 8 or tw < 8 or th > img.shape[0] or tw > img.shape[1]:
            continue
        t = cv2.resize(_SYNTH_ICON, (tw, th), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, _ = cv2.minMaxLoc(res)
        best = max(best, mx)
    return best >= CFG.get("synth_icon_threshold", 0.62)


def ensure_synthesis(sct, cube):
    """Форсить режим = Synthesis с ПРОВЕРКОЙ. Вернуть True если подтверждён.
    Открыть дропдаун -> выбрать Synthesis -> ЗАКРЫТЬ дропдаун -> verify (до 2 попыток)."""
    if DRY:
        log("  DRY ensure Синтез"); return True
    for attempt in range(2):
        if in_synthesis(cube, sct):
            return True
        click_el(cube, "cube", "mode_toggle", "режим-дропдаун")
        time.sleep(0.28)
        _, d = detect(sct)
        cube = d.get("cube", cube)
        click_el(cube, "cube", "mode_synthesis", "выбрать Synthesis")
        time.sleep(0.22)
        close_dropdown(cube)  # закрыть список, иначе след. клик уедет в Offering
        _, d = detect(sct)
        cube = d.get("cube", cube)
    ok = in_synthesis(cube, sct)
    if not ok:
        log("  ⚠ Synthesis НЕ подтверждён иконкой — мерж пропущу (защита от Offering/трат)")
    return ok


def set_type(sct, cube, type_elem):
    """Открыть выпадашку типа autofill, выбрать тип -> ЗАКРЫТЬ дропдаун."""
    if DRY:
        log(f"  DRY set type {type_elem}"); return
    click_el(cube, "cube", "type_toggle", "тип-дропдаун")
    time.sleep(0.22)
    _, d = detect(sct)
    cube2 = d.get("cube", cube)
    click_el(cube2, "cube", type_elem, f"тип={type_elem}")
    time.sleep(0.22)
    close_dropdown(cube2)  # закрыть список типа, чтобы autofill не попал в него


def ensure_cube_level_max(sct, cube):
    """Выставить дропдаун ДИАПАЗОНА УРОВНЯ куба на МАКСИМУМ (нижний пункт списка = самый высокий
    доступный, напр. Lv.65~80) перед autofill. Иначе autofill берёт предметы выбранного диапазона
    и может смешать хай-/лоу-лвл. Юзер: «держать уровень максимальный из открытых». Идемпотентно —
    раз за мерж-проход. Не откалибровано (нет offset) → тихий пропуск (старое поведение)."""
    if DRY:
        log("  DRY уровень→макс"); return
    # по флагу: форсить макс. диапазон уровня. ВЫКЛ по умолчанию — у юзера с лоу-лвл предметами
    # макс (65~80) autofill ничего не подхватит и мерж встанет. Вкл для энд-гейма / «мерж из тайника».
    if not CFG.get("cube_level_max", False):
        return
    co = OFF.get("cube", {})
    if not co.get("level_toggle") or not co.get("level_max"):
        return
    click_el(cube, "cube", "level_toggle", "уровень-дропдаун")
    human.pause(CFG, 0.2, 0.38)
    _, d = detect(sct); cube = d.get("cube", cube)
    click_el(cube, "cube", "level_max", "уровень=макс")
    human.pause(CFG, 0.2, 0.38)
    close_dropdown(cube)
    log("уровень куба → максимум")


def do_saveall_sort(sct):
    """Разложить инвентарь по ВСЕМ 5 вкладкам стэша + сортировка.
    На каждой вкладке: выбрать вкладку -> Stash All (перелив идёт в выбранную вкладку,
    если игра не авто-распределяет) -> лог заполнения. Так забивается не 2 вкладки, а все 5
    (фикс прошлой ночной поломки). Stash All по пустому инвентарю = no-op, безвредно."""
    st = ensure_open(sct, "stash")
    if not st:
        log("  [save/sort] STASH не открыт"); return
    inv0 = inv_fill(sct)
    log(f"  [save] инвентарь до раскладки: {inv0} занято")
    tabs = [f"tab{i}" for i in range(1, STASH_TABS + 1)]
    for i, tab in enumerate(tabs, 1):
        if k():
            return
        _, d = detect(sct); st = d.get("stash", st)
        click_el(st, "stash", tab, f"вкладка {i}")
        human.pause(CFG, 0.4, 0.8)
        _, d = detect(sct); st = d.get("stash", st)
        click_el(st, "stash", "save_all", f"Stash All -> вкл{i}")
        human.pause(CFG, 0.3, 0.5)
        _, d = detect(sct); st = d.get("stash", st)
        nf, tot = count_filled(sct, st, "stash", "grid_tl", "grid_br", 7, 6)
        invn = inv_fill(sct)
        log(f"  [стэш] вкл{i}: {nf}/{tot} занято | инвентарь ещё: {invn}")
        if invn == 0:
            log(f"  [save] инвентарь разложен (вкладок задействовано: {i})")
            break
    _, d = detect(sct); st = d.get("stash", st)
    click_el(st, "stash", "sort", "Сортировать"); human.pause(CFG, 0.5, 1.0)
    landing_mark_stale()        # инвентарь разложен/отсортирован → посадочную ячейку пересчитать


def cube_grade_ocr(sct, cube):
    """OCR-грейд набранного в кубе — НАДЁЖНО (рамка-классификатор путает legendary с аркана/
    запредельным, особенно у материалов с золотой рамкой). Наводит на 1-ю ячейку куба, читает
    ранг тултипа (ru). Пробует оба флипа. None если не прочитал -> вызывающий считает опасным."""
    try:
        import items
        o = OFF.get("cube", {}).get("grid_tl")
        if not o:
            return None
        x, y = vision.pt(cube, o[0], o[1])
        for flip in ("left", "right"):
            if _hardstop():
                return None
            d = _ocr_read(sct, x, y, flip)
            if d.get("rank"):
                return d["rank"]
    except Exception as e:
        log(f"  [cube OCR] {e!r}")
    return None


def _ensure_cube_empty(sct, cube, tries=2):
    """Куб должен быть ПУСТ перед автозаполнением. Если возврат прошлого набора не сработал
    (UI-лаг), остаток смешается с новым → можно слить не то. Дожимаем возврат, проверяем яркостью."""
    for _ in range(tries):
        _, d = detect(sct); cube = d.get("cube", cube)
        if cube_filled(sct, cube) == 0:
            return True
        click_el(cube, "cube", "return_btn", "очистка куба (остаток прошлого набора)")
        human.pause(CFG, 0.5, 0.9)
    _, d = detect(sct); cube = d.get("cube", cube)
    return cube_filled(sct, cube) == 0


def merge_all(sct):
    cube = ensure_open(sct, "cube")
    if not cube:
        log("  [мерж] CUBE не открыт"); return 0
    if not ensure_synthesis(sct, cube):
        log("  [мерж] режим Synthesis не подтверждён — пропуск мержа (защита)")
        return 0
    _, d = detect(sct); cube = d.get("cube", cube)
    ensure_cube_level_max(sct, cube)            # держать диапазон уровня на максимуме перед autofill
    _, d = detect(sct); cube = d.get("cube", cube)
    # какие типы мержим: lock_accessory (дефолт ON) → украшения НЕ трогаем; merge_materials → материалы
    pol = CFG.get("policy", {})
    types = [t for t in MERGE_TYPES
             if not (t == "type_accessory" and pol.get("lock_accessory", True))
             and not (t == "type_materials" and not pol.get("merge_materials", True))]
    total = 0
    for tp in types:
        if k():
            break
        _, d = detect(sct); cube = d.get("cube", cube)
        set_type(sct, cube, tp)
        ru = TYPE_RU.get(tp, tp)
        # единый список грейдов для всех типов (бело/зелёно/синее); бижу всё равно залочена lock_accessory
        allowed = set(MERGE_GRADES_RU)
        for attempt in range(MAX_MERGES_PER_TYPE + 1):
            if k():
                break
            _, d = detect(sct); cube = d.get("cube", cube)
            if not _ensure_cube_empty(sct, cube):     # защита: остаток прошлого набора не смешать
                log(f"{ru}: куб не пуст — пропуск (защита)")
                break
            click_el(cube, "cube", "autofill", f"autofill[{tp}]#{attempt+1}")
            human.pause(CFG, 0.4, 0.65)
            if DRY:
                break
            n = cube_filled(sct, cube)
            dbg_shot(f"{tp}_autofill{attempt+1}_{n}of9.png")
            if n >= 9:
                grade = cube_grade(sct, cube)            # рамка (грубо), для дешёвого отказа
                frame_ru = _RANK_RU.get(grade)
                # дешёвый первичный отказ: рамка уверенно-высокая (epic/red) и грейд НЕ разрешён
                if grade in ("epic", "red") and frame_ru not in allowed:
                    log(f"{ru}: набор «{frame_ru or grade}» берегу — пропуск")
                    click_el(cube, "cube", "return_btn", "возврат (берегу)")
                    human.pause(CFG, 0.2, 0.38)
                    break
                # OCR — АВТОРИТЕТ (рамка врёт на высоких тирах). ДВА чтения: расходятся → не мержим
                # (страховка от единичного мисрида — «пугающая строка» рамка≠OCR).
                ocr = cube_grade_ocr(sct, cube)
                ocr2 = cube_grade_ocr(sct, cube)
                if ocr != ocr2:
                    log(f"{ru}: грейд не прочитался уверенно — пропуск (защита)")
                    click_el(cube, "cube", "return_btn", "возврат (грейд нестабилен)")
                    human.pause(CFG, 0.2, 0.38)
                    break
                if not ocr or ocr not in allowed:
                    log(f"{ru}: набор «{ocr or 'нечитаем'}» не в списке — пропуск")
                    click_el(cube, "cube", "return_btn", "возврат (не в списке)")
                    human.pause(CFG, 0.2, 0.38)
                    break
                log(f"{ru}: мержу набор «{ocr}»")
                if NOMERGE:
                    log(f"{ru}: набор «{ocr}» — NOMERGE, confirm пропущен")
                    click_el(cube, "cube", "return_btn", "возврат (nomerge)")
                    human.pause(CFG, 0.3, 0.5)
                    break
                click_el(cube, "cube", "confirm", f"CONFIRM 9/9 [{tp}] грейд={grade}")
                human.pause(CFG, 1.2, 1.7)
                dismiss_popups(sct)  # мерж триггерит серверный попап валидации — снять сразу
                # ВОЗВРАТ результата в инвентарь (требование: «бэкспейс»)
                _, d = detect(sct); cube = d.get("cube", cube)
                click_el(cube, "cube", "return_btn", "возврат результата")
                human.pause(CFG, 0.3, 0.5)
                total += 1
                landing_mark_stale()      # мерж сдвинул инвентарь → посадочную ячейку пересчитать
            elif n == 0:
                log(f"{ru}: предметов нет")
                break
            else:
                log(f"{ru}: набор неполный ({n}/9) — пропуск")
                click_el(cube, "cube", "return_btn", "возврат")
                human.pause(CFG, 0.2, 0.38)
                break
        if total >= MAX_MERGES_PER_TYPE:
            break
    return total


def _count_boxes_into_stats():
    """Обновить дашборд счётчиками сундуков из _LOG. СЧЁТ ведёт ТОЛЬКО фоновый наблюдатель
    (farm2._log_observer_loop, единственный писатель в _LOG под _lock). Здесь — ТОЛЬКО ЧТЕНИЕ
    текущих значений в STATS, БЕЗ повторного grab+observe.
    🔴 ПЕРЕЩЁТ-ФИКС: раньше тут звался `_LOG.poll()` (свой find_log+observe из ГЛАВНОГО потока) →
    ДВА независимо-таймированных снимка лога лезли в один сдвиг-алайнмент (наблюдатель + этот) →
    рассинхрон сдвига и завышенный счёт сундуков. Один писатель = корректный счёт."""
    if _LOG is not None:
        try:
            _stat(box_normal=_LOG.chests.get("normal", 0),
                  box_stage=_LOG.chests.get("stage_boss", 0),
                  box_act=_LOG.chests.get("act_boss", 0))
            return
        except Exception:
            pass
    if _boxes_mod is None:
        return
    try:
        result = _boxes_mod.count_boxes()
        _stat(box_normal=int(result.get("normal", 0)),
              box_stage=int(result.get("stage_boss", 0)),
              box_act=int(result.get("act_boss", 0)))
    except Exception:
        pass  # молча пропустить — детектор упал, фарм продолжает


def _tally_loot_stats(sct, hero):
    """Подсчитать ценное и материалы в инвентаре по данным рамочного скана.

    ВАЖНО: inv_probe.analyze() даёт ТОЛЬКО РАНГ по цвету рамки, НЕ ТИП предмета.
    Поэтому:
    - loot_valuable = количество ЗАНЯТЫХ слотов с рангом "red" (Бессмертный+
      по маппингу _RANK_RU). Включает весь Immortal+ независимо от типа
      (шмот, бижутерия, материалы высокого тира) — тип-сплит pending OCR.
    - loot_materials = количество слотов с рангом "uncommon" и выше (необычный+).
      БЕЗ фильтрации по типу — тип "material" определить по рамке невозможно.
      Реальные материалы среди них определяет только OCR (items.py); этот счётчик
      является ПРИБЛИЖЕНИЕМ (верхняя граница) до включения полного OCR-скана.
    Оба числа: grade-correct, type-split — documented approximation.
    """
    try:
        cells = grid_centers(hero, "hero", "inv_tl", "inv_br", INV["cols"], HERO_ROWS)
        s = CFG.get("grid_cell_capture_size", 44)
        valuable = 0
        materials = 0
        # rank -> tier index (соответствует _RANK_RU + items.RANK_TIERS)
        _immortal_ranks = {"red"}       # рамка "red" = Бессмертный+
        _material_ranks = {"uncommon", "rare", "legendary", "epic", "red"}  # необычный+
        for _, _, x, y in cells:
            img = np.array(sct.grab({"left": int(x - s / 2), "top": int(y - s / 2),
                                     "width": s, "height": s}))[:, :, :3]
            if float(img.mean()) < SLOT_FILL_THR:
                continue
            rank = ip.analyze(img).get("rank", "common")
            if rank in _immortal_ranks:
                valuable += 1
            if rank in _material_ranks:
                materials += 1
        _stat(loot_valuable=valuable, loot_materials=materials)
    except Exception:
        pass  # молча пропустить — скан упал, фарм продолжает


def do_chests():
    ck = CFG.get("chest_key", "space")
    # ПЕРЕД клавишей — убедиться, что игра поверху (иначе Пробел уходит мимо, сундук не открыт)
    if not DRY and not human.is_foreground(game_hwnd()):
        ensure_game_foreground(force=True)
    # Считаем накопленные сундуки ПЕРЕД открытием (после — они исчезнут)
    _count_boxes_into_stats()
    # ОДИН Пробел по умолчанию (после патча 15.06 сундуки авто-открываются; бёрст = палево).
    # Вызывается ТОЛЬКО по лог-событию сундука (farm2), а не по таймеру. taps можно поднять в конфиге.
    taps = max(1, int(CFG.get("chest", {}).get("taps", 1)))
    log(f"  [сундук] {ck} x{taps} (лог-событие)")
    for i in range(taps):
        if k():
            return
        if not DRY:
            human.key(ck, CFG)
        if i + 1 < taps:
            time.sleep(random.uniform(0.35, 0.8))


def cycle(idx):
    log(f"=== ЦИКЛ {idx} ===")
    _bot_cursor[0] = None  # сброс: до первого клика бота детект «юзер вернулся» выключен
    if not focus_game():
        log("  окно не найдено"); return
    with mss.mss() as sct:
        w, d = detect(sct)
        sc = next(iter(d.values()), {}).get("scale", "?") if d else "?"
        log(f"  открыто: {list(d.keys()) or '—'} масштаб≈{sc}")
        dbg_shot(f"c{idx}_0_start.png")
        clear_panels(sct)    # закрыть RUNES/STATUS/SETTINGS/PORTAL и т.п. — иначе перекроют куб/стэш
        dismiss_popups(sct)  # снять серверный попап валидации, иначе он блокирует весь цикл
        try:
            m = merge_all(sct)
            log(f"  [мерж] всего: {m}")
            if m:
                _stat(merges=STATS.get("merges", 0) + m)
        except Exception as e:
            log(f"  [мерж] ошибка: {e!r}")
        # Тэлли инвентаря: считаем ценное (Бессмертный+ по рамке) и материалы (необычный+).
        # Вызывается после мержа, пока HERO открыт. Сбой здесь не ломает цикл.
        try:
            _, _d2 = detect(sct)
            _hero2 = _d2.get("hero")
            if _hero2:
                _tally_loot_stats(sct, _hero2)
        except Exception:
            pass
        dbg_shot(f"c{idx}_1_after_merge.png")
        if k():
            return
        dismiss_popups(sct)  # попап мог всплыть после мержа — иначе Stash All уйдёт в no-op
        try:
            do_saveall_sort(sct)
        except Exception as e:
            log(f"  [save/sort] ошибка: {e!r}")
        dbg_shot(f"c{idx}_2_after_save.png")
        if k():
            return
        try:
            do_chests()
        except Exception as e:
            log(f"  [сундуки] ошибка: {e!r}")
    human.park()


def _hardstop():
    """Жёсткий стоп: F12 или кнопка СТОП панели (НЕ учитывает возврат курсора —
    в ожиданиях курсор и так твой)."""
    return human.kill_pressed(KKEY) or _stopped()


def run(mode="live", log_cb=None, stat_cb=None, stop_event=None):
    set_hooks(log_cb, stat_cb, stop_event)
    log("")
    log(f"###### TBH FARM (vision-dynamic) | {mode.upper()} | {'вежливый' if POLITE else 'RUDE'} ######")
    if not OFF:
        log("Нет offsets.json — сперва calibrate_all.py"); return False
    if not fw():
        log("Окно игры не найдено."); return False
    if mode != "dry":
        for i in (3, 2, 1):
            if _hardstop():
                log("Отмена."); _stat(phase="стоп", running=False); return True
            log(f"  старт через {i}…"); time.sleep(1)
    if POLITE and mode == "live":
        log(f"ВЕЖЛИВЫЙ: цикл стартует только если ты не трогал мышь/клаву >= {IDLE_START}с; "
            f"вернёшься — бот сразу уступит.")
    idx = 0
    _stat(phase="старт", running=True)
    if mode in ("once", "dry"):
        cycle(1)
    else:
        while True:
            if _hardstop():
                log("Стоп."); break
            # ВЕЖЛИВЫЙ старт-гейт: ждём, пока система простаивает (= юзер отошёл).
            if POLITE:
                waited = 0
                while idle.idle_seconds() < IDLE_START:
                    if _hardstop():
                        break
                    _stat(phase=f"жду простоя ({idle.idle_seconds():.0f}/{IDLE_START}с)")
                    time.sleep(1.0); waited += 1
                    if waited % 30 == 0:
                        log(f"  …жду простоя ({idle.idle_seconds():.0f}/{IDLE_START}с)")
                if _hardstop():
                    log("Стоп."); break
                log(f"  простой {idle.idle_seconds():.0f}с — работаю")
            idx += 1
            _stat(cycle=idx, phase="цикл")
            try:
                cycle(idx)
            except Exception as e:
                log(f"!!! цикл {idx} упал: {e!r}")
            if _hardstop():
                break
            iv = random.uniform(20, 45) if POLITE else random.uniform(40, 85)
            _stat(phase="пауза")
            slept = 0.0
            while slept < iv:
                if _hardstop():
                    break
                time.sleep(0.3); slept += 0.3
    _stat(phase="стоп")
    log("Готово.")
    return True


def main():
    mode = "dry" if "--dry" in sys.argv else ("once" if "--once" in sys.argv else ("live" if "--live" in sys.argv else None))
    if not mode:
        print("Режим: --dry / --once / --live  [--rude --nomerge --shots]"); sys.exit(1)
    run(mode)


if __name__ == "__main__":
    main()
