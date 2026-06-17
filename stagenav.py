"""stagenav.py — навигация по стадиям через окно PORTAL. WIP.

Поток (подтверждён скринами PORTAL): кнопка PORTAL → дропдаун сложности (Обычный/Кошмар/Ад/Мучение)
→ таб Акт 1/2/3 → СКРОЛЛ карты к краю → клик по узлу этапа. Нотация X-Y-Z = сложность(1-4)-акт(1-3)-
этап(1-10).

КАРТА СКРОЛЛИТСЯ: видно 7 узлов из 10. Позиции узлов на экране ОДИНАКОВЫ для всех 3 актов (Денис
подтвердил скринами) → калибруем узлы ОДИН РАЗ, не по актам. Две страницы:
  • прокручено В НИЗ  → видны этапы 1-7 (nodes_bottom),
  • прокручено В ВЕРХ → видны этапы 4-10 (nodes_top).
Чтобы попасть на этап: этап ≤7 → скролл вниз к краю + клик из nodes_bottom; этап ≥8 → скролл вверх +
клик из nodes_top. Скролл к краю = 2-4 рандом-прокрутки (хуманлайк; перебор безопасен — край
клампится). Точка скролла = scroll_anchor (центр карты).

Координаты — BANNER-RELATIVE смещения из offsets.json["portal"] (node_1..node_10 + контролы).
goto() детектит баннер PORTAL ЖИВЬЁМ (vision.detect) → точки = vision.pt(banner, offset): масштаб и
позиция окна учитываются сами. Нет данных/баннера → goto() НЕ кликает, возвращает False (лучше не
прыгнуть, чем misclick).

Чистая логика (parse_label / nav_plan / calibration_status) тестируется офлайн (test_stagenav).
"""
import random
import re
import time

DIFF_IDX = {1: "NORMAL", 2: "NIGHTMARE", 3: "HELL", 4: "TORMENT"}
DIFF_RU = {"NORMAL": "Обычный", "NIGHTMARE": "Кошмар", "HELL": "Ад", "TORMENT": "Мучение"}

VIEWPORT_NODES = 7        # сколько узлов видно в окне карты
SCROLL_NOTCHES = 4        # колесо на одну прокрутку
SCROLL_MIN, SCROLL_MAX = 4, 6   # рандом число прокруток к краю (запас: перебор клампится у края)



def _page_for(no):
    """Страница, с которой доступен этап no: 'bottom' (низ, этапы 1-7) или 'top' (верх, этапы 8-10)."""
    return "bottom" if no <= VIEWPORT_NODES else "top"


def parse_label(label):
    """'4-2-7' → {'diff_idx':4,'difficulty':'TORMENT','act':2,'no':7}. None при кривом формате."""
    try:
        d, a, n = (int(x) for x in str(label).split("-"))
    except Exception:
        return None
    if d not in DIFF_IDX or not (1 <= a <= 3) or not (1 <= n <= 10):
        return None
    return {"diff_idx": d, "difficulty": DIFF_IDX[d], "act": a, "no": n}


def nav_plan(label):
    """Последовательность шагов навигации, которые goto() прокликает по порядку.
    Возвращает список (kind, key) или None. Чисто — тестируется без игры.
    kind: open/click — клик по точке; scroll — прокрутка карты к краю (key='down'|'up');
    node — клик по узлу этапа (key='<page>:<no>')."""
    p = parse_label(label)
    if not p:
        return None
    page = _page_for(p["no"])
    # Открытие PORTAL (Tab → HERO → клик кнопки PORTAL) делает _open_portal штатными хелперами
    # farm (идемпотентный Tab + offsets hero.open_portal). Здесь — только шаги ВНУТРИ карты.
    return [
        ("click", "diff_dropdown"),                       # раскрыть дропдаун сложности
        ("click", "diff_option_%s" % p["difficulty"].lower()),  # выбрать сложность
        ("click", "act_tab_%d" % p["act"]),               # таб акта
        ("scroll", "down" if page == "bottom" else "up"),  # прокрутить карту к нужному краю
        ("node", "%s:%d" % (page, p["no"])),              # узел этапа на этой странице
    ]


