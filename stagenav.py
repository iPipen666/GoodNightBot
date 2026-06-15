"""stagenav.py — навигация по стадиям через окно PORTAL. WIP.

Поток (подтверждён скрином PORTAL): кнопка PORTAL → дропдаун сложности (Обычный/Кошмар/Ад/Мучение)
→ табы Акт 1/2/3 → клик по узлу этапа на карте. Метка узла = акт-этап. Нотация сообщества
X-Y-Z = сложность(1-4)-акт(1-3)-этап(1-10).

Координаты — ДОЛИ окна игры (rx,ry) из portal_calibration.json (калибруется calibrate_portal.py,
как records_calibration). БЕЗОПАСНО: нет калибровки нужной точки → goto() НЕ кликает вслепую,
возвращает False (HopMode останется на месте — лучше не прыгнуть, чем misclick).

Чистая логика (parse_label / nav_plan / point) тестируется офлайн (test_stagenav). Живой goto()
требует foreground-игру + заполненный portal_calibration.json.
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_CAL_PATH = os.path.join(HERE, "portal_calibration.json")

DIFF_IDX = {1: "NORMAL", 2: "NIGHTMARE", 3: "HELL", 4: "TORMENT"}
DIFF_RU = {"NORMAL": "Обычный", "NIGHTMARE": "Кошмар", "HELL": "Ад", "TORMENT": "Мучение"}


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
    """Последовательность шагов навигации (ключи калибровки), которые goto() прокликает по порядку.
    Возвращает список (kind, key) или None. Чисто — тестируется без игры."""
    p = parse_label(label)
    if not p:
        return None
    return [
        ("open", "portal_open"),                          # открыть PORTAL
        ("click", "diff_dropdown"),                       # раскрыть дропдаун сложности
        ("click", "diff_option_%s" % p["difficulty"].lower()),  # выбрать сложность
        ("click", "act_tab_%d" % p["act"]),               # таб акта
        ("node", "stage_nodes/%d/%d" % (p["act"], p["no"])),    # узел этапа на карте акта
    ]


def _win():
    import logwatch
    return logwatch.find_game_window()


def _cal():
    try:
        return json.load(open(_CAL_PATH, encoding="utf-8"))
    except Exception:
        return {}


def _frac_to_screen(frac, win):
    """{'rx','ry'} (доли окна) → экранные (x,y). None если нет."""
    if not frac or not win:
        return None
    return int(win.left + frac["rx"] * win.width), int(win.top + frac["ry"] * win.height)


def resolve(cal, key, win):
    """Экранная точка для ключа плана. Поддержка вложенного 'stage_nodes/<act>/<no>'. None если нет."""
    if key.startswith("stage_nodes/"):
        _, act, no = key.split("/")
        nodes = (cal.get("stage_nodes", {}) or {}).get(str(act), [])
        idx = int(no) - 1
        frac = nodes[idx] if 0 <= idx < len(nodes) else None
        return _frac_to_screen(frac, win)
    return _frac_to_screen(cal.get(key), win)


def goto(stage, cfg, log=lambda *_: None, confirm=True):
    """ЖИВОЙ переход на стадию. stage = dict с 'label' (или строка-метка). Возвращает bool успех.
    Безопасно: любая точка плана не откалибрована → НЕ кликаем (вернём False)."""
    label = stage.get("label") if isinstance(stage, dict) else str(stage)
    plan = nav_plan(label)
    if not plan:
        log(f"stagenav: кривая метка {label!r}"); return False
    cal, win = _cal(), _win()
    if not win:
        log("stagenav: окно игры не найдено"); return False
    pts = []
    for kind, key in plan:
        pt = resolve(cal, key, win)
        if not pt:
            log(f"stagenav: точка '{key}' не откалибрована — НЕ кликаю (запусти calibrate_portal.py)")
            return False
        pts.append((kind, pt))
    import human
    try:
        import farm
        farm.focus_game(); time.sleep(0.3)
    except Exception:
        pass
    for kind, pt in pts:
        human.click(pt[0], pt[1], cfg)
        time.sleep(0.6 if kind in ("open", "click") else 0.8)
    if confirm:
        ok = _confirm(label, log)
        log(f"stagenav → {label}: {'✓' if ok else 'не подтверждён (проверь калибровку)'}")
        return ok
    return True


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
