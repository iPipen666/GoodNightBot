"""TBH — общий слой человекоподобного ввода (клики + паузы + стоп-клавиша).

Используется stash.py / clicker.py / chest_clicker.py — единая логика, чтобы
антибот-эвристики видели «живого» игрока:
  * клик НЕ пиксель-в-пиксель: джиттер масштабируется к размеру цели (gauss к центру);
  * ход курсора: случайный tween + варьируемая длительность + иногда овершут-коррекция;
  * нажатие: варьируемое время удержания;
  * паузы между действиями: рандом, ИНОГДА длинные (до ~10с) — настраивается в config.

Всё берётся из config["humanize"]; разумные дефолты, если ключа нет.
"""
import time
import random
import ctypes

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.MINIMUM_DURATION = 0  # не навязывать свой минимум
except Exception:
    pyautogui = None

try:
    import pydirectinput as PDI
    PDI.FAILSAFE = True
except Exception:
    PDI = None

try:
    import keyboard as _kb
except Exception:
    _kb = None

_STOP_CHECK = [None]   # farm регистрирует сюда _hardstop -> паузы рвутся по кнопке СТОП мгновенно


def set_stop_check(fn):
    _STOP_CHECK[0] = fn


def _stopped():
    fn = _STOP_CHECK[0]
    try:
        return bool(fn and fn())
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────
# SendInput-слой (Волна OCR): абсолютное движение курсора через настоящее
# input-событие. В отличие от pyautogui.moveTo/SetCursorPos (warp — Unity New
# Input System его НЕ видит без физической мыши), SendInput вставляет событие
# во input stream → Windows синтезирует WM_INPUT → Unity слышит наведение даже
# без подключённой мыши. Используется ТОЛЬКО для OCR-ховера (items.hover);
# клики farm2 по-прежнему идут через _move/pyautogui (не трогаем рабочий путь).
import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)

_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000
_MOUSEEVENTF_WHEEL = 0x0800
_WHEEL_DELTA = 120
_SM_XVIRTUALSCREEN, _SM_YVIRTUALSCREEN = 76, 77
_SM_CXVIRTUALSCREEN, _SM_CYVIRTUALSCREEN = 78, 79
_ULONG_PTR = wintypes.WPARAM


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def set_dpi_aware():
    """Per-Monitor v2 DPI awareness — координаты mss-захвата и SendInput в одной
    физической системе. Вызывать один раз; повторный вызов безвреден."""
    try:
        _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_V2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                _user32.SetProcessDPIAware()
            except Exception:
                pass


try:
    set_dpi_aware()
except Exception:
    pass


def _send_abs(x, y):
    """Один абсолютный SendInput-move на экранные пиксели (virtual desktop)."""
    vx = _user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
    vy = _user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
    vw = _user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
    vh = _user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
    nx = int(round((x - vx) * 65535 / max(1, vw - 1)))
    ny = int(round((y - vy) * 65535 / max(1, vh - 1)))
    nx = max(0, min(65535, nx))
    ny = max(0, min(65535, ny))
    inp = _INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(
        dx=nx, dy=ny, mouseData=0,
        dwFlags=_MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK,
        time=0, dwExtraInfo=0)))
    n = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    if n != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def wheel(x, y, notches, settle=0.18):
    """Прокрутка колеса над точкой (x,y). notches>0 — вверх, <0 — вниз (как реальное колесо).
    Сначала ставим курсор на точку (move_abs без джиттера: Unity скроллит элемент ПОД
    курсором), затем шлём колесо. settle — пауза после прокрутки (анимация списка)."""
    move_abs(int(x), int(y), nudge=0)
    time.sleep(0.05)
    data = int(notches) * _WHEEL_DELTA
    inp = _INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(
        dx=0, dy=0, mouseData=ctypes.c_uint32(data & 0xFFFFFFFF).value,
        dwFlags=_MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=0)))
    n = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    if n != 1:
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(settle)


