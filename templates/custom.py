"""custom.py — «Свой конфиг»: запись / конструктор / проигрывание пользовательских
кликер-рутин для GoodNightBot.

Координаты кликов привязываются к ПАНЕЛИ (banner-relative через vision.norm_offset) →
рутина переживает переезд окна и смену масштаба UI. Если клик вне любой панели — храним
как долю окна; крайний fallback — абсолютный экран.

Рутина может быть «freedom» (полная свобода): её низкоуровневые клики обходят мерж-защиты
фермы — это ответственность пользователя (UI требует подтверждения, см. control.py).

Хранилище: custom_routines.json  {"routines": [ {name, steps, loop, ...} ]}
Шаг (step):
  {"kind":"click","panel":"cube","ox":..,"oy":..,"button":"left","wait":0.4}
  {"kind":"click","wx":..,"wy":..,"button":"left","wait":..}   # доля окна (нет панели)
  {"kind":"click","ax":..,"ay":..,"button":"left","wait":..}   # абсолют (нет окна)
  {"kind":"key","key":"space","wait":1.0}
  {"kind":"wheel","panel":"stash","ox":..,"oy":..,"notches":-3,"wait":..}
  {"kind":"step","action":"merge_all","wait":0}                # высокоуровневый готовый шаг
"""
import json
import os
import random
import time

import mss

import farm
import human
import vision

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTINES_PATH = os.path.join(HERE, "custom_routines.json")

# высокоуровневые готовые шаги -> функции фермы (надёжные, привязаны к панелям внутри)
HIGH_STEPS = ["open_stash", "open_cube", "merge_all", "save_all", "chest", "wait"]
HIGH_RU = {"open_stash": "открыть тайник", "open_cube": "открыть куб",
           "merge_all": "мерж (безопасный)", "save_all": "разложить в тайник",
           "chest": "открыть сундуки", "wait": "пауза"}


# ─────────────────────────── хранилище ───────────────────────────
def load_routines():
    if not os.path.exists(ROUTINES_PATH):
        return {"routines": []}
    try:
        d = json.load(open(ROUTINES_PATH, encoding="utf-8"))
        if "routines" not in d:
            d = {"routines": []}
        return d
    except Exception:
        return {"routines": []}


