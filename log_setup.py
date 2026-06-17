"""log_setup.py — привести лог RECORDS в рабочее состояние (SCENARIO A2): найти → навести →
развернуть до 17 → закрепить. Лог — фундамент счёта.

Строки-пилюли лога НЕПРОЗРАЧНЫ (тёмный фон) → OCR чист. Находим лог ПО ТЕКСТУ строк-событий
(видны всегда, даже без фрейма управления). Фрейм (свернуть/развернуть/очистить/закрепить) виден
ТОЛЬКО при наведении → наводимся на регион лога, потом ищем баннер RECORDS и жмём кнопки.

Фаза 1 (этот коммит): БЕЗОПАСНАЯ — только детект (найти + посчитать строки + регион). Без кликов.
"""
import re

import numpy as np
import pytesseract
from PIL import Image

import logwatch


def _maxchan(frame):
    """Per-pixel max(R,G,B) → 8-bit grey. КЛЮЧ к OCR пиксель-арт лога: цветной текст (оранжевый
    Stage / фиолетовый Knight / зелёный Sorcerer / белый Obtained) на тёмной пилюле в обычной
    яркости (mean) сливается с фоном; max-канал делает ЛЮБОЙ цвет ярким, тёмный фон — тёмным.
    Доказано живьём: mean читает 6 строк мусора, maxchan — все 17 чисто."""
    a = np.asarray(frame)
    if a.ndim == 3 and a.shape[2] >= 3:
        return a[:, :, :3].max(axis=2).astype("uint8")
    return a.astype("uint8")


def _log_bands(frame):
    """Найти ВСЕ тёмные горизонтальные банды лога (x0,y0,x1,y1) ПО ВСЕЙ ВЫСОТЕ окна, сверху вниз.
    Лог бывает в двух видах: (1) ЗАКРЕПЛЁННОЕ многострочное окно RECORDS (один высокий тёмный
    стек, обычно верх-центр); (2) ПЛАВАЮЩАЯ пилюля последнего события (1 строка, ЛЮБОЕ место,
    часто низ-центр). Прежний `_log_region` сканил только верх 60% → ПРОПУСКАЛ нижнюю пилюлю
    (корень «n=0, не считается» в боевом виде). Теперь — все банды по высоте.
    Метод: ДОЛЯ тёмных пикселей в ЦЕНТРАЛЬНЫХ колонках (0.30–0.72W, мимо просвета браузера слева)
    > 0.5 → строка тёмного окна лога. КЛЮЧ: окно RECORDS = тёмный фон + тонкий яркий текст; по
    МЕДИАНЕ строка с текстом во всю ширину = «яркая» (текст заполняет центр) → строки текста выпадали,
    оставались тонкие сливеры 7px (баг: «Не удалось пройти Этап 2-7» не читался). Доля-тёмных собирает
    строку целиком (штрихи текста тонкие → большинство пикселей всё равно тёмные). Таскбар (>0.95H) режем."""
    a = np.asarray(frame)[:, :, :3]
    gray = a.mean(axis=2)
    H, W = gray.shape
    cl, cr = int(W * 0.30), int(W * 0.72)
    darkfrac = (gray[:, cl:cr] < 70).mean(axis=1)
    isdark = darkfrac > 0.5
    isdark[int(H * 0.95):] = False                # таскбар/нижняя кромка — не лог
    # GAP-толерантная группировка: яркая строка ТЕКСТА внутри одной строки лога рвала банду на
    # тонкие сливеры (h≈8-10), каждый = пол-высоты глифа → OCR пустой. Разрыв ≤4px не закрывает банду
    # (та же строка); >4px — отдельная строка лога. Чинит фрагментацию «Не удалось пройти Этап».
    bands, cur, gap = [], [], 0
    for y in range(H):
        if isdark[y]:
            cur.append(y); gap = 0
        elif cur:
            gap += 1
            if gap > 4:
                if cur[-1] - cur[0] >= 6:
                    bands.append((cur[0], cur[-1]))
                cur, gap = [], 0
            else:
                cur.append(y)
    if cur and cur[-1] - cur[0] >= 6:
        bands.append((cur[0], cur[-1]))
    out = []
    for y0, y1 in bands:
        cols = np.where((gray[y0 : y1 + 1] < 75).mean(axis=0) > 0.30)[0]
        if len(cols) < int(W * 0.10):             # слишком узко — не лог-бар
            continue
        out.append((int(cols.min()), y0, int(cols.max()), y1))
    return out