def move_abs(x, y, nudge=12, settle=0.05):
    """Надёжный hover-move для Unity без физической мыши. Двухшаговый:
    сначала рядом (сменить raycast-цель → exit), потом точно на слот → PointerEnter
    → тултип. nudge=0 — одиночный move. Это НЕ заменяет _move для кликов."""
    x, y = int(x), int(y)
    if nudge:
        _send_abs(x + nudge, y + nudge)
        time.sleep(settle)
    _send_abs(x, y)


def find_hwnd(title_substrings):
    """HWND видимого окна, чей заголовок содержит любую из подстрок. None если нет."""
    needles = [s.lower() for s in (title_substrings or [])]
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _):
        if _user32.IsWindowVisible(h):
            n = _user32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            _user32.GetWindowTextW(h, b, n + 1)
            t = (b.value or "").lower()
            if t and any(s in t for s in needles):
                found.append(h)
        return True

    _user32.EnumWindows(_cb, 0)
    return found[0] if found else None


_VK_MENU = 0x12
_KEYEVENTF_KEYUP = 0x2


def focus_window(hwnd):
    """Надёжно вывести окно на передний план. КРИТИЧНО для OCR-ховера: Unity
    получает raw-input (и обновляет тултипы) только когда окно в фокусе. Чистый
    SetForegroundWindow из фонового процесса Windows молча игнорит — обходим
    alt-трюком (синтетический Alt снимает foreground-lock) + AttachThreadInput.
    Проверено: даёт foreground==hwnd там, где AttachThreadInput-only давал False.
    Возвращает True если окно стало foreground."""
    if not hwnd:
        return False
    # SW_RESTORE двигал/ресайзил окно при КАЖДОМ фокусе (корень «окно прыгает» -> сетка/почта
    # мажут). Восстанавливаем ТОЛЬКО если реально свёрнуто; иначе позицию не трогаем.
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # alt-трюк: синтетический Alt разблокирует SetForegroundWindow
    _user32.keybd_event(_VK_MENU, 0, 0, 0)
    fg = _user32.GetForegroundWindow()
    cur_tid = _user32.GetWindowThreadProcessId(hwnd, None)
    fg_tid = _user32.GetWindowThreadProcessId(fg, None)
    if fg_tid and cur_tid != fg_tid:
        _user32.AttachThreadInput(fg_tid, cur_tid, True)
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        _user32.AttachThreadInput(fg_tid, cur_tid, False)
    else:
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
    _user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
    time.sleep(0.3)
    return _user32.GetForegroundWindow() == hwnd


_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


def is_foreground(hwnd):
    return bool(hwnd) and _user32.GetForegroundWindow() == hwnd


def real_click(x, y):
    """Настоящий клик SendInput-движением: Windows принимает его за активацию окна
    (в отличие от SetForegroundWindow из фона). Без human-твинов — это активация, не игра."""
    move_abs(int(x), int(y), nudge=0)
    time.sleep(0.04)
    _user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    _user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def ensure_foreground(hwnd, click_xy=None, retries=3, settle=0.25):
    """Гарантировать игру foreground (иначе Unity не рисует тултипы). Лесенка:
    alt-трюк+SetForegroundWindow -> проверка; не вышло -> РЕАЛЬНЫЙ клик по безопасной точке
    игры (если задана) -> проверка; до retries раз. Вернуть True, если стала foreground."""
    if not hwnd:
        return False
    for _ in range(retries):
        if is_foreground(hwnd):
            return True
        focus_window(hwnd)
        if is_foreground(hwnd):
            return True
        if click_xy:
            real_click(*click_xy)
            time.sleep(settle)
    return is_foreground(hwnd)


_TWEENS = None


def _tweens():
    global _TWEENS
    if _TWEENS is None and pyautogui is not None:
        _TWEENS = [pyautogui.easeInOutQuad, pyautogui.easeOutQuad,
                   pyautogui.easeInQuad, pyautogui.linear]
    return _TWEENS or [None]


def kill_pressed(key="f12"):
    if _kb is None:
        return False
    try:
        return _kb.is_pressed(key)
    except Exception:
        return False


def _h(cfg):
    return (cfg or {}).get("humanize", {})