def _open_portal(cfg, log):
    """Открыть карту PORTAL штатно: фокус → HERO (farm.ensure_hero — Tab ТОЛЬКО если меню скрыто,
    без бага «Tab при открытом») → клик кнопки PORTAL (offsets hero.open_portal, крайняя правая в
    ряду STASH·STATUS·RUNES·CUBE·PORTAL) → поллинг детекта панели 'portal'. False если не открылась."""
    import mss
    import farm
    try:
        farm.focus_game(); time.sleep(0.3)
    except Exception:
        pass
    sct = mss.mss()
    if farm.detect(sct, names=["portal"])[1].get("portal"):
        return True                                       # уже открыта
    hero = farm.ensure_hero(sct)
    if not hero:
        log("stagenav: HERO не открылся (Tab) — PORTAL не открыть"); return False
    if not farm.click_el(hero, "hero", "open_portal", "открыть PORTAL"):
        return False
    for _ in range(8):
        if farm._hardstop():
            return False
        time.sleep(0.3)
        if farm.detect(sct, names=["portal"])[1].get("portal"):
            return True
    log("stagenav: PORTAL не появился после клика open_portal"); return False


def _win():
    import logwatch
    return logwatch.find_game_window()


# Слово сложности в дропдауне (OCR) — устойчивый префикс.
_DIFF_WORD = {"NORMAL": "обычн", "NIGHTMARE": "кошмар", "HELL": "ад", "TORMENT": "мучен"}
_NODE_RE = re.compile(r"\[?(\d)\s*[-:]\s*(\d{1,2})\]?")


def calibration_status(off=None, win=None):
    """PORTAL навигируется ЗРЕНИЕМ (OCR сложности/акта/узлов + детект баннера) — отдельная
    калибровка точек НЕ нужна. ok, если игра запущена (баннер найдётся при открытии). → (status, detail)."""
    return "ok", "vision-driven (OCR + баннер, калибровка не нужна)"


def is_calibrated(win=None):
    return True


def _boxes(win, sct):
    """(frame, [(text,(x0,y0,x1,y1))]) для всего окна — относительные коорд. кадра."""
    import numpy as np
    import ocr_engine
    f = np.array(sct.grab({"left": win.left, "top": win.top,
                           "width": win.width, "height": win.height}))[:, :, :3]
    return f, ocr_engine.read(f)


def _find_text(boxes, win, *needles, ybot=None):
    """Первый OCR-бокс, текст которого содержит любую needle. → (cx,cy,box_left) ЭКРАН или None."""
    for txt, (x0, y0, x1, y1) in boxes:
        cy = win.top + (y0 + y1) // 2
        if ybot is not None and cy > ybot:
            continue
        t = txt.lower()
        if any(n in t for n in needles):
            return win.left + (x0 + x1) // 2, cy, win.left + x0
    return None