def _rows(frame, scale=1.4, max_channel=True):
    """OCR кадра по СТРОКАМ → список (text, box=(x0,y0,x1,y1)) в координатах кадра.
    max_channel=True (дефолт): max(R,G,B) grayscale — читает цветной лог (см. _maxchan)."""
    g = _maxchan(frame) if max_channel else np.asarray(frame)
    im = Image.fromarray(g)
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    d = pytesseract.image_to_data(im, lang="rus+eng", config="--psm 6",
                                  output_type=pytesseract.Output.DICT)
    rows = {}
    for i in range(len(d["text"])):
        t = (d["text"][i] or "").strip()
        if not t:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        r = rows.setdefault(key, {"w": [], "x0": 10 ** 9, "y0": 10 ** 9, "x1": 0, "y1": 0})
        r["w"].append(t)
        r["x0"] = min(r["x0"], x); r["y0"] = min(r["y0"], y)
        r["x1"] = max(r["x1"], x + w); r["y1"] = max(r["y1"], y + h)
    out = []
    for r in rows.values():
        box = (int(r["x0"] / scale), int(r["y0"] / scale),
               int(r["x1"] / scale), int(r["y1"] / scale))
        out.append((" ".join(r["w"]), box))
    return out


def _log_field():
    """(rx,ry) точки лога из records_calibration.json — центр зоны для кропа OCR. None если нет."""
    import json
    import os
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "records_calibration.json")
        v = json.load(open(p, encoding="utf-8")).get("log_field")
        return (v["rx"], v["ry"]) if v else None
    except Exception:
        return None


def find_log(frame=None):
    """Найти лог по тексту строк-событий. Вернуть dict:
      {n: число строк, box: (x0,y0,x1,y1) объединяющий бокс лог-строк, rows: [(text,box)…]}
    или {n:0} если строк лога не видно. Координаты — в кадре окна игры (отн. win.left/top).

    БЕЗ foreground-gate: игра — ВСЕГДА-ПОВЕРХ прозрачный оверлей, пилюли лога НЕПРОЗРАЧНЫ и
    рендерятся сверху всего → их пиксели грабятся в любой момент, даже когда фокус на панели
    бота/браузере. Просвет (текст браузера/VSCode сквозь прозрачные зоны) отсекает `_is_log_line`.
    Сегментация (`_log_bands`) находит банды лога ПО ВСЕЙ ВЫСОТЕ (закреплённое окно ИЛИ плавающая
    пилюля где угодно) → max-канал OCR каждой банды читает цветные строки."""
    if frame is None:
        w = logwatch.find_game_window()
        if not w:
            return {"n": 0}
        frame = logwatch.grab(w)
    # RapidOCR сам ДЕТЕКТИТ все текстовые строки (band-сегментация/мультимасштаб не нужны) и читает
    # кириллич. моделью. Просвет рабочего стола сквозь прозрачный оверлей отсекает `_is_log_line`.
    # СКОРОСТЬ: окно RECORDS в известной зоне (вокруг калибр. log_field) — OCR'им только её (≈3× быстрее,
    # меньше ложных строк). Нет калибровки → весь кадр.
    import ocr_engine
    arr = np.asarray(frame)
    H, W = arr.shape[:2]
    ox, oy = 0, 0
    lf = _log_field()
    if lf:
        cy = int(lf[1] * H)
        oy = max(0, cy - int(0.52 * H))                # окно тянется ВВЕРХ от точки клика
        y1 = min(H, cy + int(0.06 * H))
        ox = int(0.24 * W); x1 = int(0.74 * W)         # центр по X (мимо панели слева / героев справа)
        region = np.ascontiguousarray(arr[oy:y1, ox:x1])
    else:
        region = arr
    log_rows = [(t, (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy))
                for (t, b) in ocr_engine.read(region) if logwatch._is_log_line(t)]
    if not log_rows:
        return {"n": 0}
    log_rows.sort(key=lambda tb: tb[1][1])             # сверху вниз по y
    x0 = min(b[0] for _, b in log_rows); y0 = min(b[1] for _, b in log_rows)
    x1 = max(b[2] for _, b in log_rows); y1 = max(b[3] for _, b in log_rows)
    # frame отдаём наружу: наблюдателю нужен для ЦВЕТ-классификации типа сундука (chest_kind_by_color).
    return {"n": len(log_rows), "box": (x0, y0, x1, y1), "rows": log_rows, "frame": frame}