def _gauss_jitter(amp):
    """Смещение ~N(0, amp/2), обрезанное к [-amp, amp]: чаще у центра, редко у края."""
    v = random.gauss(0, amp / 2.0)
    return max(-amp, min(amp, v))


def _move(x, y, cfg):
    if _stopped():            # СТОП нажат — не двигаемся
        return
    h = _h(cfg)
    if h.get("fast_mode"):
        dur = random.uniform(h.get("fast_move_min", 0.10), h.get("fast_move_max", 0.35))
    else:
        dur = random.uniform(h.get("move_duration_min", 0.18), h.get("move_duration_max", 0.75))
    tw = random.choice(_tweens())
    # иногда (overshoot_chance) промахиваемся и доводим — как живая рука
    if random.random() < h.get("overshoot_chance", 0.25):
        ox = x + random.uniform(-1, 1) * h.get("overshoot_px", 22)
        oy = y + random.uniform(-1, 1) * h.get("overshoot_px", 22)
        try:
            pyautogui.moveTo(int(ox), int(oy), duration=dur * 0.7, tween=tw)
        except Exception:
            pyautogui.moveTo(int(ox), int(oy))
        time.sleep(random.uniform(0.02, 0.09))
        try:
            pyautogui.moveTo(int(x), int(y), duration=dur * 0.5,
                             tween=random.choice(_tweens()))
        except Exception:
            pyautogui.moveTo(int(x), int(y))
    else:
        try:
            pyautogui.moveTo(int(x), int(y), duration=dur, tween=tw)
        except Exception:
            pyautogui.moveTo(int(x), int(y))


def _press(cfg):
    h = _h(cfg)
    a, b = h.get("press_min", 0.04), h.get("press_max", 0.14)
    if PDI is not None:
        PDI.mouseDown(); time.sleep(random.uniform(a, b)); PDI.mouseUp()
    else:
        pyautogui.mouseDown(); time.sleep(random.uniform(a, b)); pyautogui.mouseUp()


def click(x, y, cfg, size=None, button="left", mod=None):
    """Человекоподобный клик в (x,y).

    size: (w,h) или скаляр — джиттер берётся как доля от размера цели
          (jitter_frac, по умолч. 0.30), но не больше jitter_max_px. Если size=None —
          фикс. джиттер target_jitter_px. mod: 'alt'/'ctrl'/None — модификатор.
    """
    if _stopped():            # СТОП нажат — клик не делаем (бурст обрывается мгновенно)
        return
    h = _h(cfg)
    if size is not None:
        if isinstance(size, (tuple, list)):
            sw, sh = size
        else:
            sw = sh = size
        frac = h.get("jitter_frac", 0.30)
        cap = h.get("jitter_max_px", 18)
        ampx = min(sw * frac * 0.5, cap)
        ampy = min(sh * frac * 0.5, cap)
    else:
        ampx = ampy = h.get("target_jitter_px", 6)
    jx = x + _gauss_jitter(ampx)
    jy = y + _gauss_jitter(ampy)
    _move(jx, jy, cfg)
    time.sleep(random.uniform(0.02, 0.07))
    if mod:
        (PDI or pyautogui).keyDown(mod); time.sleep(random.uniform(0.03, 0.08))
    if button == "right":
        if PDI is not None:
            PDI.mouseDown(button="right"); time.sleep(random.uniform(h.get("press_min", 0.04), h.get("press_max", 0.14))); PDI.mouseUp(button="right")
        else:
            pyautogui.mouseDown(button="right"); time.sleep(random.uniform(0.04, 0.14)); pyautogui.mouseUp(button="right")
    else:
        _press(cfg)
    if mod:
        time.sleep(random.uniform(0.03, 0.08)); (PDI or pyautogui).keyUp(mod)
    time.sleep(random.uniform(0.03, 0.12))


def key(name, cfg=None):
    """Человекоподобное нажатие клавиши (например 'space' — Руна открытия сундуков)."""
    if _stopped():                 # СТОП — клавиша не жмётся (без конвульсий после стопа)
        return
    drv = PDI or pyautogui
    if drv is None:
        return
    try:
        drv.keyDown(name)
        time.sleep(random.uniform(0.04, 0.13))
        drv.keyUp(name)
    except Exception:
        try:
            drv.press(name)
        except Exception:
            pass


