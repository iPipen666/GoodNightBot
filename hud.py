"""GoodNightBot — HUD-таймер над игрой (свободный, перетаскиваемый, ФИКС-размер = без дёрганья).

Низ — что делает бот (NEXT · MAIL / checking mail / opening chests …). Верх — отсчёт до действия
(«12,34 sec» → «5,4,3,2,1» → «GO!»). При дропе бессмертный+ верх празднует: HELL YEAH!!! →
IMMORTAL <TYPE> → CONGRATULATIONS! → назад в таймер. Окно фикс-размера, позиция/масштаб/цвета в
config.json "hud" (настройки в ⚙). Тянешь за цифры — ставишь куда угодно.
"""
import os
import json
import time
import math
import tkinter as tk

import theme as T  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")
_BG = "#010203"
_GOLD = "#ffd95e"

# короткое слово для ВЕРХА в активной фазе / после "NEXT ·"
_SHORT = {"почта": "MAIL", "сундуки": "CHESTS", "скан инвентаря": "SCAN", "скан": "SCAN",
          "скан…": "SCAN", "проход": "WORK", "готовлюсь": "WARM-UP", "следующий проход": "CYCLE",
          "стоп": "STOP", "ожидание": "WAIT"}
# длинная подпись для НИЗА в активной фазе
_LONG = {"почта": "checking mail", "сундуки": "opening chests", "скан": "scanning inventory",
         "скан…": "scanning inventory", "проход": "working", "готовлюсь": "warming up",
         "стоп": "stopped"}
DEFAULTS = {"x": 700, "y": 860, "scale": 42, "color_top": "#ffffff", "color_bottom": _GOLD}


def _font(size, italic=True):
    return ("Impact", max(8, int(size)), "bold italic" if italic else "bold")


def _short(s):
    s = (s or "").strip()
    return _SHORT.get(s.lower(), s.upper())


def _long(s):
    s = (s or "").strip()
    return _LONG.get(s.lower(), s.lower())


def _load_hud_cfg():
    try:
        c = json.load(open(CFG_PATH, encoding="utf-8")).get("hud", {})
    except Exception:
        c = {}
    return {k: c.get(k, v) for k, v in DEFAULTS.items()}


