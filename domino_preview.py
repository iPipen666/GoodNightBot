"""Превью домино-бара в цветах темы (без сборки). Запуск:
   python domino_preview.py
"""
import tkinter as tk

import theme as T
from domino_bar import DominoBar

root = tk.Tk()
root.title("DominoBar preview")
root.configure(bg=T.NIGHT)
root.geometry("440x170")
tk.Label(root, text="GoodNightBot — превью прогресс-бара", bg=T.NIGHT, fg=T.MOON,
         font=("Consolas", 13, "bold")).pack(pady=(16, 8))
bar = DominoBar(root, segs=20, height=24, bg=T.NIGHT, lo=T.SUB, hi=T.GO,
                unlit=T.EDGE, spark=T.STAR, wave=T.GO)
bar.pack(fill="x", padx=18)
lbl = tk.Label(root, text="", bg=T.NIGHT, fg=T.SUB, font=("Consolas", 9))
lbl.pack(pady=10)

st = {"p": 0, "mode": "charge"}


def tick():
    if st["mode"] == "charge":
        st["p"] += 2
        bar.set_pct(st["p"])
        lbl.config(text="скачивание %d%%  (лаванда → мятный, искры)" % st["p"])
        if st["p"] >= 100:
            st["mode"] = "wave"
            bar.wave_start()
            lbl.config(text="фаза установки — мятная (GO) волна…")
            root.after(2800, lambda: (bar.wave_stop(), st.update(p=0, mode="charge")))
    root.after(90, tick)


tick()
root.mainloop()
