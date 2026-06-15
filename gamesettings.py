"""gamesettings.py — установка ЛЮБЫХ игровых настроек через панель Settings (шестерёнка). WIP.

Поток: gear → панель Settings → клик по тумблеру нужной настройки → закрыть (Esc). Координаты —
ДОЛИ окна игры (rx,ry) из game_settings_calibration.json (калибруется отдельно). БЕЗОПАСНО: нет
калибровки точки → НЕ кликаем (вернём False). Идемпотентный set-to-desired требует чтения состояния
тумблера (read_state-колбэк); без него apply() = одиночный toggle (клик).

Чистая логика (resolve/plan/known) тестируется офлайн (test_gamesettings). Живой apply() требует
foreground-игру + заполненную калибровку.
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_CAL_PATH = os.path.join(HERE, "game_settings_calibration.json")

# Известные игровые настройки-тумблеры (имя → описание). Калибруются как toggles.<name>.
KNOWN = {
    "pin_log": "Закрепить окно лога (Pin Log Window)",
    "log_filter_chest": "Лог: показывать сундуки",
    "log_filter_stage": "Лог: показывать этапы/боссов",
    "log_filter_item": "Лог: показывать предметы",
    "chest_autoopen": "Авто-открытие сундуков",
}


def _cal():
    try:
        return json.load(open(_CAL_PATH, encoding="utf-8"))
    except Exception:
        return {}


def _win():
    import logwatch
    return logwatch.find_game_window()


def _frac_to_screen(frac, win):
    if not frac or not win:
        return None
    return int(win.left + frac["rx"] * win.width), int(win.top + frac["ry"] * win.height)


def resolve(cal, key, win):
    """Экранная точка ключа: 'gear'/'close' на верхнем уровне, тумблеры в cal['toggles'][name]."""
    if key.startswith("toggle:"):
        name = key.split(":", 1)[1]
        frac = (cal.get("toggles", {}) or {}).get(name)
    else:
        frac = cal.get(key)
    return _frac_to_screen(frac, win)


def plan(name):
    """Шаги установки настройки name: открыть Settings → кликнуть тумблер → закрыть. None если имя
    неизвестно. Чисто — тестируется без игры."""
    if name not in KNOWN:
        return None
    return [("open", "gear"), ("click", "toggle:%s" % name), ("close", "close")]


def apply(name, cfg, log=lambda *_: None, desired=None, read_state=None):
    """ЖИВО установить настройку. read_state(name)->bool (опц.): если дан и desired задан — кликаем
    тумблер ТОЛЬКО при несовпадении (идемпотентно). Иначе одиночный toggle. Безопасно: некалибровано
    → False без кликов. Возвращает bool (применено/уже в нужном состоянии)."""
    p = plan(name)
    if not p:
        log(f"gamesettings: неизвестная настройка {name!r}"); return False
    cal, win = _cal(), _win()
    if not win:
        log("gamesettings: окно игры не найдено"); return False
    pts = []
    for kind, key in p:
        pt = resolve(cal, key, win)
        if not pt:
            log(f"gamesettings: точка '{key}' не откалибрована — НЕ кликаю"); return False
        pts.append((kind, pt))
    # идемпотентность: если умеем читать состояние и оно уже = desired → ничего не делаем
    if desired is not None and read_state is not None:
        try:
            if bool(read_state(name)) == bool(desired):
                log(f"gamesettings: {name} уже = {desired} — пропуск"); return True
        except Exception:
            pass
    import human
    try:
        import farm
        farm.focus_game(); time.sleep(0.3)
    except Exception:
        pass
    for kind, pt in pts:
        human.click(pt[0], pt[1], cfg)
        time.sleep(0.5)
    log(f"gamesettings: {name} переключена" + (f" → {desired}" if desired is not None else ""))
    return True


def set_profile(profile, cfg, log=lambda *_: None, read_state=None):
    """Применить набор настроек {name: desired_bool}. Возвращает {name: ok}."""
    res = {}
    for name, desired in profile.items():
        res[name] = apply(name, cfg, log=log, desired=desired, read_state=read_state)
    return res