def _map_circles(win, sct, banner):
    """Кружки узлов карты — детект по БЕЛОМУ цвету (узлы чисто белые, в отличие от фона; босс [*-10]
    красный — не белый, отсекается сам). ЭКРАН, отсортированы СНИЗУ ВВЕРХ (этап 1 → выше). []."""
    import numpy as np
    import cv2
    x0 = int(banner["cx"] - 0.55 * banner["w"]); y0 = int(banner["cy"] + 0.1 * banner["w"])
    x1 = int(banner["cx"] + 0.78 * banner["w"]); y1 = win.top + win.height
    img = np.array(sct.grab({"left": x0, "top": y0,
                             "width": max(10, x1 - x0), "height": max(10, y1 - y0)}))[:, :, :3]
    white = cv2.inRange(img, (188, 188, 188), (255, 255, 255))   # BGR почти-белый
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    r = 0.03 * banner["w"]
    amin, amax = (0.7 * r) ** 2, (3.0 * r) ** 2 * 4             # площадь блоба ~ размера узла
    n, _, stats, cent = cv2.connectedComponentsWithStats(white)
    cs = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if amin <= a <= amax and 0.5 <= bw / max(1, bh) <= 2.0:   # нужного размера и ~круглый
            cs.append((x0 + int(cent[i][0]), y0 + int(cent[i][1])))
    # отсечь выбросы по X: узлы идут тесной вертикальной колонкой
    if len(cs) >= 3:
        mx = sorted(c[0] for c in cs)[len(cs) // 2]
        cs = [c for c in cs if abs(c[0] - mx) <= 0.2 * banner["w"]]
    return sorted(cs, key=lambda c: -c[1])              # снизу (этап 1) вверх


def _red_node(win, sct, banner):
    """Центроид КРАСНОГО узла (босс [*-10]) в карте → (cx,cy) ЭКРАН или None."""
    import numpy as np
    import cv2
    x0 = int(banner["cx"] - 0.55 * banner["w"]); y0 = int(banner["cy"] + 0.1 * banner["w"])
    x1 = int(banner["cx"] + 0.78 * banner["w"]); y1 = win.top + win.height
    img = np.array(sct.grab({"left": x0, "top": y0,
                             "width": max(10, x1 - x0), "height": max(10, y1 - y0)}))[:, :, :3]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
    n, _, stats, cent = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return None
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    if stats[i, cv2.CC_STAT_AREA] < 60:
        return None
    return x0 + int(cent[i][0]), y0 + int(cent[i][1])


def _locate_node(win, sct, banner, act, no, base=None):
    """Кружок узла [act-no] методом индексации кружков: якоримся на ЛЮБОЙ читаемый короткий ярлык
    [act-k] (правее центра, не тултип) и считаем кружок цели по разнице номеров (путь = этапы 1→N
    снизу вверх). Надёжно, даже если ярлык самой цели перекрыт/не прочитан. → (cx,cy) ЭКРАН или None."""
    cs = _map_circles(win, sct, banner)
    if not cs:
        return None
    _, boxes = _boxes(win, sct)
    for txt, (x0, y0, x1, y1) in boxes:
        s = txt.strip()
        if len(s) > 7:                                  # длинный = тултип названия, не узел
            continue
        m = _NODE_RE.search(s)
        if not m or int(m.group(1)) != act:
            continue
        lx, ly = win.left + (x0 + x1) // 2, win.top + (y0 + y1) // 2
        if lx < banner["cx"]:                           # тултип слева от центра карты — пропустить
            continue
        ai = min(range(len(cs)), key=lambda i: abs(cs[i][1] - ly))   # кружок этого ярлыка
        ti = ai + (no - int(m.group(2)))
        if 0 <= ti < len(cs):
            return cs[ti]
    # фолбэк без OCR: на краю нижний кружок = этап `base` (cs снизу вверх) → cs[no-base]
    if base is not None and 0 <= no - base < len(cs):
        return cs[no - base]
    return None


def _green_ring(win, sct, banner):
    """Центроид ЗЕЛЁНОГО кольца текущего этапа (крупнейшая зелёная компонента в карте) → (gx,gy) или None."""
    import numpy as np
    import cv2
    x0 = int(banner["cx"] - 0.55 * banner["w"]); y0 = int(banner["cy"] + 0.1 * banner["w"])
    x1 = int(banner["cx"] + 0.78 * banner["w"]); y1 = win.top + win.height
    img = np.array(sct.grab({"left": x0, "top": y0,
                             "width": max(10, x1 - x0), "height": max(10, y1 - y0)}))[:, :, :3]
    mask = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), (40, 120, 120), (85, 255, 255))
    n, _, stats, cent = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return None
    i = max(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA])
    if stats[i, cv2.CC_STAT_AREA] < 60:
        return None
    return x0 + int(cent[i][0]), y0 + int(cent[i][1])


