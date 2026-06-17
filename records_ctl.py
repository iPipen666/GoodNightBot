"""records_ctl.py — управление игровым окном лога RECORDS по калибровке.

Источник координат: records_calibration.json (доли окна игры rx,ry, см. calibrate_records.py).
Игра должна быть ПОВЕРХ (в цикле фарма так и есть). Все клики — через human-слой (джиттер).

Задача: на старте сессии гарантировать, что лог RECORDS ОТКРЫТ и читается (иначе счёт сундуков
= 0). Если закрыт — открыть через игровые Settings → General → тумблер лога, затем развернуть
на максимум (Expand) для большего числа строк под OCR.

Путь открытия: game_settings (шестерёнка) → log_open (тумблер «Pin Log Window» в General) → Esc.
"""
import json
import os
import time

import logwatch

HERE = os.path.dirname(os.path.abspath(__file__))
_CAL_PATH = os.path.join(HERE, "records_calibration.json")


def _cal():
    try:
        return json.load(open(_CAL_PATH, encoding="utf-8"))
    except Exception:
        return {}


def _screen(key, cal=None):
    """Экранные координаты точки калибровки (rx,ry → пиксели через окно игры). None если нет."""
    cal = cal if cal is not None else _cal()
    v = cal.get(key)
    w = logwatch.find_game_window()
    if not v or not w:
        return None
    return int(w.left + v["rx"] * w.width), int(w.top + v["ry"] * w.height)


def _click(pt, cfg):
    import human
    human.click(pt[0], pt[1], cfg)


def is_ready():
    """Лог открыт и пишет события?"""
    return logwatch.records_signal() > 0


def _checkbox_on(sct, x, y, size=24):
    """Чекбокс игры включён? Включённый = зелёная галка; выключенный = пустой тёмный бокс.
    Читаем зелёные пиксели в окне size×size вокруг точки. mss grab = BGRA → канал G = [...,1]."""
    import numpy as np
    h = size // 2
    img = np.array(sct.grab({"left": int(x - h), "top": int(y - h),
                             "width": size, "height": size}))[:, :, :3]
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    green = ((g > 90) & (g > r + 25) & (g > b + 25)).sum()
    return green > size * size * 0.05            # ≥5% зелёных = галка стоит


def pin_log_via_settings(cfg, sct, log=lambda *_: None):
    """ЗАКРЕПИТЬ окно лога через игровые Settings, vision-методом (баннер-relative офсеты из
    offsets.json — едут всем юзерам, без дробной калибровки). Поток: focus → (Tab открыть HERO,
    если ни HERO ни Settings не открыты) → клик шестерёнки `hero.open_settings` → детект баннера
    SETTINGS → читаем чекбокс `settings.pin_log`: стоит — закрыть; снят — кликнуть → закрыть.
    Идемпотентно (не снимает уже стоящую галку). Безопасно: нет офсетов → False без слепых кликов."""
    import vision
    import farm
    need = ("open_settings" in farm.OFF.get("hero", {})
            and "pin_log" in farm.OFF.get("settings", {}))
    if not need:
        log("⚠ нет офсетов hero.open_settings / settings.pin_log — запусти calibrate_all.py (фазы 4-5)")
        return False
    farm.focus_game(); time.sleep(0.4)
    _, d = farm.detect(sct)
    if "settings" not in d:
        if "hero" not in d:                       # игровой UI закрыт → Tab открывает HERO
            farm.press_tab(); time.sleep(0.6)
            _, d = farm.detect(sct)
        if "hero" in d:
            farm.click_el(d["hero"], "hero", "open_settings", "открыть Настройки")
            time.sleep(0.8)
            _, d = farm.detect(sct)
    if "settings" not in d:
        log("⚠ панель Settings не открылась (баннер не найден)")
        return False
    sp = d["settings"]
    if "tab_basic" in farm.OFF.get("settings", {}):    # на всякий — открыть вкладку «Основные»
        farm.click_el(sp, "settings", "tab_basic", "вкладка Основные"); time.sleep(0.3)
        _, d = farm.detect(sct); sp = d.get("settings", sp)
    cbx, cby = vision.pt(sp, *farm.OFF["settings"]["pin_log"])
    if _checkbox_on(sct, cbx, cby):
        log("лог уже закреплён ✓")
    else:
        farm.click_el(sp, "settings", "pin_log", "Закрепить окно лога")
        time.sleep(0.4)
        log("поставил «Закрепить окно лога»")
    if "close" in farm.OFF.get("settings", {}):
        farm.click_el(sp, "settings", "close", "закрыть Настройки")
    else:
        import human
        human.key("esc", cfg)
    time.sleep(0.5)
    return True