def save_routines(d):
    json.dump(d, open(ROUTINES_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def get_routine(name):
    for r in load_routines()["routines"]:
        if r.get("name") == name:
            return r
    return None


def upsert_routine(routine):
    d = load_routines()
    d["routines"] = [r for r in d["routines"] if r.get("name") != routine.get("name")]
    d["routines"].append(routine)
    save_routines(d)


def delete_routine(name):
    d = load_routines()
    d["routines"] = [r for r in d["routines"] if r.get("name") != name]
    save_routines(d)


# ─────────────────────── привязка координат ───────────────────────
def _nearest_panel(panels, x, y):
    """Панель, к баннеру которой клик ближе всего по горизонтали (панели стоят бок о бок).
    Возвращает (name, panel, ox, oy) или None."""
    best = None
    for name, p in panels.items():
        ox, oy = vision.norm_offset(p, x, y)
        if best is None or abs(ox) < abs(best[2]):
            best = (name, p, ox, oy)
    return best


def _attach_coords(step, x, y, win, sct):
    """Записать координаты в шаг: panel-relative → window-relative → absolute."""
    if win:
        try:
            panels = vision.detect(win, sct)
        except Exception:
            panels = {}
        np_ = _nearest_panel(panels, x, y) if panels else None
        if np_:
            step["panel"], _, ox, oy = np_
            step["ox"], step["oy"] = round(ox, 4), round(oy, 4)
            return
        step["wx"] = round((x - win.left) / max(1, win.width), 4)
        step["wy"] = round((y - win.top) / max(1, win.height), 4)
        return
    step["ax"], step["ay"] = int(x), int(y)


def _resolve_xy(step, win, panels):
    """Шаг → экранные (x,y). panel-relative → window-relative → absolute. None если нельзя."""
    pn = step.get("panel")
    if pn and pn in panels:
        return vision.pt(panels[pn], step.get("ox", 0), step.get("oy", 0))
    if "wx" in step and win:
        return (int(win.left + step["wx"] * win.width), int(win.top + step["wy"] * win.height))
    if "ax" in step:
        return (int(step["ax"]), int(step["ay"]))
    return None


# ─────────────────────────── рекордер ───────────────────────────
_SPECIAL_KEYS = {
    "space": "space", "enter": "enter", "tab": "tab", "esc": "esc", "backspace": "backspace",
    "delete": "delete", "up": "up", "down": "down", "left": "left", "right": "right",
}


def _key_name(key):
    """pynput key → имя для human.key(); None если игнорируем."""
    try:
        from pynput import keyboard
    except Exception:
        return None
    if isinstance(key, keyboard.KeyCode) and key.char:
        return key.char.lower()
    if isinstance(key, keyboard.Key):
        nm = str(key).split(".")[-1]
        if nm.startswith("f") and nm[1:].isdigit():
            return nm                       # f1..f12
        return _SPECIAL_KEYS.get(nm)
    return None


def record(stop_event, status=None):
    """Записать реальные действия (мышь/клавиши/колесо) до stop_event или хоткея F9.
    Возвращает список шагов (panel-relative координаты). None если pynput недоступен."""
    try:
        from pynput import mouse, keyboard
    except Exception:
        return None
    steps = []
    last = [time.time()]
    sct = mss.mss()

    def _dt():
        now = time.time(); d = now - last[0]; last[0] = now
        return round(min(d, 5.0), 2)

    def on_click(x, y, button, pressed):
        if stop_event.is_set():
            return False
        if not pressed:
            return
        step = {"kind": "click", "button": ("right" if button == mouse.Button.right else "left"),
                "wait": _dt()}
        _attach_coords(step, x, y, farm.fw(), sct)
        steps.append(step)
        if status:
            status(len(steps))

    def on_scroll(x, y, dx, dy):
        if stop_event.is_set():
            return False
        step = {"kind": "wheel", "notches": int(dy), "wait": _dt()}
        _attach_coords(step, x, y, farm.fw(), sct)
        steps.append(step)
        if status:
            status(len(steps))

    def on_press(key):
        if stop_event.is_set():
            return False
        nm = _key_name(key)
        if nm == "f9":                      # хоткей остановки записи
            stop_event.set()
            return False
        if nm == "f12":                     # глобальный стоп — не записываем как шаг
            return
        if nm:
            steps.append({"kind": "key", "key": nm, "wait": _dt()})
            if status:
                status(len(steps))

    ml = mouse.Listener(on_click=on_click, on_scroll=on_scroll)
    kl = keyboard.Listener(on_press=on_press)
    ml.start(); kl.start()
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    finally:
        ml.stop(); kl.stop()
        try:
            sct.close()
        except Exception:
            pass
    return steps


# ─────────────────────────── проигрывание ───────────────────────────
def _do_high(action, sct, log):
    """Высокоуровневый шаг через функции фермы (всегда в безопасной логике фермы)."""
    if action == "open_stash":
        farm.ensure_open(sct, "stash")
    elif action == "open_cube":
        farm.ensure_open(sct, "cube")
    elif action == "merge_all":
        farm.merge_all(sct)
    elif action == "save_all":
        farm.do_saveall_sort(sct)
    elif action == "chest":
        farm.do_chests()
    elif action == "wait":
        pass


def play(routine, log=print, stat=None, stop_event=None):
    """Проиграть рутину. Уважает F12/stop_event между шагами. Гейт фокуса как у фермы.
    log(str), stat(dict), stop_event(threading.Event)."""
    steps = routine.get("steps", [])
    if not steps:
        log("рутина пустая — нечего проигрывать")
        return
    farm.set_hooks(log_cb=log, stat_cb=stat, stop_event=stop_event)   # human-паузы рвутся по стопу
    loop = bool(routine.get("loop", True))
    reps = int(routine.get("repeats", 0))          # 0 = бесконечно (пока стоп)
    freedom = bool(routine.get("freedom", False))
    name = routine.get("name", "?")
    log(f"▶ свой кликер «{name}»" + (" · СВОБОДА (без защит!)" if freedom else ""))

    def stopped():
        return farm._hardstop()

    cnt = 0
    with mss.mss() as sct:
        while not stopped():
            if not farm.ensure_game_foreground(force=True):
                log("нет фокуса игры — жду (сверни браузер/кликни игру)")
                if not farm.isleep(1.5):
                    break
                continue
            win, panels = farm.detect(sct)
            for st in steps:
                if stopped():
                    break
                try:
                    _play_step(st, sct, win, panels, log, freedom)
                except Exception as e:
                    log(f"шаг {st.get('kind')} ошибка: {e!r}")
                if not farm.isleep(max(0.0, float(st.get("wait", 0.3)))):
                    break
                win, panels = farm.detect(sct)     # окно/панели могли сместиться
            cnt += 1
            if stat:
                stat({"cycle": cnt, "running": True})
            if not loop or (reps and cnt >= reps):
                break
            iv = random.uniform(float(routine.get("interval_min", 0)),
                                max(float(routine.get("interval_min", 0)),
                                    float(routine.get("interval_max", 0))))
            if iv > 0:
                log(f"пауза {iv:.1f}с до повтора")
                if not farm.isleep(iv):
                    break
    human.park()
    log(f"⏸ свой кликер «{name}» остановлен")


def _play_step(st, sct, win, panels, log, freedom):
    kind = st.get("kind")
    if kind == "step":
        _do_high(st.get("action", ""), sct, log)
        return
    if kind == "key":
        human.key(st.get("key", ""), farm.CFG)
        return
    xy = _resolve_xy(st, win, panels)
    if xy is None:
        log(f"шаг {kind}: координаты не разрешились (панель закрыта?) — пропуск")
        return
    if kind == "wheel":
        human.wheel(xy[0], xy[1], int(st.get("notches", -1)))
    elif kind == "click":
        human.click(xy[0], xy[1], farm.CFG, button=st.get("button", "left"))
    farm._bot_cursor[0] = (xy[0], xy[1])