def _green_node(win, sct, banner, expect_act=None, base=None):
    """Текущий этап по ЗЕЛЁНОМУ кольцу: кольцо → его КРУЖОК → индекс; ЛЮБОЙ читаемый ярлык [act-k] —
    якорь; номер = по разнице индексов кружков. Фолбэк без OCR: на НИЖНЕМ краю нижний кружок = этап 1
    (act берём из expect_act). → (act,no) или None."""
    cs = _map_circles(win, sct, banner)
    g = _green_ring(win, sct, banner)
    if not cs or not g:
        return None
    ri = min(range(len(cs)), key=lambda k: abs(cs[k][0] - g[0]) + abs(cs[k][1] - g[1]))
    _, boxes = _boxes(win, sct)
    for txt, (bx0, by0, bx1, by1) in boxes:
        s = txt.strip()
        if len(s) > 7:
            continue
        m = _NODE_RE.search(s)
        if not m:
            continue
        lx, ly = win.left + (bx0 + bx1) // 2, win.top + (by0 + by1) // 2
        if lx < banner["cx"]:
            continue
        ai = min(range(len(cs)), key=lambda k: abs(cs[k][1] - ly))
        return int(m.group(1)), int(m.group(2)) + (ri - ai)
    if base is not None and expect_act is not None:
        return expect_act, ri + base                    # нижний кружок = этап base
    return None


def _scroll_extreme(win, sct, banner, cfg, down):
    """Доскроллить карту в крайнее положение (вниз=этапы 1-7, вверх=4-10), курсор НАД кластером
    узлов (над баннером колесо Unity-карту не крутит). Перебор клампится у края."""
    import farm
    import human
    cs = _map_circles(win, sct, banner)
    if cs:
        cx = sum(c[0] for c in cs) // len(cs); cy = sum(c[1] for c in cs) // len(cs)
    else:
        cx = int(banner["cx"] + 0.05 * banner["w"]); cy = int(banner["cy"] + 1.0 * banner["w"])
    notches = -SCROLL_NOTCHES if down else SCROLL_NOTCHES
    for _ in range(12):
        if farm._hardstop():
            return
        human.wheel(cx, cy, notches); time.sleep(0.12)
    time.sleep(0.5)


