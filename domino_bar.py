"""domino_bar.py — прогресс-бар «домино» (Tkinter-порт CSS-референса фронта): скошенные плитки,
заряд зажигает их слева направо. Цвета — из НОЧНОЙ темы приложения (не радуга): заряд плывёт
лаванда→лунное золото по позиции, зажжённые плитки искрят к звёздному, фаза установки — бегущая
мятная (GO) волна.

API:
    bar = DominoBar(parent, segs=20, height=20, bg=NIGHT, lo=SUB, hi=MOON,
                    unlit=EDGE, spark=STAR, wave=GO)
    bar.set_pct(0..100)   # детерминированный заряд
    bar.wave_start()      # бегущая волна (неизвестный прогресс — напр. установка)
    bar.wave_stop()
"""
import random
import tkinter as tk


def _rgb(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    ar, ag, ab = _rgb(a); br, bg, bb = _rgb(b)
    return "#%02x%02x%02x" % (int(ar + (br - ar) * t), int(ag + (bg - ag) * t), int(ab + (bb - ab) * t))


class DominoBar(tk.Canvas):
    def __init__(self, master, segs=20, height=20, bg="#171229", lo="#9a8fce", hi="#f6e3a1",
                 unlit="#3d2f6b", spark="#fff4c2", wave="#48d98a", **kw):
        super().__init__(master, height=height, highlightthickness=0, bd=0, bg=bg, **kw)
        self.segs = segs
        self._h = height
        self._lo, self._hi, self._unlit, self._spk, self._wavecol = lo, hi, unlit, spark, wave
        self._pct = 0.0
        self._wave = None          # индекс бегущей волны (None → выкл)
        self._spark = -1           # индекс искрящей плитки (-1 → нет)
        self.bind("<Configure>", lambda e: self._redraw())
        self.after(160, self._spark_tick)

    def _geom(self):
        w = max(self.winfo_width(), 1)
        sk = self._h * 0.28                       # скос (skewX)
        gap = 3
        tw = max(1.0, (w - sk - gap * (self.segs - 1)) / self.segs)
        return sk, gap, tw

    def _tile(self, x, tw, sk, lit, fill):
        h = self._h
        tf = 0.92 if lit else 0.5                 # незаряженная плитка ниже (scaleY .55), прижата вниз
        y0 = h * (1 - tf)
        pts = [x + sk, y0, x + sk + tw, y0, x + tw, h - 1, x, h - 1]
        self.create_polygon(pts, fill=(fill if lit else self._unlit), outline="")

    def _redraw(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.delete("all")
        sk, gap, tw = self._geom()
        span = max(1, self.segs - 1)
        if self._wave is not None:                # ── волна установки (мятная GO, бежит) ──
            for i in range(self.segs):
                x = i * (tw + gap)
                d = abs(i - self._wave)
                fill = _lerp(self._wavecol, self._spk, 0.45) if d == 0 else self._wavecol
                self._tile(x, tw, sk, d <= 1, fill)
            return
        lit_n = int(round(self._pct / 100.0 * self.segs))   # ── заряд: лаванда→золото по позиции ──
        for i in range(self.segs):
            x = i * (tw + gap)
            fill = _lerp(self._lo, self._hi, i / span)
            if i == self._spark:
                fill = _lerp(fill, self._spk, 0.6)
            self._tile(x, tw, sk, i < lit_n, fill)

    def _spark_tick(self):
        try:
            if self._wave is None and self._pct > 0:
                lit_n = int(round(self._pct / 100.0 * self.segs))
                self._spark = random.randrange(lit_n) if lit_n > 0 else -1
                self._redraw()
            self.after(160, self._spark_tick)
        except tk.TclError:
            pass

    def set_pct(self, pct):
        self._pct = max(0.0, min(100.0, float(pct)))
        if self._wave is None:
            self._redraw()

    def wave_start(self):
        if self._wave is None:
            self._wave = 0
            self._wave_tick()

    def _wave_tick(self):
        if self._wave is None:
            return
        try:
            self._wave = (self._wave + 1) % (self.segs + 4)
            self._redraw()
            self.after(55, self._wave_tick)
        except tk.TclError:
            self._wave = None

    def wave_stop(self):
        self._wave = None
        self._redraw()
