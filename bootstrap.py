"""Sleepy — turnkey-лаунчер. Один запуск: проверяет окружение, докачивает зависимости
(в свой venv), показывает pixel-art loading, затем запускает панель Sleepy.

Работает на СИСТЕМНОМ Python (только stdlib: tkinter) — до установки остальных пакетов.
Запускается через Sleepy.bat. Для чайников: 1 клик и всё готово.
"""
import os
import sys
import json
import queue
import threading
import subprocess
import urllib.request
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
VENV = os.path.join(HERE, ".venv")
VENV_PY = os.path.join(VENV, "Scripts", "python.exe")
VENV_PYW = os.path.join(VENV, "Scripts", "pythonw.exe")
REQ = os.path.join(HERE, "requirements.txt")
DEPS_CHECK = "import cv2,mss,pyautogui,numpy,pygetwindow,keyboard,pydirectinput,pytesseract"

# ── Tesseract-OCR (внешний бинарь, нужен для чтения тултипов) ──
CFG_PATH = os.path.join(HERE, "config.json")
TESS_DIR = os.path.join(HERE, ".tesseract")              # локальная установка (без админ-прав)
TESS_EXE = os.path.join(TESS_DIR, "tesseract.exe")
TESS_URL = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
RUS_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/rus.traineddata"
TESS_KNOWN = (TESS_EXE, r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")

sys.path.insert(0, HERE)
try:
    import theme as T
except Exception:
    class T:  # фолбэк-палитра, если theme.py нет
        NIGHT="#171229"; PANEL="#221a3d"; EDGE="#3d2f6b"; INK="#ece8fb"; SUB="#9a8fce"
        FAINT="#6b5fa0"; MOON="#f6e3a1"; STAR="#fff4c2"; GO="#48d98a"; STOPC="#e8615a"
        PIX_FONTS=("Consolas","Courier New")

Q = queue.Queue()   # (kind, payload): ('step',txt) ('done',None) ('fail',txt)
W, H = 460, 340


LOG = os.path.join(HERE, "bootstrap.log")


def _run(cmd):
    """Запустить команду без консольного окна. True если код 0. Вывод -> bootstrap.log (диагностика)."""
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    try:
        r = subprocess.run(cmd, cwd=HERE, creationflags=flags, capture_output=True, text=True)
        try:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write("$ " + " ".join(str(c) for c in cmd) + "\n")
                f.write((r.stdout or "") + (r.stderr or "") + "\n")
        except Exception:
            pass
        return r.returncode == 0
    except Exception as e:
        try:
            open(LOG, "a", encoding="utf-8").write(f"ERR {cmd}: {e}\n")
        except Exception:
            pass
        return False


def _find_tess():
    """Путь к tesseract.exe (конфиг -> локальный -> Program Files) или None."""
    try:
        p = json.load(open(CFG_PATH, encoding="utf-8")).get("ocr", {}).get("tesseract_cmd")
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    for p in TESS_KNOWN:
        if os.path.exists(p):
            return p
    return None


def _set_cfg_tess(path):
    try:
        cfg = json.load(open(CFG_PATH, encoding="utf-8"))
        cfg.setdefault("ocr", {})["tesseract_cmd"] = path
        json.dump(cfg, open(CFG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def _has_rus(tess_exe):
    td = os.path.join(os.path.dirname(tess_exe), "tessdata", "rus.traineddata")
    return os.path.exists(td)


def _dl(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)


def ensure_tesseract():
    """Гарантировать Tesseract-OCR + русский язык. Если нет — СКАЧАТЬ и поставить локально
    (в .tesseract, без админ-прав) + докачать rus.traineddata. Прописать путь в config."""
    tess = _find_tess()
    if tess and _has_rus(tess):
        _set_cfg_tess(tess)
        return True
    Q.put(("step", "ставлю OCR (Tesseract + рус)…\n(первый раз — ~1-2 мин)"))
    os.makedirs(TESS_DIR, exist_ok=True)
    # 1) сам Tesseract (если ещё нет ни локального, ни системного)
    if not tess:
        inst = os.path.join(TESS_DIR, "tess_setup.exe")
        try:
            _dl(TESS_URL, inst)
            _run([inst, "/S", "/D=" + TESS_DIR])   # тихая установка NSIS в локальную папку
        except Exception:
            pass
        tess = TESS_EXE if os.path.exists(TESS_EXE) else _find_tess()
    # 2) русский язык
    if tess and not _has_rus(tess):
        td_dir = os.path.join(os.path.dirname(tess), "tessdata")
        try:
            os.makedirs(td_dir, exist_ok=True)
            _dl(RUS_URL, os.path.join(td_dir, "rus.traineddata"))
        except Exception:
            pass
    if tess and os.path.exists(tess):
        _set_cfg_tess(tess)
        return True
    Q.put(("step", "OCR не поставился — установи Tesseract вручную\n(github.com/UB-Mannheim/tesseract)"))
    return False


def setup_worker():
    """В фоне: venv -> зависимости -> OCR -> запуск панели. Шлёт статусы в Q."""
    Q.put(("step", "проверяю Python…"))
    if not os.path.exists(VENV_PY):
        Q.put(("step", "создаю окружение (venv)…"))
        if not _run([sys.executable, "-m", "venv", VENV]):
            Q.put(("fail", "не удалось создать venv")); return

    Q.put(("step", "проверяю зависимости…"))
    if not _run([VENV_PY, "-c", DEPS_CHECK]):
        Q.put(("step", "докачиваю зависимости…\n(первый раз — пара минут)"))
        # --no-cache-dir: ставим в обход кэша pip. Кэш в %LOCALAPPDATA%\pip иногда встаёт в
        # «доступ запрещён» (битые/залоченные собранные колёса pygetwindow/pyautogui) — тогда
        # установка падала на ровном месте. Без кэша колёса собираются во временную папку.
        PIP = [VENV_PY, "-m", "pip", "install", "--no-cache-dir"]
        _run(PIP + ["--upgrade", "pip"])
        if not _run(PIP + ["-r", REQ]):
            # массовая установка упала — ставим ПОШТУЧНО (один битый пакет не должен валить всё)
            Q.put(("step", "ставлю пакеты по одному…"))
            try:
                pkgs = [l.strip() for l in open(REQ, encoding="utf-8")
                        if l.strip() and not l.strip().startswith("#")]
            except Exception:
                pkgs = []
            for pkg in pkgs:
                _run(PIP + [pkg])
        # успех определяем по ИМПОРТУ ядра, а не по коду pip (pynput опционален)
        if not _run([VENV_PY, "-c", DEPS_CHECK]):
            Q.put(("fail", "не удалось поставить пакеты\nсм. bootstrap.log рядом с программой")); return
        _run(PIP + ["pynput>=1.7"])  # для записи кликера; не критично

    ensure_tesseract()        # OCR-движок + русский (скачает и поставит локально, если нет)

    Q.put(("step", "почти готово…"))
    pyw = VENV_PYW if os.path.exists(VENV_PYW) else VENV_PY
    try:
        subprocess.Popen([pyw, os.path.join(HERE, "control.py")], cwd=HERE)
    except Exception as e:
        Q.put(("fail", f"не запустилась панель: {e}")); return
    Q.put(("done", None))


class Loader:
    def __init__(self, root):
        self.root = root
        self.t = 0
        self.step = "просыпаюсь…"
        self.fail = None
        self.stars = [(37, 41, 7), (110, 28, 5), (300, 36, 6), (400, 60, 5),
                      (60, 90, 5), (420, 120, 6), (28, 150, 5), (390, 175, 5)]
        root.overrideredirect(True)
        root.configure(bg=T.NIGHT)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        root.attributes("-topmost", True)
        self.c = tk.Canvas(root, width=W, height=H, bg=T.NIGHT, highlightthickness=0)
        self.c.pack()
        self._font = self._pick_font()
        # окно ВСЕГДА закрывается: ✕ в углу, Esc, Alt+F4, клик по ✕ (а при ошибке — клик где угодно)
        self.root.bind("<Escape>", lambda e: self._close())
        self.root.bind("<Alt-F4>", lambda e: self._close())
        self.c.bind("<Button-1>", self._click)
        self.root.after(60, self._tick)
        self.root.after(120, self._pump)

    def _close(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)        # гарантированно убить процесс (фоновый воркер — daemon)

    def _click(self, e):
        if e.x >= W - 34 and e.y <= 28:    # клик по ✕
            self._close()
        elif self.fail:                    # при ошибке — клик где угодно закрывает
            self._close()

    def _pick_font(self):
        import tkinter.font as tkf
        fams = set(tkf.families())
        for f in T.PIX_FONTS:
            if f in fams:
                return f
        return "Courier"

    def _px(self, x, y, w, h, col):
        self.c.create_rectangle(x, y, x + w, y + h, fill=col, outline="")

    def _moon(self, cx, cy, r, phase):
        # полная луна с лёгким «дыханием» + кратеры
        glow = T.MOON if phase % 2 == 0 else "#fff0b8"
        self.c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=glow, outline="#d8c477", width=2)
        for dx, dy, rr in ((-6, -4, 4), (5, 2, 3), (-2, 8, 3), (8, -6, 2)):
            self.c.create_oval(cx + dx - rr, cy + dy - rr, cx + dx + rr, cy + dy + rr,
                               fill="#e6d28a", outline="")

    def _tick(self):
        self.t += 1
        self.c.delete("all")
        # звёзды (мерцают)
        for i, (x, y, s) in enumerate(self.stars):
            if (self.t // 6 + i) % 4:
                self._px(x, y, s, s, T.STAR)
        # луна
        self._moon(W // 2, 96, 40, self.t // 10)
        # «zzz» всплывают
        for i, ch in enumerate("zZz"):
            off = (self.t + i * 14) % 42
            self.c.create_text(W // 2 + 44 + i * 14, 70 - off, text=ch,
                               fill=T.MOON, font=(self._font, 10 + i * 3, "bold"))
        # спящий маскот
        self.c.create_text(W // 2, 158, text="(- . -)", fill=T.SUB,
                           font=(self._font, 22, "bold"))
        # title
        self.c.create_text(W // 2, 200, text="GoodNightBot", fill=T.INK,
                           font=(self._font, 24, "bold"))
        self.c.create_text(W // 2, 226, text="smart TBH auto-clicker", fill=T.FAINT,
                           font=(self._font, 9))
        # loading-бар из пиксель-блоков
        n, bw, gap = 12, 22, 4
        total = n * (bw + gap) - gap
        x0 = (W - total) // 2
        lit = (self.t // 3) % (n + 4)
        for i in range(n):
            on = (lit - i) % (n + 4) < 4 and i <= lit
            col = T.MOON if (abs((self.t // 3) % (n + 6) - i) <= 1) else T.EDGE
            self._px(x0 + i * (bw + gap), 256, bw, 10, col)
        # статус
        msg = self.fail if self.fail else self.step
        col = T.STOPC if self.fail else T.SUB
        for j, line in enumerate(msg.split("\n")):
            self.c.create_text(W // 2, 290 + j * 16, text=line, fill=col,
                               font=(self._font, 9))
        # ✕ закрыть — ВСЕГДА в правом верхнем углу (окно без рамки, иначе закрыть нечем)
        self.c.create_text(W - 18, 16, text="✕", fill=T.STOPC, font=(self._font, 13, "bold"))
        if self.fail:
            self.c.create_text(W // 2, H - 40, text="проверь интернет/Python · подробности в bootstrap.log",
                               fill=T.FAINT, font=(self._font, 8))
            # крупная кнопка закрытия
            bw, bh = 150, 22
            bx, by = (W - bw) // 2, H - 30
            self._px(bx, by, bw, bh, T.PANEL)
            self.c.create_text(W // 2, by + bh // 2, text="✕ закрыть", fill=T.STOPC,
                               font=(self._font, 10, "bold"))
        if not self.fail:
            self.root.after(60, self._tick)

    def _pump(self):
        try:
            while True:
                kind, payload = Q.get_nowait()
                if kind == "step":
                    self.step = payload
                elif kind == "fail":
                    self.fail = "упс: " + payload
                elif kind == "done":
                    self.root.after(400, self.root.destroy)
                    return
        except queue.Empty:
            pass
        self.root.after(120, self._pump)


def main():
    root = tk.Tk()
    Loader(root)
    threading.Thread(target=setup_worker, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