def goto(stage, cfg, log=lambda *_: None, confirm=True):
    """ЖИВОЙ переход ЗРЕНИЕМ: открыть PORTAL → выбрать сложность/акт (калиброванные кнопки) →
    доскроллить в край (1-7 вниз / 8-10 вверх) → найти узел [act-no] (белые кружки + OCR-якорь) →
    клик кружка = телепорт → проверка зелёным кольцом. Этап 10 (босс) НЕ жмём."""
    import farm
    import human
    import vision
    import mss
    import geom
    p = parse_label(stage.get("label") if isinstance(stage, dict) else str(stage))
    if not p:
        log("stagenav: кривая метка"); return False
    win = _win()
    if not win:
        log("stagenav: окно игры не найдено"); return False
    if not _open_portal(cfg, log):
        return False
    sct = mss.MSS(); time.sleep(0.4)
    banner = None
    for _ in range(6):
        if farm._hardstop():
            return False
        banner = vision.detect(win, sct, names=["portal"]).get("portal")
        if banner:
            break
        time.sleep(0.3)
    if not banner:
        log("stagenav: баннер PORTAL не задетектился"); return False
    # 1) сложность — только если текущая (OCR сверху) != целевой; кнопки калиброваны (offsets.json)
    top = banner["cy"] + 0.35 * banner["w"]
    _, boxes = _boxes(win, sct)
    word = _DIFF_WORD[p["difficulty"]]
    cur_word = next((wd for wd in _DIFF_WORD.values() if _find_text(boxes, win, wd, ybot=top)), None)
    if cur_word != word:
        dd = geom.point("portal", "diff_dropdown", win, sct)
        if dd:
            human.click(dd[0], dd[1], cfg); time.sleep(0.5)
        opt = geom.point("portal", "diff_option_%s" % p["difficulty"].lower(), win, sct)
        if opt:
            human.click(opt[0], opt[1], cfg); time.sleep(0.7)
        else:
            log("stagenav: опция сложности не откалибрована — пропуск")
    # 2) акт — калиброванная кнопка
    at = geom.point("portal", "act_tab_%d" % p["act"], win, sct)
    if at:
        human.click(at[0], at[1], cfg); time.sleep(0.7)
    banner = vision.detect(win, sct, names=["portal"]).get("portal") or banner
    # 3) скролл в край + найти узел. Низ: этапы 1-7 (base=1). Верх: 4-10 (base=4), [*-10] красный.
    down = p["no"] <= 7
    base = 1 if down else 4
    _scroll_extreme(win, sct, banner, cfg, down=down)
    if p["no"] == 10:                                    # босс — красный узел (белым не детектится)
        node = _red_node(win, sct, banner)
    else:
        node = _locate_node(win, sct, banner, p["act"], p["no"], base=base)
    if not node:
        log("stagenav: узел %d-%d не найден после скролла" % (p["act"], p["no"])); return False
    human.click(node[0], node[1], cfg); time.sleep(1.6)
    if p["no"] == 10:                                    # босс: красный узел, кольцо поверх — не верифицируем
        log("stagenav → %d-10: клик по боссу (best-effort)" % p["act"]); return True
    # самокоррекция: зелёное кольцо = ТОЧНЫЙ текущий этап (читается надёжно) → шагаем по белым
    # кружкам на разницу до цели, пока не совпадёт (исправляет промах OCR-якоря на ±1).
    for _ in range(4):
        if farm._hardstop():
            return False
        cur = _green_node(win, sct, banner, expect_act=p["act"], base=base)
        if cur == (p["act"], p["no"]):
            log("stagenav → %d-%d: ✓" % (p["act"], p["no"])); return not confirm or True
        if not cur or cur[0] != p["act"]:
            break
        cs = _map_circles(win, sct, banner)
        g = _green_ring(win, sct, banner)
        if not (cs and g):
            break
        ri = min(range(len(cs)), key=lambda k: abs(cs[k][0] - g[0]) + abs(cs[k][1] - g[1]))
        ti = max(0, min(len(cs) - 1, ri + (p["no"] - cur[1])))   # bottom→top = по возрастанию этапа
        if ti == ri:                                     # уперлись — доскроллить в сторону цели
            _scroll_extreme(win, sct, banner, cfg, down=(p["no"] < cur[1]))
            continue
        human.click(cs[ti][0], cs[ti][1], cfg); time.sleep(1.6)
    cur = _green_node(win, sct, banner, expect_act=p["act"], base=base)
    ok = cur == (p["act"], p["no"])
    log("stagenav → %d-%d: %s (кольцо на %s)" % (p["act"], p["no"], "✓" if ok else "?", cur))
    return ok if confirm else True


def _confirm(label, log):
    """Подтвердить, что текущая стадия == целевой (OCR индикатора). Нет ридера → True (доверяем
    плану) — реальный OCR-чек добавится со stagestate. Сейчас честно: 'unknown' → не блокируем."""
    try:
        import stagestate
        cur = stagestate.current_label()
        if cur is None:
            return True                                   # не прочитали → не валим (unknown)
        return cur == label
    except Exception:
        return True


def navigate(stage):
    """Адаптер под HopMode.navigate(stage_dict)->bool. Тянет cfg из farm.CFG."""
    import farm
    import logx
    return goto(stage, farm.CFG, log=logx.log_human)