def pause(cfg, lo=None, hi=None):
    """Рандомная пауза. Если lo/hi не заданы — берёт between_clicks_* из config.
    С вероятностью long_pause_chance вставляет ДЛИННУЮ паузу до long_pause_max (~10с),
    чтобы каденс не был машинно-ровным. Прерывается стоп-клавишей (дробит сон)."""
    h = _h(cfg)
    if h.get("fast_mode"):
        if lo is None:
            lo = h.get("fast_between_min", 0.5)
        if hi is None:
            hi = h.get("fast_between_max", 1.2)
        long_chance = h.get("long_pause_chance_fast", 0.06)
    else:
        if lo is None:
            lo = h.get("between_clicks_min", 0.8)
        if hi is None:
            hi = h.get("between_clicks_max", 3.5)
        long_chance = h.get("long_pause_chance", 0.18)
    if random.random() < long_chance:
        hi = h.get("long_pause_max", 10.0)
        lo = max(lo, h.get("long_pause_min", 3.0))
    dur = random.uniform(lo, hi)
    key = (cfg or {}).get("kill_key", "f12")
    slept = 0.0
    while slept < dur:
        if kill_pressed(key) or _stopped():
            return False
        step = min(0.12, dur - slept)
        time.sleep(step); slept += step
    return True


def tap(x, y):
    """Мгновенный клик без гуманлайк-задержек — для быстрых скан-кликов (вкладки тайника).
    Прямой moveTo без tween/overshoot + короткий down/up. Гейм-детекта тут нет, нужна скорость."""
    if _stopped():                 # СТОП — не кликаем
        return
    drv = PDI or pyautogui
    if drv is None:
        return
    try:
        pyautogui.moveTo(int(x), int(y))
        drv.mouseDown(); time.sleep(0.02); drv.mouseUp()
    except Exception:
        pass


def restore_cursor(pos):
    """Параллельный режим: вернуть курсор в сохранённую точку (бот сделал дело — вернул мышь
    туда, где её оставил юзер). Мгновенный SetCursorPos, без анимации."""
    if not pos:
        return
    try:
        ctypes.windll.user32.SetCursorPos(int(pos[0]), int(pos[1]))
    except Exception:
        pass


def park(x=8, y=400):
    """Увести курсор в нейтральную точку (нет тултипов/слотов)."""
    if _stopped() or pyautogui is None:
        return
    try:
        pyautogui.moveTo(int(x), int(y), duration=0.2)
    except Exception:
        pass


def twitch(cfg=None) -> None:
    """Микро-твич: 1-2 крошечных смещения курсора (±3..8px) с паузой 0.05..0.2с,
    имитация дрожи руки. Через _move."""
    if pyautogui is None:
        return
    for _ in range(random.randint(1, 2)):
        cx, cy = pyautogui.position()
        nx = cx + random.choice([-1, 1]) * random.randint(3, 8)
        ny = cy + random.choice([-1, 1]) * random.randint(3, 8)
        _move(nx, ny, cfg)
        time.sleep(random.uniform(0.05, 0.2))


def loiter(sct, cfg=None) -> None:
    """С вероятностью cfg.humanize.loiter_chance выполнить ОДНО случайное
    действие и вернуть как было:
      - открыть/закрыть инфо-панель (key из loiter_keys, нажать дважды: открыл/закрыл),
      - короткая пауза "отошёл".
    sct прокидывается на случай будущей проверки экрана (в Волне 1 не обязателен)."""
    h = _h(cfg)
    if random.random() >= h.get("loiter_chance", 0.0):
        return
    action = random.choice(["key", "pause"])
    if action == "key":
        keys = h.get("loiter_keys", [])
        if keys:
            k = random.choice(keys)
            key(k, cfg)
            time.sleep(random.uniform(0.1, 0.4))
            key(k, cfg)
    else:
        pause(cfg, lo=0.3, hi=1.0)