class TimerHud:
    def __init__(self, root):
        self.root = root
        self.deadline = None
        self.action = ""
        self.running = False
        self.shown = True
        self._visible = False
        self._celeb = None
        self._celeb_start = 0.0
        self._drag = (0, 0)
        self.cfg = _load_hud_cfg()
        self._build()
        self.root.after(200, self._tick)

    def _build(self):
        w = tk.Toplevel(self.root)
        self.win = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=_BG)
        try:
            w.attributes("-transparentcolor", _BG)
        except Exception:
            pass
        self.c = tk.Canvas(w, bg=_BG, highlightthickness=0, bd=0)
        self.c.pack()
        self.id_top = self.c.create_text(0, 0, anchor="sw", text="")    # крупная целая часть / слово
        self.id_frac = self.c.create_text(0, 0, anchor="sw", text="")   # мелкие ",00 sec"
        self.id_bot = self.c.create_text(0, 0, anchor="nw", text="")    # подпись действия
        for it in (self.id_top, self.id_frac, self.id_bot):
            self.c.tag_bind(it, "<Button-1>", self._press)
            self.c.tag_bind(it, "<B1-Motion>", self._move)
            self.c.tag_bind(it, "<ButtonRelease-1>", self._release)
            self.c.tag_bind(it, "<Enter>", lambda e: self.c.config(cursor="fleur"))
            self.c.tag_bind(it, "<Leave>", lambda e: self.c.config(cursor=""))
        self._apply_style()
        self.win.geometry(f"+{int(self.cfg['x'])}+{int(self.cfg['y'])}")
        w.withdraw()

    def _apply_style(self):
        s = int(self.cfg["scale"])
        self.big = int(s * 1.18)
        self.small = int(s * 0.5)
        self._M = max(6, int(s * 0.28))                 # маржин (наклонный шрифт не режется)
        self._BASE = self.big + self._M                 # базовая линия верхней строки
        self._W = int(s * 12)                           # ФИКС размер окна — не дёргается
        self._H = int(self.big + self.small + self._M * 2.4)
        self.c.config(width=self._W, height=self._H)
        self.c.itemconfig(self.id_top, font=_font(self.big), fill=self.cfg["color_top"])
        self.c.itemconfig(self.id_frac, font=_font(self.small), fill=self.cfg["color_top"])
        self.c.itemconfig(self.id_bot, font=_font(self.small), fill=self.cfg["color_bottom"])
        self._gap = max(2, int(s * 0.06))
        self.c.coords(self.id_top, self._M, self._BASE)
        self.c.coords(self.id_bot, self._M, self._BASE + self._gap)

    def reload(self):
        self.cfg = _load_hud_cfg()
        try:
            self._apply_style()
            self.win.geometry(f"+{int(self.cfg['x'])}+{int(self.cfg['y'])}")
        except Exception:
            pass

    # ---- перетаскивание ----
    def _press(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _move(self, e):
        self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _release(self, e):
        x, y = self.win.winfo_x(), self.win.winfo_y()
        self.cfg["x"], self.cfg["y"] = x, y
        try:
            c = json.load(open(CFG_PATH, encoding="utf-8"))
            c.setdefault("hud", {}).update({"x": x, "y": y})
            json.dump(c, open(CFG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- API ----
    def toggle(self):
        pass

    def celebrate(self, item_type=None):
        t = (item_type or "RANK DROP").upper()
        self._celeb = ["HELL YEAH!!!", f"IMMORTAL {t}", "CONGRATULATIONS!"]
        self._celeb_start = time.monotonic()

    def update_stat(self, s):
        self.running = bool(s.get("running", True)) and s.get("phase") != "стоп"
        cel = s.get("celebrate")
        if cel:
            self.celebrate(cel if isinstance(cel, str) else None)
        ni = s.get("next_in")
        if s.get("phase") == "ожидание" and ni:
            self.deadline = time.monotonic() + float(ni)
            self.action = s.get("next_action", "следующий проход")
        else:
            self.deadline = None
            self.action = s.get("phase", "")

    def stop(self):
        self.running = False
        try:
            self.win.withdraw()
            self._visible = False
        except Exception:
            pass

    # ---- внутреннее ----
    def _remaining(self):
        return None if self.deadline is None else max(0.0, self.deadline - time.monotonic())

    def _tick(self):
        try:
            self._refresh()
        except Exception:
            pass
        self.root.after(120, self._tick)

    def _set_top(self, text, font, fill):
        self.c.itemconfig(self.id_top, text=text, font=font, fill=fill)
        self.c.coords(self.id_top, self._M, self._BASE)   # позиция ФИКС (окно не двигается)

    def _refresh(self):
        if not self.running:
            if self._visible:
                self.win.withdraw(); self._visible = False
            return
        if not self._visible:
            self.win.deiconify(); self.win.attributes("-topmost", True); self._visible = True
        c = self.c
        celeb = False
        if self._celeb is not None:
            idx = int((time.monotonic() - self._celeb_start) // 1.1)
            if idx < len(self._celeb):           # ПРАЗДНОВАНИЕ
                self._set_top(self._celeb[idx], _font(int(self.small * 1.6)), _GOLD)
                c.itemconfig(self.id_frac, text="")
                c.itemconfig(self.id_bot, text="🎉  ★  🎉", fill=self.cfg["color_bottom"])
                celeb = True
            else:
                self._celeb = None
        if not celeb:
            rem = self._remaining()
            if rem is not None:                   # ОЖИДАНИЕ: верх=отсчёт, низ=что будет (не дубль)
                if rem <= 0.3:
                    top, frac = "GO!", ""
                elif rem <= 5:
                    top, frac = str(max(1, math.ceil(rem))), ""
                else:
                    ip, _, fp = f"{rem:0.2f}".replace(".", ",").partition(",")
                    top, frac = ip, "," + fp + " sec"
                self._set_top(top, _font(self.big), self.cfg["color_top"])
                c.itemconfig(self.id_frac, text=frac, fill=self.cfg["color_top"])
                c.itemconfig(self.id_bot, text=_long(self.action), fill=self.cfg["color_bottom"])
            else:                                 # ДЕЙСТВИЕ: одна строка сверху, низ ПУСТ (без дубля)
                self._set_top(_short(self.action), _font(self.big), self.cfg["color_top"])
                c.itemconfig(self.id_frac, text="")
                c.itemconfig(self.id_bot, text="")
        # вернуть строки на канонические позиции (после нормализации прошлого тика),
        # затем поставить ",00 sec" сразу за крупной частью
        c.coords(self.id_top, self._M, self._BASE)
        c.coords(self.id_bot, self._M, self._BASE + self._gap)
        c.update_idletasks()
        bt = c.bbox(self.id_top)
        if bt:
            c.coords(self.id_frac, bt[2] + 3, self._BASE)
        self._layout()

    def _layout(self):
        """Гарантия отсутствия обреза: меряем РЕАЛЬНЫЙ bbox всех строк и, если верх/лево глифов
        ушли выше маржина (наклонный Impact вылазит над базовой линией), сдвигаем весь контент
        вниз/вправо так, чтобы со ВСЕХ сторон был отступ _M. Затем подгоняем канвас. Окно стоит
        на месте (позиция фикс) → ни обреза, ни дёрганья."""
        c = self.c
        c.update_idletasks()
        items = (self.id_top, self.id_frac, self.id_bot)
        boxes = [b for b in (c.bbox(i) for i in items) if b]
        if not boxes:
            return
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        dx, dy = self._M - x0, self._M - y0
        if dx or dy:                                   # верх/лево залезли за край — сдвинуть всё
            for i in items:
                c.move(i, dx, dy)
            c.update_idletasks()
            boxes = [b for b in (c.bbox(i) for i in items) if b]
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        c.config(width=int(x1 + self._M), height=int(y1 + self._M))
