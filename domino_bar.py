"""domino_bar.py — прогресс-бар «домино» (Tkinter-порт CSS-референса фронта): скошенные плитки,
заряд зажигает их слева направо, оттенок плывёт красный(8°)→голубой(205°) по проценту, зажжённые
плитки слегка мерцают (spark). На фазе установки — бегущая «волна» (indeterminate).

API:
    bar = DominoBar(parent, segs=20, height=20, bg="#171229", unlit="#3d2f6b")
    bar.set_pct(0..100)   # детерминированный заряд
    bar.wave_start()      # бегущая волна (неизвестный прогресс — напр. установка)
    bar.wave_stop()
"""
import colorsys
import random
import tkinter as tk


class DominoBar(tk.Canvas):
    def __init__(self, master, segs=20, height=20, bg="#171229", unlit="#3d2f6b", **kw):
        super().__init__(master, height=height, highlightthickness=0, bd=0, bg=bg, **kw)
        self.segs = segs
        self._h = height
        self._unlit = unlit
        self._pct = 0.0
        self._wave = None         # индекс бегущей волны (None → выкл)
        self._spark = -1          # индекс мерцающей плитки (-1 → нет)
        self.bind("<Configure>", lambda e: self._redraw())
        self.after(160, self._spark_tick)

    @staticmethod
    def _hsl(h, s, l):
        r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, max(0.0, min(1.0, l)), s)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

    def _geom(self):
        w = max(self.winfo_width(), 1)
        sk = self._h * 0.28                       # скос (skewX)
        gap = 3
        tw = max(1.0, (w - sk - gap * (self.segs - 1)) / self.segs)
        return sk, gap, tw

    def _tile(self, x, tw, sk, lit, hue, bright):
        h = self._h
        tf = 0.92 if lit else 0.5                 # незаряженная плитка ниже (scaleY .55), прижата вниз
        y0 = h * (1 - tf)
        pts = [x + sk, y0, x + sk + tw, y0, x + tw, h - 1, x, h - 1]
        if lit:
            fill = self._hsl(hue, 0.95, min(0.70, 0.5 * bright))
        else:
            fill = self._unlit
        self.create_polygon(pts, fill=fill, outline="")

    def _redraw(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.delete("all")
        sk, gap, tw = self._geom()
        if self._wave is not None:                # ── волна (установка) ──
            for i in range(self.segs):
                x = i * (tw + gap)
                d = abs(i - self._wave)
                lit = d <= 1
                bright = 1.3 if d == 0 else 1.0
                hue = 150 + 90 * ((self._wave % self.segs) / self.segs)   # сине-зелёная бегущая
                self._tile(x, tw, sk, lit, hue, bright)
            return
        frac = self._pct / 100.0                  # ── детерминированный заряд ──
        lit_n = int(round(frac * self.segs))
        hue = 8 + 197 * frac                       # красный → голубой
        for i in range(self.segs):
            x = i * (tw + gap)
            bright = 1.4 if i == self._spark else 1.0
            self._tile(x, tw, sk, i < lit_n, hue, bright)

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