def reveal_banner(cfg):
    """Навести курсор на регион лога → проявить фрейм → найти баннер RECORDS (OCR 'RECORD').
    Вернуть {found, box(в кадре), win}. БЕЗ кликов. None-box если фрейм не проявился."""
    import time
    import human
    w = logwatch.find_game_window()
    if not w:
        return {"found": False}
    r = find_log()
    if not r.get("box"):
        return {"found": False, "no_log": True}
    x0, y0, x1, y1 = r["box"]
    cx, cy = w.left + (x0 + x1) // 2, w.top + (y0 + y1) // 2
    try:
        human.move_abs(cx, cy)
    except Exception:
        return {"found": False}
    time.sleep(0.9)
    frame = logwatch.grab(w)
    for tx, b in _rows(frame):
        if re.search(r"record", tx, re.I):
            return {"found": True, "box": b, "win": (w.left, w.top, w.width, w.height), "log_box": r["box"]}
    return {"found": False, "log_n": r["n"]}


def establish(cfg, log=lambda *_: None):
    """Попытка авто-привести лог к 17+закреплён. Возвращает число строк ПОСЛЕ попытки.
    Шаг 0: ЗАКРЫТЬ HERO/панели (ESC) — иначе HERO перекрывает лог (подтверждено: после закрытия лог
    высвобождается). БЕЗОПАСНО: кнопки «Развернуть/Закрепить» жмём ТОЛЬКО при откалиброванных
    смещениях (`records_banner.calibrated`). Иначе кликов нет → решает модалка/юзер.
    NB: открыть ЗАКРЫТЫЙ лог (когда панель не закреплена) этот метод НЕ умеет — только Настройки→Pin
    (хрупко, окно двигается) или юзер вручную (модалка)."""
    # СНАЧАЛА детект: если лог УЖЕ виден достаточно — НИЧЕГО не трогаем (ни ESC, ни клики — иначе
    # рискуем закрыть закреплённый лог, как и было). Это главное правило.
    r0 = find_log()
    n0 = r0.get("n", 0)
    if n0 == -1:
        return -1                                     # игра не поверх — не проверить, ничего не трогаем
    if n0 >= 8:
        return n0                                     # уже развёрнут — НЕ трогаем (не кликаем rec_expand повторно)
    # лог МАЛ (1-несколько строк). Авто-РАЗВОРОТ (rec_expand) при включённом флаге + калибровке.
    # Разворот клеит больше строк → события держатся дольше → счёт ловит и сундуки, не только последнее.
    if cfg.get("policy", {}).get("records_autoopen"):
        try:
            import records_ctl
            if records_ctl._cal().get("game_settings"):
                records_ctl.ensure_ready(cfg, log=log, expand=True)
                return find_log().get("n", n0)
        except Exception as e:
            log(f"[establish] {e!r}")
    return n0                                          # без авторазворота — считаем от видимого (1 строка ок)


def state_name(n):
    """Грубая категория состояния лога по числу видимых строк (SCENARIO: 0/1/5/17)."""
    if n <= 0:
        return "0 — не видно"
    if n == 1:
        return "1 — одна строка (мини-окно или HERO перекрыл)"
    if n <= 8:
        return "~5 — средний размер"
    return "~17 — развёрнут"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    w = logwatch.find_game_window()
    print("окно игры:", None if not w else (w.left, w.top, w.width, w.height))
    r = find_log()
    print("найдено строк лога:", r["n"], "|", state_name(r["n"]))
    if r.get("box"):
        print("регион лога (в кадре):", r["box"])
        for t, b in r["rows"][:6]:
            print("   ", b, t[:50])