def ensure_ready(cfg, log=lambda *_: None, expand=True):
    """Гарантировать читаемый лог. Закрыт → ЗАКРЕПИТЬ через Settings (vision). Вернуть (ok, did_open).
    Безопасно: нет офсетов настроек → предупреждение, без слепых кликов."""
    if is_ready():
        if expand:
            _expand(cfg)
        return True, False
    import mss
    with mss.mss() as sct:
        pin_log_via_settings(cfg, sct, log=log)
    ok = is_ready()
    if ok and expand:
        _expand(cfg)
    log("лог RECORDS закреплён ✓" if ok else "⚠ не удалось закрепить лог автоматически")
    return ok, True


_POPUP_KW = ("validation", "server item", "deleted item", "not held on the server",
             "cleaned up")


def close_validation_popup(cfg, txt=None):
    """Серверный попап «SERVER ITEM VALIDATION RESULTS» — детект по OCR-словам + клик Confirm по
    калибровке (центрированный модал, rx≈0.5). Надёжный дубль к template-матчу farm.dismiss_popups.
    Возвращает True, если попап найден и Confirm нажат."""
    if txt is None:
        win = logwatch.find_game_window()
        if not win:
            return False
        try:
            txt = logwatch.ocr(logwatch.grab(win))
        except Exception:
            return False
    low = (txt or "").lower()
    if not any(k in low for k in _POPUP_KW):
        return False
    pt = _screen("popup_confirm")
    if not pt:
        return False
    _click(pt, cfg)
    return True


def poll_loop(stop_check, interval=2.5):
    """Фоновый опрос игрового лога (ТОЛЬКО OCR, без кликов — не гонится с кликами фарма).
    Держит logwatch.LogWatcher (farm._LOG) в актуальном состоянии, ловя события ДО скролла.
    Запускается демон-потоком из farm2.run; останавливается по stop_check()."""
    import farm
    lw = getattr(farm, "_LOG", None)
    if lw is None:
        return
    while True:
        try:
            if stop_check():
                return
            if not logwatch.is_game_foreground():    # игра не поверх → OCR схватит чужой текст, пропуск
                for _ in range(int(interval / 0.25) + 1):
                    if stop_check():
                        return
                    time.sleep(0.25)
                continue
            lw.poll()                 # grab+OCR+ingest накопленных событий (сундуки/дроп/стадия)
            farm._stat(box_normal=lw.chests.get("normal", 0),     # живое обновление дашборда
                       box_stage=lw.chests.get("stage_boss", 0),
                       box_act=lw.chests.get("act_boss", 0))
        except Exception:
            pass
        # дробим сон, чтобы быстро реагировать на стоп
        for _ in range(int(interval / 0.25) + 1):
            if stop_check():
                return
            time.sleep(0.25)


def reveal_log(cfg, sct=None, log=lambda *_: None):
    """КЛИКНУТЬ в поле лога (калибр. `log_field` в records_calibration), чтобы проявить окно RECORDS.
    Unity НЕ реагирует надёжно на программный ховер (move_abs) — нужен реальный клик (Денис, живьём
    2026-06-16). Клик по месту нижней строки лога вызывает рамку RECORDS + строки. Без калибровки →
    no-op (False). Безопасно: точка = пустое поле лога, не кнопка/предмет."""
    cal = _cal()
    lf = cal.get("log_field")
    w = logwatch.find_game_window()
    if not lf or not w:
        if not lf:
            log("⚠ нет калибровки log_field — запусти calibrate_logfield.py (1 клик по нижней строке лога)")
        return False
    x = int(w.left + lf["rx"] * w.width)
    y = int(w.top + lf["ry"] * w.height)
    import human
    try:
        import farm
        farm.focus_game(); time.sleep(0.3)
    except Exception:
        pass
    human.click(x, y, cfg); time.sleep(0.5)         # реальный клик → проявить RECORDS
    return True


def collapse_for_observe(cfg, sct, log=lambda *_: None):
    """Свернуть инвентарь/тайник/куб и прочие оверлеи, чтобы панель RECORDS была не перекрыта —
    чистый снимок лога под сдвиг-счёт. ESC закрывает верхнее открытое окно (на пустом — no-op,
    проверено). Бьём короткую серию, выходя как только hero/stash/cube не видно."""
    import farm
    try:
        farm.clear_panels(sct)                        # runes/status/settings/portal/tradeship
    except Exception:
        pass
    import human
    for _ in range(4):
        try:
            _, d = farm.detect(sct)
        except Exception:
            return
        if not any(k in d for k in ("hero", "stash", "cube")):
            return                                    # инвентарь/тайник/куб закрыты → лог открыт
        human.key("esc", cfg)
        time.sleep(0.4)


def reveal_line(cfg, screen_y, dwell=2.8):
    """Навести курсор на строку лога (по экранному Y) и дождаться прокрутки маркизы, склеивая
    фрагменты OCR в полную строку (таймстемп + '(Моб)' + имя). Требует калибровку полосы строк
    лога (records_calibration 'log_row_x'); НЕТ калибровки → возвращает '' (деградация без краша,
    моб всё равно дочитывается пассивно по маркизе в observe._enrich)."""
    cal = _cal()
    row_x = cal.get("log_row_x")
    w = logwatch.find_game_window()
    if not row_x or not w:
        return ""
    import human
    x = int(w.left + row_x["rx"] * w.width)
    try:
        human.move_abs(x, int(screen_y))
    except Exception:
        return ""
    band_h = int(cal.get("log_row_h", {}).get("px", 26))
    best = ""
    t_end = time.time() + dwell
    while time.time() < t_end:
        try:
            frame = logwatch.grab(w)
            top = max(0, int(screen_y - w.top - band_h // 2))
            strip = frame[top:top + band_h, :]
            txt = logwatch.ocr(strip, scale=1.6).strip()
        except Exception:
            txt = ""
        if len(txt) > len(best):
            best = txt
        time.sleep(0.4)
    return best


def _expand(cfg):
    """Развернуть панель RECORDS на максимум (больше строк под OCR). 3 размера — жмём Expand
    дважды, перебор безвреден (на макс размере кнопка просто не растит дальше)."""
    ex = _screen("rec_expand")
    if not ex:
        return
    try:
        _click(ex, cfg); time.sleep(0.2)
        _click(ex, cfg); time.sleep(0.2)
    except Exception:
        pass


# ── АВТОРАЗВОРОТ лога через matchTemplate кнопки ⛶ (банннер RECORDS появляется на наведение) ──
# Прозрачный оверлей: фон за игрой произвольный (браузер/чат/тёмная сцена) → детект баннера по
# цвету/OCR ненадёжен. Кнопка ⛶ — НЕПРОЗРАЧНЫЙ пиксель-арт игры → matchTemplate её находит устойчиво
# к фону. Шаблоны: templates/records_expand.png (снят живьём, self-match 1.0). Порог высокий —
# ниже НЕ жмём (без слепых кликов по мусору фона). Гейт: policy.records_autoexpand (дефолт OFF до
# живой верификации — чтобы не misclick'нуть в боевом цикле).
_TPL_CACHE = {}
_MATCH_MIN = 0.70                # порог уверенности matchTemplate (true≈1.0, false≤0.45 — запас большой)


def _diag(msg):
    """Диагностика авторазворота в отдельный файл (expand_diag.log) — понять, где цепочка рвётся
    (нет пилюли / низкий score / нет роста), не спамя панель. Дёшево, append-only."""
    try:
        p = os.path.join(HERE, "expand_diag.log")
        import time as _t
        with open(p, "a", encoding="utf-8") as f:
            f.write(_t.strftime("%H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def _tpl(name):
    if name not in _TPL_CACHE:
        import cv2
        import numpy as np
        from PIL import Image
        p = os.path.join(HERE, "templates", name)
        _TPL_CACHE[name] = cv2.cvtColor(np.asarray(Image.open(p).convert("RGB")),
                                        cv2.COLOR_RGB2GRAY).astype("float32")
    return _TPL_CACHE[name]


def _match(frame, tpl_name, region=None):
    """Мультимасштаб matchTemplate → (score, cx, cy) центр в координатах КАДРА, или (0,None,None).
    region=(rx0,ry0,rx1,ry1) ограничивает поиск (вокруг пилюли) → убирает ложные матчи по просвету
    фона за прозрачным оверлеем и ускоряет."""
    import cv2
    import numpy as np
    tpl = _tpl(tpl_name)
    full = cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2GRAY).astype("float32")
    ox, oy = 0, 0
    if region:
        rx0, ry0, rx1, ry1 = region
        rx0 = max(0, rx0); ry0 = max(0, ry0)
        rx1 = min(full.shape[1], rx1); ry1 = min(full.shape[0], ry1)
        g = full[ry0:ry1, rx0:rx1]; ox, oy = rx0, ry0
    else:
        g = full
    best = (0.0, None, None)
    for sc in (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.35):
        t = cv2.resize(tpl, (max(8, int(tpl.shape[1] * sc)), max(8, int(tpl.shape[0] * sc))))
        if t.shape[0] >= g.shape[0] or t.shape[1] >= g.shape[1]:
            continue
        res = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, ml = cv2.minMaxLoc(res)
        if mx > best[0]:
            best = (mx, ox + ml[0] + t.shape[1] // 2, oy + ml[1] + t.shape[0] // 2)
    return best


def pin_and_expand(cfg, log=lambda *_: None):
    """Развернуть лог RECORDS до многострочного (стабильный счёт). Цепочка: find_log находит
    пилюлю → наводим курсор (проявляем рамку RECORDS) → matchTemplate кнопки ⛶ → клик ×2 (до макс).
    Достаточно ОДНОГО успеха: развёрнутое окно держится → дальнейшее чтение чистое. БЕЗОПАСНО:
    пилюлю не видно ИЛИ score < порога → НЕ жмём (no-op, ретрай в след. цикле). Возврат: развёрнут ли."""
    import log_setup
    import human
    w = logwatch.find_game_window()
    if not w:
        _diag("no game window")
        return False
    r = log_setup.find_log()
    n0 = r.get("n", 0)
    if n0 >= 6:
        _diag(f"already expanded n0={n0}")
        return True                       # уже многострочный — не трогаем
    rows = r.get("rows", [])
    if not rows:
        _diag(f"no rows (n0={n0}) — find_log не видит лог (busy/тёмный фон)")
        return False
    # ПИЛЮЛЯ = НИЖНЯЯ строка лога (новейшее событие). Наводимся на ЛЕВУЮ часть строки (там игровой
    # текст пилюли; правый край бокса часто = просвет фона). На busy-фоне точное место пилюли неясно
    # → пробуем НЕСКОЛЬКО точек слева-направо, ищем где проявится баннер RECORDS (matchTemplate ⛶).
    bx0, by0, bx1, by1 = sorted(rows, key=lambda tb: tb[1][1])[-1][1]
    ry = w.top + (by0 + by1) // 2
    # КРИТИЧНО: рамка RECORDS проявляется по наведению ТОЛЬКО когда игра — foreground-окно (Unity
    # обрабатывает hover лишь для активного окна). По шагу авторазворота игра часто уже не впереди →
    # баннер не появлялся (score 0.39). Выводим игру вперёд ДО наведения.
    try:
        import farm
        farm.focus_game(); time.sleep(0.4)
    except Exception:
        pass
    best = (0.0, None, None)
    for frac in (0.16, 0.28, 0.40, 0.10, 0.52):
        hx = w.left + int(bx0 + (bx1 - bx0) * frac)
        try:
            human.move_abs(hx, ry)        # навести → проявить рамку RECORDS с кнопками
        except Exception as e:
            _diag(f"move_abs err {e!r}"); continue
        time.sleep(0.85)
        frame = logwatch.grab(w)
        region = (bx0 - 50, by0 - 70, bx1 + 50, by1 + 15)   # баннер ВЫШЕ строки пилюли
        es, ex, ey = _match(frame, "records_expand.png", region=region)
        if es > best[0]:
            best = (es, ex, ey)
        if es >= _MATCH_MIN:
            break
    es, ex, ey = best
    if es < _MATCH_MIN or ex is None:
        _diag(f"⛶ best score={es:.2f} < {_MATCH_MIN} (баннер не проявился) bottom_row=({bx0},{by0},{bx1},{by1})")
        return False                      # кнопку ⛶ не нашли уверенно — НЕ жмём вслепую
    # ⛶ растит лог по 1 шагу. Жмём по одному и ПРОВЕРЯЕМ рост — если строк стало БОЛЬШЕ, повторяем
    # (до 3х, до максимума); если МЕНЬШЕ/равно (попали на свёрнуть/тогл) — СТОП, не долбим вслепую.
    # (PIN убрал: клик по pin промахивался на borderline-score и СХЛОПЫВАЛ лог — n 2→1. Expand-only
    #  держится сам, как было в ночном прогоне.)
    n_cur = n0
    for _ in range(3):
        try:
            human.click(w.left + ex, w.top + ey, cfg)
        except Exception:
            break
        time.sleep(0.8)
        n_new = log_setup.find_log().get("n", n_cur)
        if n_new <= n_cur:                # не выросло (или схлопнулось) → дальше не жмём
            n_cur = n_new
            break
        n_cur = n_new
    _diag(f"expand done score={es:.2f} @win({ex},{ey}): n0={n0} → n1={n_cur}")
    if n_cur > n0:
        log(f"лог RECORDS развёрнут (score={es:.2f}): строк {n_cur}")
        return True
    return False


if __name__ == "__main__":
    import json as _j
    print("calibration:", _j.dumps(_cal(), ensure_ascii=False))
    print("is_ready:", is_ready())
    for k in ("game_settings", "log_open", "rec_expand", "rec_gear", "check_first", "check_last"):
        print(f"  {k}: {_screen(k)}")
