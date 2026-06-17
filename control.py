"""GoodNightBot — smart TBH auto-clicker. Pixel-art панель управления ночным фармом.

Запуск: GoodNightBot.bat (через bootstrap — проверит окружение и докачает зависимости).
  СТАРТ — будит бота (farm2.run в фоновом потоке).  СТОП / F12 — укладывает спать.
Окно поверх игры, тянется за лунный заголовок. ⚙ настройки · ? помощь · ✕ закрыть.

Лог чистый: только события (дроп/мерж/почта/сундуки/тайник), цветом в тон грейда.
"""
import os
import re
import sys
import json
import time
import ctypes
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox

import farm2
import farm
import state
import hud
import sessionlog
import theme as T
import i18n
from i18n import t, st

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")
ICON_ICO = os.path.join(HERE, "icon.ico")
HW = 425   # ширина панели (+25%)
APP_ID = "SQll.GoodNightBot.1"   # AppUserModelID — иначе таскбар берёт значок pythonw, не наш
# куда вести юзеров (сбор аудитории в наш Telegram). Реальные ссылки — в config.links, это фолбэк.
DEFAULT_LINKS = {"telegram": "https://t.me/+vHGjyYJt1JM0NzNi",
                 "telegram_bot": "https://t.me/taskbar_herobot"}
CTA_FONT = "Saira Condensed"        # бандл-шрифт CTA (fonts/SairaCondensed-BoldItalic.ttf)


def _load_custom_fonts():
    """Подгрузить бандл-шрифты (Saira Condensed для CTA) в сессию Windows — иначе Tk их не видит.
    FR_PRIVATE: шрифт доступен только этому процессу, в систему не ставится."""
    try:
        import ctypes
        fdir = os.path.join(HERE, "fonts")
        for fn in os.listdir(fdir) if os.path.isdir(fdir) else []:
            if fn.lower().endswith((".ttf", ".otf")):
                ctypes.windll.gdi32.AddFontResourceExW(
                    ctypes.c_wchar_p(os.path.join(fdir, fn)), 0x10, 0)
    except Exception:
        pass


_load_custom_fonts()

LOG_Q = queue.Queue()
STAT_Q = queue.Queue()
MODAL_Q = queue.Queue()        # воркер просит показать модалку (текст) → _drain рисует, farm.modal_done()

_GRADE_RE = re.compile("(" + "|".join(T.GRADE.keys()) + ")", re.IGNORECASE)
# все 10 грейдов игры (рус-тиры из items.RANK_TIERS) — галки выбирают, что мержить
MERGE_GRADES = ["обычный", "необычный", "редкий", "легендарный", "бессмертный",
                "аркана", "запредельный", "celestial", "божественный", "космический"]
# безопасный дефолт — мержим только 4 низких, остальное бережём
DEFAULT_MERGE_GRADES = ["обычный", "необычный", "редкий", "легендарный"]
# с какого тира включительно — предупреждать (можно потерять ценное)
_RISKY_FROM = 4   # бессмертный и выше


def load_cfg():
    return json.load(open(CFG_PATH, encoding="utf-8"))


def save_cfg(c):
    json.dump(c, open(CFG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _grade_color(text):
    m = _GRADE_RE.search(text)
    return T.GRADE[m.group(1).lower()] if m else None


def _is_loot(raw):
    """Событие добычи лута (для отдельной вкладки «Лут»): дроп или забранное из почты."""
    low = raw.strip().lower()
    return low.startswith("дроп") or "забрал предметов" in low


def _pretty(raw):
    s = raw.strip()
    low = s.lower()
    NOISE = ("click ", "[ensure", "hero не виден", "фокус", "[save/sort] stash не открыт",
             "[мерж] cube", "dry ", "[shot", "autofill[", "тип-дроп", "режим-дроп",
             "выбрать synthesis", "возврат @", "вкладка ", "stash all", "сортировать @",
             "[решение] merge", "[решение] save", "[решение] open_chest", "[решение] mail")
    if any(n in low for n in NOISE):
        return None
    gc = _grade_color(s)
    if "смержил наборов" in low:
        n = re.search(r"(\d+)", s)
        n = int(n.group(1)) if n else 0
        return (st("✦ синтез: +{n} апгрейд").format(n=n), T.EV["merge"]) if n > 0 else None
    if "[почта] открыл" in low or "[почта] открыт" in low:
        return (st("✉ открыл почту…"), T.EV["mail"])
    if "забрал предметов" in low:
        n = re.search(r"(\d+)", s)
        return (st("✉ почта: забрал {n}").format(n=n.group(1) if n else ""), T.EV["mail"])
    if "[почта] провер" in low:
        return (st("✉ почта: «получить все» ✓"), T.EV["mail"])
    if "[почта]" in low and ("не откр" in low or "пропуск" in low):
        return (st("✉ почта: пропуск"), T.EV["warn"])
    if "сундук" in low:
        return (st("🎁 руна сундуков (Пробел)"), T.EV["chest"])
    if "инвентарь разложен" in low:
        return (st("📦 разложил в тайник"), T.EV["save"])
    if low.startswith("[стэш]"):
        m = re.search(r"вкл\s*(\d+):\s*(\d+)/(\d+)", s)
        return (st("📦 тайник {t}: {a}/{b}").format(t=m.group(1), a=m.group(2), b=m.group(3)),
                T.EV["save"]) if m else None
    if "idle:" in low or "жду лут" in low:
        return (st("💤 жду лут…"), T.EV["idle"])
    if "попап" in low:
        return (st("⚠ закрыл серверный попап"), T.EV["warn"])
    if low.startswith("ошибка") or "traceback" in low:
        return ("✖ " + s[:40], T.EV["err"])
    if "запуск" in low or "просыпа" in low:
        return (st("☾ просыпаюсь…"), T.EV["ok"])
    if low.startswith("готово"):
        return (st("⏸ уснул"), T.SUB)
    if low.startswith("дроп"):
        return ("🔹 " + s, gc or T.SUB)
    # строки прескана содержат МНОГО грейдов — НЕ резать (wrap='word' перенесёт целиком)
    if low.startswith("скан") or low.startswith("инвентарь") or low.startswith("тайник") \
            or low.startswith("персонаж") or low.startswith("ростер"):
        return (s, T.EV.get("save", T.SUB))
    if gc:
        return (s[:46], gc)
    return None


class Panel:
    def __init__(self, root):
        self.root = root
        self.worker = None
        self.stop_evt = threading.Event()
        self._drag = (0, 0)
        self.t = 0
        self.ready = False
        self.mode = "parallel"
        self._ov = None
        self._db = None
        self._help_win = None
        self._pill = None
        self._loot_n = 0
        self.hud = None
        self._build()
        self.hud = None                             # таймер убран — статус идёт в sysbar под кнопкой БД
        self._add_panel_grip()                      # регулировка высоты панели (низ окна)
        self.root.after(60, self._show_in_taskbar)  # кнопка в таскбаре + alt-tab (иначе не найти)
        self.root.after(150, self._animate)
        self.root.after(120, self._drain)
        self.root.after(1600, self._activity_tick)
        self.root.after(4000, self._startup_update_check)   # тихо проверить апдейт → заметное уведомление
        if load_cfg().get("autostart_db", False):   # БД авто-открытие — ВЫКЛ по умолчанию: окно БД
            self.root.after(800, self._autostart_db) # перекрывало плашку лога внизу → счёт читал 0
        farm.set_modal_hook(lambda text: MODAL_Q.put(text))   # воркер сможет просить модалку
        threading.Thread(target=self._selfcheck, daemon=True).start()

    def _font(self, size, bold=False):
        if size < 12:               # слегка крупнее для читабельности
            size += 1
        fams = set(tkfont.families())
        fam = next((f for f in T.PIX_FONTS if f in fams), "Courier")
        return (fam, size, "bold" if bold else "normal")

    def _cta_font(self, size):
        """Шрифт CTA — Saira Condensed Bold Italic (если подгрузился), иначе пиксельный жирный."""
        if CTA_FONT in set(tkfont.families()):
            return (CTA_FONT, size, "bold italic")
        return self._font(size, True)

    # ---------- мелкая кнопка-бейдж в шапке ----------
    def _badge(self, parent, off, text, fg, cmd):
        """Бейдж-кнопка в шапке. off — отступ от ПРАВОГО края (anchor=ne, relx=1.0),
        чтобы значки не вылезали за окно при любой ширине."""
        b = tk.Label(parent, text=text, bg=T.PANEL, fg=fg, font=self._font(10, True),
                     cursor="hand2", padx=5, pady=1)
        b.place(relx=1.0, x=-off, y=6, anchor="ne")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _build(self):
        r = self.root
        r.title("GoodNightBot")
        try:
            r.iconbitmap(ICON_ICO)
        except Exception:
            pass
        r.configure(bg=T.NIGHT)
        r.overrideredirect(True)
        # панель НЕ поверх всех окон (топмост только у таймера). Позиция/высота — запоминаются.
        try:
            geom = load_cfg().get("panel_geom")
        except Exception:
            geom = None
        r.geometry(geom or "+40+40")
        outer = tk.Frame(r, bg=T.EDGE)
        outer.pack(fill="both", expand=True)
        wrap = tk.Frame(outer, bg=T.NIGHT)
        wrap.pack(fill="both", expand=True, padx=2, pady=2)

        self.head = tk.Canvas(wrap, width=HW, height=196, bg=T.NIGHT, highlightthickness=0)
        self.head.pack(fill="x")
        try:
            self._head_img = tk.PhotoImage(file=os.path.join(HERE, "templates", "header.png"))
        except Exception:
            self._head_img = None
        # тайлы живых сцен игры (листаются в шапке); если их нет — статичный header.png
        self._scene_imgs = []
        try:
            import glob as _glob
            for _fp in sorted(_glob.glob(os.path.join(HERE, "templates", "header_scenes", "*.png"))):
                self._scene_imgs.append(tk.PhotoImage(file=_fp))
        except Exception:
            pass
        # готовая плёнка шапки (затемнённая, с кроссфейдами) — крутится по кругу
        self._play = []
        try:
            import glob as _glp
            for _fp in sorted(_glp.glob(os.path.join(HERE, "templates", "header_play", "*.png"))):
                self._play.append(tk.PhotoImage(file=_fp))
        except Exception:
            pass
        # сырые серии по локациям — фолбэк, только если плёнки нет (экономим память)
        self._anim = {}
        if not self._play:
            try:
                import glob as _glob2
                _adir = os.path.join(HERE, "templates", "header_anim")
                if os.path.isdir(_adir):
                    for _loc in sorted(os.listdir(_adir)):
                        _fr = [tk.PhotoImage(file=fp)
                               for fp in sorted(_glob2.glob(os.path.join(_adir, _loc, "*.png")))]
                        if _fr:
                            self._anim[_loc] = _fr
            except Exception:
                pass
        self.head.bind("<Button-1>", self._press)
        self.head.bind("<B1-Motion>", self._move)
        self.head.bind("<ButtonRelease-1>", lambda e: self._save_panel_geom())
        # бейджи (видимые, контрастные)
        # бейджи привязаны к правому краю (off справа): ✕ → ? → ⚙ → — (свернуть)
        self._badge(wrap, 8,  "✕", T.STOPC, self._quit)
        self._badge(wrap, 36, "?", T.INK,   self._help)
        self._badge(wrap, 62, "⚙", T.MOON,  self._settings)
        self._badge(wrap, 90, "—", T.INK,   self._minimize)

        body = tk.Frame(wrap, bg=T.NIGHT)
        body.pack(fill="both", expand=True, padx=12, pady=(2, 8))

        st = tk.Frame(body, bg=T.NIGHT)
        st.pack(fill="x")
        self.dot = tk.Canvas(st, width=18, height=18, bg=T.NIGHT, highlightthickness=0)
        self.dot.pack(side="left")
        self._oval = self.dot.create_oval(3, 3, 15, 15, fill=T.FAINT, outline="")
        self.status = tk.Label(st, text=t("waking"), bg=T.NIGHT, fg=T.SUB,
                               font=self._font(12, True))
        self.status.pack(side="left", padx=6)

        bfr = tk.Frame(body, bg=T.EDGE)
        bfr.pack(fill="x", pady=(8, 6))
        self.btn = tk.Button(bfr, text="ASLEEP…", command=self.toggle,
                             bg=T.PANEL, fg=T.FAINT, activebackground=T.PANEL,
                             relief="flat", font=self._cta_font(17),
                             cursor="hand2", pady=6, bd=0, state="disabled")
        self.btn.pack(fill="x", padx=2, pady=2)

        # ── калибровка: ПРЯМО ПОД START (не в настройках) — заметна когда что-то не готово ──
        cal_bar = tk.Frame(body, bg=T.NIGHT)
        cal_bar.pack(fill="x", pady=(2, 2))
        self._calib_btn = tk.Button(cal_bar, text="⚙ Calibrate", command=self._run_calibration,
                                    bg=T.PANEL, fg=T.MOON, activebackground=T.EDGE_HI,
                                    relief="flat", bd=0, font=self._font(11, True),
                                    cursor="hand2", pady=6)
        self._calib_btn.pack(fill="x", padx=2)
        self._calib_hint = tk.Label(body, text="", bg=T.NIGHT, fg=T.WARN, font=self._font(8),
                                    wraplength=HW - 40, justify="left")
        self._calib_hint.pack(anchor="w", padx=2)
        self.root.after(4500, self._refresh_calib_bar)   # показать статус калибровки после старта

        # ── «Поддержать проект» — 3 фикс-суммы, открывают платёжную ссылку в браузере ──
        # ХАРДКОД-текст (без i18n, не переводится). Ссылки в config.donate.urls; секретов в клиенте нет.
        try:
            _amts = (load_cfg().get("donate", {}) or {}).get("amounts", [99, 499, 999])
        except Exception:
            _amts = [99, 499, 999]
        dfr = tk.Frame(body, bg=T.NIGHT)
        dfr.pack(fill="x", pady=(0, 4))
        tk.Label(dfr, text="Support the project", bg=T.NIGHT, fg=T.MOON,
                 font=self._cta_font(13)).pack(anchor="w", pady=(0, 2))
        drow = tk.Frame(dfr, bg=T.NIGHT)
        drow.pack(fill="x")
        for _a in _amts:
            b = tk.Button(drow, text="%s rub" % _a, command=lambda v=_a: self._donate(v),
                          bg=T.PANEL2, fg=T.MOON, activebackground=T.EDGE_HI,
                          activeforeground=T.STAR, relief="flat", bd=0,
                          font=self._font(10, True), cursor="hand2", pady=5)
            b.pack(side="left", fill="x", expand=True, padx=2)
        # своя сумма (ввод на странице оплаты; минимум 99 — лимит на сервере)
        tk.Button(dfr, text="Custom amount…", command=self._donate_custom,
                  bg=T.PANEL, fg=T.SUB, activebackground=T.EDGE_HI, activeforeground=T.STAR,
                  relief="flat", bd=0, font=self._font(8, True), cursor="hand2",
                  pady=4).pack(fill="x", padx=2, pady=(3, 0))
        # для иностранцев — «спасибо» в Telegram Stars (открывает бота; текст не переводится)
        tk.Button(dfr, text="★  Say thanks in Stars", command=self._donate_stars,
                  bg=T.PANEL, fg=T.SUB, activebackground=T.EDGE_HI, activeforeground=T.STAR,
                  relief="flat", bd=0, font=self._font(8, True), cursor="hand2",
                  pady=4).pack(fill="x", padx=2, pady=(3, 0))

        # ── микро-дашборд: полоса сундуков + 3 тайла (синтез / ценное / материалы) ──
        self._dash, self._dash_lbl = {}, {}

        # -- полоса сундуков: 3 чипа icon+число --
        self._box_imgs = []  # держим refs на PhotoImage, иначе Tk GC уберёт
        chest_strip = tk.Frame(body, bg=T.NIGHT)
        chest_strip.pack(fill="x", pady=(8, 2))
        _box_defs = [
            ("normal",      "normal.png",     "box_normal"),
            ("stage_boss",  "stage_boss.png",  "box_stage"),
            ("act_boss",    "act_boss.png",    "box_act"),
        ]
        for _bk, _bfn, _stat_key in _box_defs:
            chip = tk.Frame(chest_strip, bg=T.PANEL)
            chip.pack(side="left", padx=(0, 3))
            # иконка сундука
            _fp = os.path.join(HERE, "templates", "boxes", _bfn)
            try:
                _img = tk.PhotoImage(file=_fp)
                # уменьшить если слишком большое (32px target)
                _iw, _ih = _img.width(), _img.height()
                if _iw > 36 or _ih > 36:
                    _ss = max(1, max(_iw, _ih) // 32)
                    _img = _img.subsample(_ss, _ss)
                self._box_imgs.append(_img)
                tk.Label(chip, image=_img, bg=T.PANEL).pack(side="left", padx=(3, 1), pady=3)
            except Exception:
                self._box_imgs.append(None)
                tk.Label(chip, text="☐", bg=T.PANEL, fg=T.FAINT,
                         font=self._font(10)).pack(side="left", padx=(3, 1), pady=3)
            num = tk.Label(chip, text="0", bg=T.PANEL, fg=T.MOON, font=self._font(11, True))
            num.pack(side="left", padx=(1, 4), pady=3)
            self._dash[_bk] = num
            # нет отдельного label-ключа для каждого чипа — тип понятен по иконке

        # подпись полосы сундуков
        _chest_lbl = tk.Label(body, text=t("dash_chests"), bg=T.NIGHT, fg=T.FAINT,
                               font=self._font(7))
        _chest_lbl.pack(anchor="w", padx=2, pady=(0, 4))
        self._dash_lbl["chests_label"] = (_chest_lbl, "dash_chests")

        # -- чипы: синтез / ценное / материалы (компактно, как полоса сундуков) --
        self.dash = tk.Frame(body, bg=T.NIGHT)
        self.dash.pack(fill="x", pady=(2, 2))
        # синтез (мержи) · этапы пройдено ✓ · этапы провалено ✗ — ВСЁ из игрового лога (не из
        # старого инвентаря). Раньше «ценное/материалы» считали стоящий в сетке инвентаря лут →
        # вводило в заблуждение (показывало то, что давно лежит). Теперь — лог-driven счётчики сессии.
        for i, (k, lk) in enumerate((("merge", "dash_synthesis"),
                                     ("stages_ok", "dash_stages_ok"),
                                     ("stages_fail", "dash_stages_fail"))):
            chip = tk.Frame(self.dash, bg=T.PANEL)
            chip.pack(side="left", padx=(0, 3))
            lab = tk.Label(chip, text=t(lk), bg=T.PANEL, fg=T.FAINT, font=self._font(7))
            lab.pack(side="left", padx=(5, 2), pady=2)
            num = tk.Label(chip, text="0", bg=T.PANEL, fg=T.MOON, font=self._font(11, True))
            num.pack(side="left", padx=(0, 5), pady=2)
            self._dash[k] = num
            self._dash_lbl[k] = (lab, lk)
        # тонкий прогресс «до следующего действия»
        self.pbar = tk.Canvas(body, height=4, bg=T.EDGE, highlightthickness=0, bd=0)
        self.pbar.pack(fill="x", pady=(3, 0))
        self._pbar_fill = self.pbar.create_rectangle(0, 0, 0, 4, fill=T.MOON, outline="")
        self._wait_max = 0

        # UI всегда английский — селекторов языка на главной нет. Язык переводов БД — в Настройках.
        self.phase = tk.Label(body, text="—", bg=T.NIGHT, fg=T.SUB, font=self._font(8))  # фаза уехала в дашборд/статус-бар (не пакуем)

        # режим — сегмент-тоггл + описание под каждым
        self._lbl_mode = tk.Label(body, text=t("mode"), bg=T.NIGHT, fg=T.FAINT,
                                  font=self._font(8))
        self._lbl_mode.pack(anchor="w", pady=(2, 1))
        seg = tk.Frame(body, bg=T.EDGE)
        seg.pack(fill="x")
        self.mode_btns = {}
        for val, key in (("parallel", "m_parallel"), ("auto", "m_auto")):
            b = tk.Button(seg, text=t(key), command=lambda v=val: self._set_mode(v),
                          relief="flat", bd=0, cursor="hand2", font=self._font(9, True), pady=6)
            b.pack(side="left", fill="x", expand=True, padx=1, pady=1)
            self.mode_btns[val] = b
        self.mdesc = {}
        for val, key in (("parallel", "d_parallel"), ("auto", "d_auto")):
            lb = tk.Label(body, text="• " + t(key), bg=T.NIGHT, fg=T.FAINT,
                          font=self._font(7), wraplength=HW - 30, justify="left")
            lb.pack(anchor="w")
            self.mdesc[val] = lb
        self._set_mode("parallel")

        tk.Frame(body, bg=T.EDGE, height=2).pack(fill="x", pady=4)

        # вкладки лога: Общий / только Лут (дроп слабо виден в общем потоке)
        logtabs = tk.Frame(body, bg=T.NIGHT)
        logtabs.pack(fill="x", pady=(2, 0))
        self.logtab_btns = {}
        for key, lblk in (("all", "tab_all"), ("loot", "tab_loot"), ("sessions", "tab_sessions"),
                          ("hero", "tab_hero"), ("stash", "tab_stash"), ("loot2", "tab_loot2")):
            b = tk.Label(logtabs, text=t(lblk), bg=T.PANEL, fg=T.SUB, padx=2, pady=3,
                         cursor="hand2", font=self._font(8, True), anchor="center")
            b.pack(side="left", fill="x", expand=True, padx=1)
            b.bind("<Button-1>", lambda e, k=key: self._set_logtab(k))
            self.logtab_btns[key] = b

        # ── нижняя группа: закреплена СНИЗУ (не исчезает при сжатии окна по высоте) ──
        cr = tk.Label(body, text="Created by SQll", bg=T.NIGHT, fg=T.FAINT, font=self._font(8))
        cr.pack(side="bottom", pady=(2, 0))
        # строка версии + ручная проверка обновлений (клиент обновляемый; сервер задаётся в config.update.api)
        verrow = tk.Frame(body, bg=T.NIGHT)
        verrow.pack(side="bottom", fill="x")
        self.ver_lbl = tk.Label(verrow, text="v" + self._app_version(), bg=T.NIGHT,
                                fg=T.FAINT, font=self._font(7))
        self.ver_lbl.pack(side="left", padx=(4, 0))
        self.upd_lbl = tk.Label(verrow, text=t("upd_check"), bg=T.NIGHT, fg=T.MOON,
                                font=self._font(7), cursor="hand2")
        self.upd_lbl.pack(side="right", padx=(0, 4))
        self.upd_lbl.bind("<Button-1>", lambda e: self._check_updates())
        # ── CTA «вступай в наш Telegram» — золотой акцентный блок, заманиваем в сообщество ──
        self.tg_wrap = tk.Frame(body, bg=T.MOON, cursor="hand2")
        self.tg_wrap.pack(side="bottom", fill="x", padx=2, pady=(3, 0))
        self.tg_btn = tk.Label(self.tg_wrap, text=t("tg_btn"), bg=T.MOON, fg=T.GO_INK,
                               font=self._cta_font(15), cursor="hand2")
        self.tg_btn.pack(fill="x", pady=(5, 0))
        self.tg_sub = tk.Label(self.tg_wrap, text=t("tg_sub"), bg=T.MOON, fg="#6e5c22",
                               font=self._font(8), cursor="hand2")
        self.tg_sub.pack(fill="x", pady=(0, 5))

        def _tg_hover(on):
            c = T.STAR if on else T.MOON
            for _w in (self.tg_wrap, self.tg_btn, self.tg_sub):
                _w.config(bg=c)
        for _w in (self.tg_wrap, self.tg_btn, self.tg_sub):
            _w.bind("<Button-1>", lambda e: self._open_link("telegram"))
            _w.bind("<Enter>", lambda e: _tg_hover(True))
            _w.bind("<Leave>", lambda e: _tg_hover(False))
        # ── карусель активности: что бот делает СЕЙЧАС (Saira, как CTA) + следующий шаг (полупрозрачно) ──
        self._act_i = 0
        actfr = tk.Frame(body, bg=T.PANEL)
        actfr.pack(side="bottom", fill="x", pady=(4, 2))
        self.act_now = tk.Label(actfr, text="ready for the night", bg=T.PANEL, fg=T.MOON,
                                font=self._cta_font(12), anchor="w", padx=8, pady=0)
        self.act_now.pack(fill="x", pady=(5, 0))
        self.act_next = tk.Label(actfr, text="", bg=T.PANEL, fg=T.FAINT,
                                 font=self._cta_font(9), anchor="w", padx=8, pady=0)
        self.act_next.pack(fill="x", pady=(0, 5))
        self.sysbar = self.act_now      # совместимость: статус/системные сообщения → текущая строка
        # кнопка «База знаний» ПОД логом — закреплена снизу, всегда видна
        self.db_glow = tk.Frame(body, bg=T.EDGE)
        self.db_glow.pack(side="bottom", fill="x")
        self.db_btn = tk.Label(self.db_glow, text=t("db_btn"), bg=T.PANEL2,
                               fg=T.MOON, font=self._cta_font(13), cursor="hand2", pady=7)
        self.db_btn.pack(fill="x", padx=2, pady=2)
        self.db_btn.bind("<Button-1>", lambda e: self._open_db())
        self._lbl_f12 = tk.Label(body, text=t("f12"), bg=T.NIGHT, fg=T.FAINT, font=self._font(7))
        self._lbl_f12.pack(side="bottom", anchor="w", pady=(4, 1))

        logwrap = tk.Frame(body, bg=T.EDGE)
        logwrap.pack(side="top", fill="both", expand=True, pady=(2, 0))
        mk = lambda: tk.Text(logwrap, height=34, width=38, bg="#120e22", fg=T.SUB,
                             relief="flat", font=self._font(9), wrap="word",
                             state="disabled", padx=7, pady=5, spacing1=1, bd=0)
        self.log = mk()          # общий
        self.log_loot = mk()     # только лут (дроп)
        self._make_copyable(self.log)
        self._make_copyable(self.log_loot)
        # вкладка «Сессии»: выбор даты + журнал
        self.f_sessions = tk.Frame(logwrap, bg=T.EDGE)
        topr = tk.Frame(self.f_sessions, bg=T.NIGHT); topr.pack(fill="x")
        self._lbl_date = tk.Label(topr, text=t("date"), bg=T.NIGHT, fg=T.FAINT,
                                  font=self._font(8))
        self._lbl_date.pack(side="left", padx=(4, 4), pady=2)
        self._sess_date = tk.StringVar(value="—")
        self._sess_om = tk.OptionMenu(topr, self._sess_date, "—")
        self._sess_om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                             relief="flat", bd=0, highlightthickness=0, font=self._font(8), cursor="hand2")
        self._sess_om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2,
                                     activeforeground=T.MOON, font=self._font(8), bd=0)
        self._sess_om.pack(side="left")
        self.log_sessions = tk.Text(self.f_sessions, bg="#120e22", fg=T.SUB, relief="flat",
                                    font=self._font(9), wrap="word", state="disabled",
                                    padx=7, pady=5, bd=0)
        self.log_sessions.pack(fill="both", expand=True, pady=(2, 0))
        self._make_copyable(self.log_sessions)

        # ── вкладка HERO: герои + инвентарь (grade-colored, scrollable) ──
        self.f_hero = tk.Frame(logwrap, bg=T.NIGHT)
        self._build_hero_tab(self.f_hero)

        # ── вкладка STASH: sub-tabs по вкладкам тайника ──
        self.f_stash = tk.Frame(logwrap, bg=T.NIGHT)
        self._build_stash_tab(self.f_stash)

        # ── вкладка LOOT2: аккордеон по категориям дропа текущего этапа ──
        self.f_loot2 = tk.Frame(logwrap, bg=T.NIGHT)
        self._build_loot2_tab(self.f_loot2)

        self._photo_refs = []   # держим PhotoImage от GC

        self._tags = {}
        self._tags_loot = {}
        self._set_logtab("all")

    def _on_panel_lang(self, label):
        """Смена языка БД/имён прямо с панели — сразу, без перезапуска."""
        code = self._panel_l2c.get(label)
        if not code:
            return
        try:
            c = load_cfg(); c["lang_main"] = code; save_cfg(c)
        except Exception:
            pass
        if self._db:
            try:
                self._db.set_language(code)      # live-перерисовка БД
            except Exception:
                pass
        if self._help_win is not None:
            try:
                if self._help_win.win.winfo_exists():
                    self._help_win.set_language(code)  # live-перерисовка справки
            except Exception:
                pass
        try:
            farm.reload_config()                 # лут-лог берёт имена на новом языке
        except Exception:
            pass
        self._refresh_ui()                       # live-перерисовка UI-строк панели

    def _on_panel_translate(self, label):
        """Смена языка перевода-оверлея БД прямо с панели — сразу, без перезапуска."""
        c = load_cfg()
        if label == "—":
            c["translate_enabled"] = False
            save_cfg(c)
            if self._db:
                try:
                    self._db.set_translate(None)
                except Exception:
                    pass
            return
        code = self._panel_l2c.get(label)
        if not code:
            return
        c["translate_enabled"] = True
        c["lang_translate"] = code
        save_cfg(c)
        if self._db:
            try:
                self._db.set_translate(code)
            except Exception:
                pass

    def _refresh_ui(self):
        """Перерисовать локализуемые строки панели на текущем языке (live, без перезапуска)."""
        try:
            self._lbl_mode.config(text=t("mode"))
            self._lbl_f12.config(text=t("f12"))
            self.db_btn.config(text=t("db_btn"))
            self.tg_btn.config(text=t("tg_btn"))
            self.tg_sub.config(text=t("tg_sub"))
            self.upd_lbl.config(text=t("upd_check"))
            self._lbl_date.config(text=t("date"))
            self.mode_btns["parallel"].config(text=t("m_parallel"))
            self.mode_btns["auto"].config(text=t("m_auto"))
            self.mdesc["parallel"].config(text="• " + t("d_parallel"))
            self.mdesc["auto"].config(text="• " + t("d_auto"))
            self.logtab_btns["all"].config(text=t("tab_all"))
            self.logtab_btns["loot"].config(text=t("tab_loot"))
            self.logtab_btns["sessions"].config(text=t("tab_sessions"))
            self.logtab_btns["hero"].config(text=t("tab_hero"))
            self.logtab_btns["stash"].config(text=t("tab_stash"))
            self.logtab_btns["loot2"].config(text=t("tab_loot2"))
            for lab, lk in getattr(self, "_dash_lbl", {}).values():
                lab.config(text=t(lk))
            self._running_ui(self._alive())      # кнопка/статус — локализованно по состоянию
        except Exception:
            pass

    # ---------- шапка: цельный пиксель-арт баннер кладбища + заголовок поверх ----------
    def _animate(self):
        if getattr(self, "_resizing", False):       # во время ресайза не перерисовываем шапку (без ряби)
            self.root.after(33, self._animate)
            return
        self.t += 1
        c = self.head
        c.delete("all")
        if self._play:                              # готовая плёнка (затемнённая, кроссфейды)
            c.create_image(0, 0, anchor="nw", image=self._play[int(self.t / 1.5) % len(self._play)])
        elif self._anim:                            # фолбэк: сырые серии по локациям
            locs = sorted(self._anim)
            HOLD = 240
            loc = locs[(self.t // HOLD) % len(locs)]
            fr = self._anim[loc]
            c.create_image(0, 0, anchor="nw", image=fr[self.t % len(fr)])
        else:
            imgs = self._scene_imgs or ([self._head_img] if self._head_img else [])
            if imgs:
                c.create_image(0, 0, anchor="nw", image=imgs[(self.t // 25) % len(imgs)])
            else:
                c.create_rectangle(0, 0, HW, 196, fill=T.NIGHT, outline="")

        # шапка = полный логотип TBH TASK BAR HERO (горящие буквы) — поверх НИЧЕГО не рисуем,
        # чтобы логотип был виден целиком (текст/звёзды убраны).

        # плавное «дыхание» рамки кнопки «База знаний» (треугольная волна, без мигания)
        if hasattr(self, "db_glow"):
            p = self.t % 24
            k = p / 12 if p < 12 else (24 - p) / 12     # 0→1→0 плавно
            self.db_glow.config(bg=self._lerp(T.EDGE, T.EDGE_HI, k))
        self.root.after(16, self._animate)          # ~60fps как в игре

    @staticmethod
    def _lerp(a, b, t):
        """Линейная интерполяция двух hex-цветов (#rrggbb) по t∈[0,1]."""
        a = a.lstrip("#"); b = b.lstrip("#")
        return "#%02x%02x%02x" % tuple(
            int(int(a[i:i+2], 16) + (int(b[i:i+2], 16) - int(a[i:i+2], 16)) * t)
            for i in (0, 2, 4))

    def _selfcheck(self):
        import time
        for stp in (t("sc_templates"), t("sc_window"), t("sc_ready")):
            LOG_Q.put(("__status__", stp)); time.sleep(0.5)
        win = None
        try:
            win = farm.fw()
        except Exception:
            pass
        LOG_Q.put(("__ready__", bool(win)))

    def _press(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _make_copyable(self, w):
        """Лог можно выделять и копировать (Ctrl+C / Ctrl+A / правый клик), хоть он read-only."""
        def _copy(_=None):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(w.get("sel.first", "sel.last"))
            except Exception:
                pass
            return "break"

        def _all(_=None):
            w.tag_add("sel", "1.0", "end-1c")
            return "break"
        w.bind("<Button-1>", lambda e: w.focus_set(), add="+")
        w.bind("<Control-c>", _copy)
        w.bind("<Control-C>", _copy)
        w.bind("<Control-a>", _all)
        w.bind("<Control-A>", _all)
        menu = tk.Menu(w, tearoff=0, bg=T.PANEL, fg=T.INK,
                       activebackground=T.PANEL2, activeforeground=T.MOON)
        menu.add_command(label="Копировать", command=_copy)
        menu.add_command(label="Выделить всё", command=_all)
        w.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _show_in_taskbar(self):
        """Показать borderless-панель в ТАСКБАРЕ и alt-tab (overrideredirect-окно само туда не
        попадает — иначе панель не найти). Win32: снять TOOLWINDOW, выставить APPWINDOW."""
        try:
            GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = -20, 0x00040000, 0x00000080
            u = ctypes.windll.user32
            hwnd = u.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            style = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
            self.root.withdraw()                    # переустановка — чтобы кнопка появилась
            self.root.after(12, self.root.deiconify)
            self.root.after(60, self._apply_taskbar_icon)
        except Exception:
            pass

    def _apply_taskbar_icon(self):
        """Поставить наш значок на кнопку в таскбаре (WM_SETICON по HICON из icon.ico).
        Для overrideredirect-окна надёжнее, чем iconbitmap — Tk иначе показывает значок pythonw."""
        try:
            if not os.path.exists(ICON_ICO):
                return
            u = ctypes.windll.user32
            hwnd = u.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            LR = 0x00000010 | 0x00000040            # LR_LOADFROMFILE | LR_DEFAULTSIZE
            big = u.LoadImageW(0, ICON_ICO, 1, 0, 0, LR)      # IMAGE_ICON=1
            small = u.LoadImageW(0, ICON_ICO, 1, 16, 16, 0x00000010)
            WM_SETICON = 0x0080
            if big:
                u.SendMessageW(hwnd, WM_SETICON, 1, big)      # ICON_BIG
            if small:
                u.SendMessageW(hwnd, WM_SETICON, 0, small)    # ICON_SMALL
        except Exception:
            pass

    def _save_panel_geom(self):
        """Запомнить позицию/высоту панели (восстановится при следующем запуске)."""
        try:
            c = load_cfg()
            c["panel_geom"] = self.root.winfo_geometry()
            save_cfg(c)
        except Exception:
            pass

    def _move(self, e):
        nx, ny = e.x_root - self._drag[0], e.y_root - self._drag[1]
        self.root.geometry(f"+{nx}+{ny}")
        # БД «прикреплена» → едет за панелью
        if self._db is not None:
            try:
                if self._db.win.winfo_exists():
                    self._db.follow(nx, ny)
            except Exception:
                pass

    # ---------- регулировка высоты панели ----------
    def _add_panel_grip(self):
        grip = tk.Frame(self.root, bg=T.EDGE_HI, height=7, cursor="sb_v_double_arrow")
        grip.place(relx=0.0, rely=1.0, anchor="sw", relwidth=1.0, height=7)
        grip.bind("<Button-1>", self._prz_press)
        grip.bind("<B1-Motion>", self._prz_drag)
        grip.bind("<ButtonRelease-1>", self._prz_release)

    def _prz_press(self, e):
        self._prz = (e.y_root, self.root.winfo_height())
        self._resizing = True          # заморозить анимацию шапки → ресайз без ряби/разрывов

    def _prz_drag(self, e):
        nh = max(420, self._prz[1] + (e.y_root - self._prz[0]))
        self.root.geometry(f"{HW}x{int(nh)}+{self.root.winfo_x()}+{self.root.winfo_y()}")

    def _prz_release(self, e):
        self._resizing = False
        self._save_panel_geom()

    def _alive(self):
        return bool(self.worker and self.worker.is_alive())

    def _set_mode(self, val):
        self.mode = val
        # активный сегмент = заметная заливка-акцент под смысл режима (CTA), неактивный — тусклый
        acc = {"parallel": (T.EDGE_HI, T.INK), "auto": (T.WARN, "#2a1e06")}
        for v, b in self.mode_btns.items():
            on = v == val
            bg, fg = acc.get(v, (T.PANEL2, T.MOON)) if on else (T.PANEL, T.FAINT)
            b.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
        for v, lb in self.mdesc.items():
            lb.config(fg=(T.INK if v == val else T.FAINT))

    # ---------- сворачивание в мини-пилюлю ----------
    def _minimize(self):
        if self._pill is not None:
            return
        try:
            self.root.update_idletasks()
            gx, gy = self.root.winfo_x(), self.root.winfo_y()
            self._restore_geom = self.root.winfo_geometry()   # WxH+X+Y — сохранить высоту
        except Exception:
            gx, gy = 40, 40
            self._restore_geom = None
        self._restore_geo = (gx, gy)
        self._db_was_open = bool(self._db and self._db.win.winfo_exists())
        if self._db_was_open:
            try:
                self._db.win.withdraw()
            except Exception:
                pass
        self.root.withdraw()
        p = tk.Toplevel(self.root)
        self._pill = p
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=T.EDGE)
        p.geometry(f"+{gx}+{gy}")
        inner = tk.Frame(p, bg=T.NIGHT)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        lbl = tk.Label(inner, text="🌙 GNB", bg=T.NIGHT, fg=T.MOON,
                       font=self._font(12, True), cursor="hand2", padx=14, pady=7)
        lbl.pack()
        for w in (p, inner, lbl):
            w.bind("<Button-1>", lambda e: self._restore_from_pill())

    def _restore_from_pill(self):
        if self._pill is not None:
            try:
                self._pill.destroy()
            except Exception:
                pass
            self._pill = None
        gx, gy = getattr(self, "_restore_geo", (40, 40))
        self.root.deiconify()
        self.root.overrideredirect(True)        # панель НЕ topmost (поверх — только таймер)
        geom = getattr(self, "_restore_geom", None)
        self.root.geometry(geom if geom else f"+{gx}+{gy}")
        if getattr(self, "_db_was_open", False) and self._db is not None:
            try:
                self._db.win.deiconify()
            except Exception:
                pass

    # ---------- модалки ----------
    def _overlay(self, title):
        if self._ov is not None:
            self._ov.destroy()
        ov = tk.Frame(self.root, bg=T.NIGHT, highlightbackground=T.EDGE, highlightthickness=2)
        ov.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._ov = ov
        top = tk.Frame(ov, bg=T.NIGHT)
        top.pack(fill="x")
        tk.Label(top, text=title, bg=T.NIGHT, fg=T.MOON,
                 font=self._font(13, True)).pack(side="left", padx=14, pady=(14, 6))
        x = tk.Label(top, text="✕", bg=T.NIGHT, fg=T.STOPC, font=self._font(12, True),
                     cursor="hand2")
        x.pack(side="right", padx=12, pady=(12, 0))
        x.bind("<Button-1>", lambda e: self._close_ov())
        return ov

    def _close_ov(self):
        if getattr(self, "_wheel_bound", False):
            try:
                self.root.unbind_all("<MouseWheel>")   # вернуть колесо логам/БД
            except Exception:
                pass
            self._wheel_bound = False
        if self._ov is not None:
            self._ov.destroy(); self._ov = None

    def _open_db(self):
        """ТОГГЛ браузера БД: открыт → закрыть, закрыт → открыть. Высота = высоте панели."""
        try:
            import db_browser
            if getattr(self, "_db", None) is not None and self._db.win.winfo_exists():
                self._db.win.destroy()     # повторный клик — закрыть
                self._db = None
                return
            self.root.update_idletasks()
            h = max(self.root.winfo_height(), 480)   # подогнать под высоту панели
            self._db = db_browser.open_browser(self.root, height=h)
        except Exception as e:
            LOG_Q.put(f"ОШИБКА: БД не открылась: {e}")

    def _autostart_db(self):
        """Открыть БД сразу при запуске бота (просьба пользователя)."""
        try:
            self._open_db()
        except Exception:
            pass

    # ───────────────────── Telegram / обновления ─────────────────────
    @staticmethod
    def _app_version():
        try:
            import updater
            return updater._current()
        except Exception:
            return "1.0.0"

    def _open_link(self, which):
        """Открыть внешнюю ссылку (наш Telegram и т.п.) в браузере/клиенте."""
        import webbrowser
        try:
            links = load_cfg().get("links", {})
        except Exception:
            links = {}
        url = links.get(which) or DEFAULT_LINKS.get(which)
        if not url:
            return
        try:
            webbrowser.open(url)
            if hasattr(self, "sysbar"):
                self.sysbar.config(text=t("tg_opened"))
        except Exception as e:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text=str(e))

    def _donate(self, amount):
        """Открыть платёжную ссылку для суммы (config.donate.urls[amount]) в браузере.
        Никаких платёжных секретов в клиенте — только готовая статическая ссылка. Текст не переводится."""
        import webbrowser
        try:
            urls = (load_cfg().get("donate", {}) or {}).get("urls", {}) or {}
        except Exception:
            urls = {}
        url = urls.get(str(amount)) or urls.get(amount)
        if not url:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text="ссылка оплаты ещё не настроена")
            return
        try:
            webbrowser.open(url)
            if hasattr(self, "sysbar"):
                self.sysbar.config(text="спасибо! открываю оплату…")
        except Exception as e:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text=str(e))

    def _donate_custom(self):
        """Открыть страницу доната со СВОЕЙ суммой (минимум 99 ₽ — лимит на стороне сервера)."""
        import webbrowser
        try:
            url = (load_cfg().get("donate", {}) or {}).get("custom_url", "")
        except Exception:
            url = ""
        if not url:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text="ссылка оплаты ещё не настроена")
            return
        try:
            webbrowser.open(url)
            if hasattr(self, "sysbar"):
                self.sysbar.config(text="спасибо! открываю оплату…")
        except Exception as e:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text=str(e))

    def _donate_stars(self):
        """Открыть Telegram-бота для «спасибо» звёздами (для иностранцев). config.donate.stars_url."""
        import webbrowser
        try:
            url = (load_cfg().get("donate", {}) or {}).get("stars_url", "")
        except Exception:
            url = ""
        if not url:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text="Stars link not set up yet")
            return
        try:
            webbrowser.open(url)
            if hasattr(self, "sysbar"):
                self.sysbar.config(text="opening Telegram Stars…")
        except Exception as e:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text=str(e))

    def _check_updates(self):
        """Ручная проверка обновлений. Вся анимация/результат живут НА КНОПКЕ (upd_lbl), не лезут
        в общую карусель статусов: click → «checking…» (бегущие точки) → результат держится 8с → назад."""
        if getattr(self, "_upd_busy", False):
            return
        self._upd_busy = True
        self._upd_anim_n = 0
        self._upd_anim()                              # запустить бегущие точки
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _upd_anim(self):
        if not getattr(self, "_upd_busy", False):
            return
        try:
            base = t("upd_checking").rstrip(".… ")
            self._upd_anim_n = (self._upd_anim_n + 1) % 4
            self.upd_lbl.config(text=base + "." * self._upd_anim_n, fg=T.MOON)
        except Exception:
            pass
        self.root.after(350, self._upd_anim)

    def _check_updates_worker(self):
        try:
            import updater
            if updater._manifest() is None:          # сервер недоступен / офлайн
                self.root.after(0, lambda: self._upd_done(t("upd_offline")))
                return
            m = updater.check()                       # валидная новее + подпись
            if not m:
                cur = updater._current()
                self.root.after(0, lambda: self._upd_done(t("upd_latest", v=cur)))
                return
            ver = m.get("version")
            self.root.after(0, lambda: self.upd_lbl.config(text=t("upd_found", v=ver), fg=T.MOON))
            ok, msg = updater.download_and_apply(m)
            self.root.after(0, lambda: self._upd_done(msg))
        except Exception as e:
            self.root.after(0, lambda: self._upd_done(t("upd_err", e=e)))

    def _upd_done(self, msg):
        """Стоп анимации, показать результат на кнопке 8с, затем вернуть «check updates»."""
        self._upd_busy = False
        try:
            self.upd_lbl.config(text=msg, fg=T.MOON)
            self.root.after(8000, lambda: self.upd_lbl.config(text=t("upd_check"), fg=T.MOON)
                            if not getattr(self, "_upd_busy", False) else None)
        except Exception:
            pass

    # ── проактивное уведомление об апдейте (для юзеров с EXE) ──
    def _startup_update_check(self):
        """При старте тихо проверить апдейт; если есть — ПРЕВРАТИТЬ ссылку в заметное уведомление
        (сами НЕ ставим — юзер решает). Так юзеры с EXE узнают о новой версии без ручной проверки.
        Юзеры open-source обновляются через git — им сервер latest.json не отдаёт новее."""
        if getattr(self, "_upd_busy", False):
            return
        threading.Thread(target=self._startup_update_worker, daemon=True).start()

    def _startup_update_worker(self):
        try:
            import updater
            m = updater.check()                       # валидная новее + подпись
        except Exception:
            m = None
        if m:
            self._pending_update = m
            self.root.after(0, self._show_update_badge)

    def _show_update_badge(self):
        m = getattr(self, "_pending_update", None)
        if not m:
            return
        self.upd_lbl.config(text="update v%s !" % m.get("version"), fg=T.GO)
        self.upd_lbl.unbind("<Button-1>")
        self.upd_lbl.bind("<Button-1>", lambda e: self._apply_pending_update())

    def _apply_pending_update(self):
        """Установить ожидающий апдейт — с предупреждением про разовую калибровку новой версии."""
        m = getattr(self, "_pending_update", None)
        if not m:
            return self._check_updates()
        msg = ("Обновить до v%s?\n\nПанель скачает и тихо установит обновление, затем попросит "
               "перезапуститься. Калибровка и настройки сохранятся." % m.get("version"))
        notes = (m.get("notes") or "").strip()
        if notes:
            msg += "\n\n" + notes
        if not messagebox.askyesno("Update available", msg, parent=self.root):
            return
        self._upd_busy = True
        self._upd_anim_n = 0
        self._upd_anim()

        def work():
            import updater
            ok, rmsg = updater.download_and_apply(m)
            self.root.after(0, lambda: self._upd_done(rmsg))
        threading.Thread(target=work, daemon=True).start()

    def _help(self):
        try:
            import help_window
            if (self._help_win is not None
                    and self._help_win.win.winfo_exists()):
                self._help_win.win.destroy()
                self._help_win = None
                return
            self.root.update_idletasks()
            h = max(self.root.winfo_height(), 480)
            self._help_win = help_window.open_help(self.root, height=h)
        except Exception as e:
            LOG_Q.put(f"ОШИБКА: Справка не открылась: {e}")

    # ───────────────────── страница настроек (вкладки) ─────────────────────
    SETTAGS = [("beh", "Поведение"), ("scan", "Сканы/OCR"), ("hum", "Хуманлайк"),
               ("pol", "Вежливость"), ("mail", "Почта"), ("lang", "Язык/БД"),
               ("hop", "Stage hop"), ("custom", "Свой конфиг")]

    @staticmethod
    def _cfg_get(c, path, default=None):
        cur = c
        for p in path.split("."):
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    @staticmethod
    def _cfg_set(c, path, val):
        parts = path.split("."); cur = c
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = val

    def _s_section(self, parent, title):
        tk.Label(parent, text=st(title), bg=T.NIGHT, fg=T.MOON, wraplength=HW - 78,
                 justify="left", font=self._font(10, True)).pack(anchor="w", pady=(10, 2))

    def _s_hint(self, parent, text):
        # wraplength занижен под реальную ширину области прокрутки (минус скроллбар+отступы),
        # иначе длинный хинт обрезается справа.
        tk.Label(parent, text=st(text), bg=T.NIGHT, fg=T.FAINT, font=self._font(8),
                 wraplength=HW - 78, justify="left").pack(anchor="w")

    def _s_toggle(self, parent, label, path, default, hint=None, fg=None):
        v = tk.BooleanVar(value=bool(self._cfg_get(self._cfg, path, default)))
        self._cfgvars[path] = ("bool", v)
        self._defaults[path] = default
        tk.Checkbutton(parent, text=st(label), variable=v, bg=T.NIGHT, fg=fg or T.INK,
                       selectcolor=T.EDGE, activebackground=T.NIGHT, activeforeground=T.INK,
                       font=self._font(10), anchor="w", wraplength=HW - 80,
                       justify="left").pack(fill="x", pady=1)
        if hint:
            self._s_hint(parent, hint)

    def _s_num(self, parent, label, path, default, kind="int", hint=None):
        v = tk.StringVar(value=str(self._cfg_get(self._cfg, path, default)))
        self._cfgvars[path] = (kind, v)
        self._defaults[path] = default
        row = tk.Frame(parent, bg=T.NIGHT); row.pack(fill="x", pady=2)
        tk.Label(row, text=st(label), bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                 anchor="w", wraplength=HW - 110, justify="left").pack(side="left")
        tk.Entry(row, textvariable=v, width=6, bg=T.PANEL, fg=T.INK, insertbackground=T.MOON,
                 relief="flat", font=self._font(10), bd=0, justify="right").pack(side="right", ipady=3, ipadx=4)
        if hint:
            self._s_hint(parent, hint)

    def _s_slider(self, parent, label, path, lo, hi, default, step=1, hint=None):
        cur = self._cfg_get(self._cfg, path, default)
        v = tk.IntVar(value=int(cur))
        self._cfgvars[path] = ("int", v)
        self._defaults[path] = default
        row = tk.Frame(parent, bg=T.NIGHT); row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text=st(label), bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                 anchor="w").pack(side="left")
        tk.Label(row, textvariable=v, bg=T.NIGHT, fg=T.MOON,
                 font=self._font(11, True)).pack(side="right")
        tk.Scale(parent, from_=lo, to=hi, orient="horizontal", variable=v, resolution=step,
                 showvalue=False, bg=T.NIGHT, fg=T.INK, troughcolor=T.EDGE, highlightthickness=0,
                 bd=0, sliderrelief="flat", activebackground=T.MOON, cursor="hand2",
                 length=HW - 60).pack(fill="x")
        if hint:
            self._s_hint(parent, hint)

    def _s_dropdown(self, parent, label, path, choices, default, hint=None):
        v = tk.StringVar(value=str(self._cfg_get(self._cfg, path, default)))
        self._cfgvars[path] = ("str", v)
        self._defaults[path] = default
        row = tk.Frame(parent, bg=T.NIGHT); row.pack(fill="x", pady=2)
        tk.Label(row, text=st(label), bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                 anchor="w").pack(side="left")
        om = tk.OptionMenu(row, v, *choices)
        om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                  relief="flat", bd=0, highlightthickness=0, font=self._font(10), cursor="hand2")
        om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2,
                          activeforeground=T.MOON, font=self._font(10), bd=0)
        om.pack(side="right")
        if hint:
            self._s_hint(parent, hint)

    def _s_list(self, parent, label, path, hint=None):
        val = self._cfg_get(self._cfg, path, []) or []
        v = tk.StringVar(value=", ".join(str(x) for x in val))
        self._cfgvars[path] = ("list", v)
        self._defaults[path] = []
        tk.Label(parent, text=st(label), bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                 anchor="w").pack(anchor="w", pady=(2, 0))
        tk.Entry(parent, textvariable=v, bg=T.PANEL, fg=T.INK, insertbackground=T.MOON,
                 relief="flat", font=self._font(10), bd=0).pack(fill="x", ipady=3)
        if hint:
            self._s_hint(parent, hint)

    def _settings(self):
        """Простой экран настроек — только главное. Всё остальное — под кнопкой Advanced."""
        if self._ov is not None:
            return self._close_ov()
        self._cfg = load_cfg()
        self._cfgvars = {}
        self._gvars = {}
        self._defaults = {}
        ov = self._overlay("Settings")
        btns = tk.Frame(ov, bg=T.NIGHT); btns.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
        tk.Button(btns, text="Save ✓", command=self._save_settings, bg=T.GO, fg=T.GO_INK,
                  relief="flat", bd=0, font=self._cta_font(14), pady=8, cursor="hand2").pack(fill="x")
        tk.Button(btns, text="↺ reset to defaults", command=self._reset_defaults, bg=T.PANEL,
                  fg=T.SUB, relief="flat", bd=0, font=self._font(9, True), pady=5,
                  cursor="hand2").pack(fill="x", pady=(4, 0))
        body = tk.Frame(ov, bg=T.NIGHT); body.pack(fill="both", expand=True, padx=16, pady=6)
        self._s_toggle(body, "Auto-synthesis (cube)", "policy.merge_enabled", False,
                       "Merge low-grade items into stronger ones. OFF = never touch the cube (safest).",
                       fg=T.MOON)
        self._s_toggle(body, "Collect mail", "state.mail_enabled", True)
        self._s_toggle(body, "Protect valuables", "policy.log_prelock", True,
                       "Locks jewelry & Immortal+ before merging — keep ON.")
        # язык перевода БД (UI всегда английский)
        try:
            import db_browser as _dbm
            _locs = list(_dbm.LOCALES); _labs = [_dbm.LANG_LABELS.get(c, c) for c in _locs]
            _LL = dict(_dbm.LANG_LABELS)
        except Exception:
            _locs, _labs, _LL = ["ru-RU", "en-US"], ["Русский", "English"], {"ru-RU": "Русский", "en-US": "English"}
        self._lang_l2c = dict(zip(_labs, _locs))
        self._lang_main_var = tk.StringVar(value=_LL.get("en-US", "English"))   # UI фиксирован EN
        self._s_section(body, "Database translation")
        self._lang_tr_on = tk.BooleanVar(value=bool(self._cfg.get("translate_enabled", True)))
        tk.Checkbutton(body, text="show item names translated", variable=self._lang_tr_on,
                       bg=T.NIGHT, fg=T.EV["mail"], selectcolor=T.EDGE, activebackground=T.NIGHT,
                       activeforeground=T.INK, font=self._font(9), anchor="w").pack(fill="x")
        _curtr = self._cfg.get("lang_translate", "ru-RU")
        self._lang_tr_var = tk.StringVar(value=_LL.get(_curtr, _curtr))
        _om = tk.OptionMenu(body, self._lang_tr_var, *_labs)
        _om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                   relief="flat", bd=0, highlightthickness=0, font=self._font(9), anchor="w", cursor="hand2")
        _om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                           font=self._font(9), bd=0)
        _om.pack(fill="x", pady=2)
        # Advanced — всё остальное (сканы, тайминги, интервалы, выбор грейдов, hoard…)
        tk.Frame(body, bg=T.EDGE, height=1).pack(fill="x", pady=(16, 6))
        tk.Button(body, text="Advanced  ▾", command=self._open_advanced, bg=T.PANEL, fg=T.SUB,
                  relief="flat", bd=0, font=self._cta_font(12), pady=6, cursor="hand2").pack(fill="x")
        tk.Label(body, text="scans · timing · intervals · grade selection · hoard list",
                 bg=T.NIGHT, fg=T.FAINT, font=self._font(7), wraplength=HW - 80,
                 justify="left").pack(anchor="w", pady=(3, 0))

    def _open_advanced(self):
        self._close_ov()
        self._settings_full()

    def _settings_full(self):
        """Полные настройки (вкладки) — для продвинутых. Открывается из простого экрана."""
        if self._ov is not None:
            return self._close_ov()
        self._cfg = load_cfg()
        self._cfgvars = {}
        self._gvars = {}
        self._defaults = {}
        ov = self._overlay(st("⚙ настройки"))
        # ttk-стиль тёмного скроллбара (как в db_browser)
        try:
            stl = ttk.Style(self.root)
            stl.theme_use("clam")
            stl.configure("Night.Vertical.TScrollbar", troughcolor=T.NIGHT, background=T.EDGE,
                          bordercolor=T.NIGHT, arrowcolor=T.SUB, darkcolor=T.EDGE, lightcolor=T.EDGE)
            stl.map("Night.Vertical.TScrollbar",
                    background=[("active", T.EDGE_HI), ("pressed", T.EDGE_HI)])
        except Exception:
            pass
        # кнопка сохранить — закреплена внизу
        btns = tk.Frame(ov, bg=T.NIGHT); btns.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
        tk.Button(btns, text=st("сохранить ✓"), command=self._save_settings, bg=T.GO, fg=T.GO_INK,
                  relief="flat", bd=0, font=self._font(11, True), pady=7, cursor="hand2").pack(fill="x")
        tk.Button(btns, text=st("↺ сбросить к умолчанию"), command=self._reset_defaults, bg=T.PANEL,
                  fg=T.SUB, relief="flat", bd=0, font=self._font(9, True), pady=5,
                  cursor="hand2").pack(fill="x", pady=(4, 0))
        # бар вкладок (две строки, чтобы влезло в узкую панель)
        tabbar = tk.Frame(ov, bg=T.NIGHT); tabbar.pack(fill="x", padx=8)
        self._settab_btns = {}
        row = tk.Frame(tabbar, bg=T.NIGHT); row.pack(fill="x")
        for i, (key, lbl) in enumerate(self.SETTAGS):
            if i == 4:
                row = tk.Frame(tabbar, bg=T.NIGHT); row.pack(fill="x")
            b = tk.Label(row, text=st(lbl), bg=T.PANEL, fg=T.SUB, padx=7, pady=4,
                         cursor="hand2", font=self._font(8, True))
            b.pack(side="left", padx=1, pady=1)
            b.bind("<Button-1>", lambda e, k=key: self._set_settab(k))
            self._settab_btns[key] = b
        # прокручиваемая область
        area = tk.Frame(ov, bg=T.EDGE); area.pack(fill="both", expand=True, padx=8, pady=(4, 2))
        canvas = tk.Canvas(area, bg=T.NIGHT, highlightthickness=0)
        sb = ttk.Scrollbar(area, orient="vertical", command=canvas.yview,
                           style="Night.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        self._set_canvas = canvas
        holder = tk.Frame(canvas, bg=T.NIGHT)
        win = canvas.create_window((0, 0), window=holder, anchor="nw")
        holder.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self._wheel_bound = True
        # построить все вкладки (вары живут пока открыт оверлей — переключение не теряет правки)
        self._settab_frames = {}
        for key, _ in self.SETTAGS:
            f = tk.Frame(holder, bg=T.NIGHT)
            self._settab_frames[key] = f
            getattr(self, "_tab_" + key)(f)
        self._set_settab("beh")

    def _set_settab(self, key):
        for f in self._settab_frames.values():
            f.pack_forget()
        self._settab_frames[key].pack(fill="both", expand=True, padx=10, pady=2)
        for k, b in self._settab_btns.items():
            on = k == key
            b.config(bg=(T.PANEL2 if on else T.PANEL), fg=(T.MOON if on else T.SUB))
        if hasattr(self, "_set_canvas"):
            self._set_canvas.yview_moveto(0)
            self.root.after(30, lambda: self._set_canvas.configure(
                scrollregion=self._set_canvas.bbox("all")))

    # ── вкладка: Поведение (мерж / политика / периоды) ──
    def _tab_beh(self, f):
        chosen = set(self._cfg.get("merge_grades", DEFAULT_MERGE_GRADES))
        self._s_section(f, "Синтез грейдов (отмечено — синтезирует, снято — бережёт):")
        for i, ru in enumerate(MERGE_GRADES):
            v = tk.BooleanVar(value=(ru in chosen))
            self._gvars[ru] = v
            label = i18n.grade_name(ru) + ("  ⚠" if i >= _RISKY_FROM else "")
            tk.Checkbutton(f, text=label, variable=v, bg=T.NIGHT, fg=T.GRADE.get(ru, T.INK),
                           selectcolor=T.EDGE, activebackground=T.NIGHT, activeforeground=T.INK,
                           font=self._font(10), anchor="w", wraplength=HW - 80,
                           justify="left").pack(fill="x", pady=1)
        self._s_hint(f, "⚠ Бессмертный и выше — ценное. Включай осознанно: бот сольёт их в куб.")
        self._s_section(f, "Политика предметов")
        self._s_toggle(f, "лочить бижутерию (кольца / амулеты / серьги)", "policy.lock_accessory", True)
        self._s_list(f, "никогда не синтезировать (имена через запятую):", "policy.hoard_names",
                     "кусок имени; предмет с таким именем бот не тронет")
        self._s_toggle(f, "🛡 защита ценного (лог-прелок)", "policy.log_prelock", True,
                       "читает игровой лог; бижу/Immortal+ лочит до синтеза")
        self._s_section(f, "Периоды действий (секунды)")
        self._s_slider(f, "проверка почты", "cycles.mail_every_sec", 30, 1800, 330, 10,
                       "как часто бот заходит в почту")
        self._s_slider(f, "задержка открытия сундука (макс, сек)", "chest.open_delay_max", 2, 15, 5, 1,
                       "сундук в логе → бот жмёт Пробел ОДИН раз через 2..N сек (по событию, без таймеров/бёрста)")
        self._s_slider(f, "скан инвентаря на новые предметы", "cycles.scan_every_sec", 5, 600, 15, 5,
                       "как часто проверяет инвентарь на новый лут и разбирает")
        self._s_section(f, "Мерж — тонкая настройка")
        self._s_num(f, "максимум мержей на тип за проход", "merge.max_per_type", 5, "int")
        self._s_num(f, "разгрузка инвентаря при заполнении (ячеек)", "state.save_inv_threshold", 34, "int",
                    "сколько ячеек занято → раскладка в тайник")
        self._s_dropdown(f, "клавиша открытия сундуков", "chest_key", ["space", "e", "f"], "space",
                         "Руна открытия (Пробел открывает все сундуки)")
        self._s_section(f, "🛠 В разработке")
        self._s_hint(f, "• Тонкий синтез по типам (кольцо/браслет/оружие отдельно) — скоро, ночной "
                        "режим (медленный потоварный скан).\n• Полный счёт инвентаря со скроллом — "
                        "скоро (нужна калибровка прокрутки).\n• Скиллы героев в БД — часть игровых "
                        "описаний недоступна, данные неполные.")

    # ── вкладка: Сканы / OCR ──
    def _tab_scan(self, f):
        self._s_section(f, "OCR дропа")
        self._s_toggle(f, "читать имя/грейд дропа (OCR)", "policy.ocr_drops", True,
                       "наводит на новые предметы, читает тултип")
        self._s_num(f, "макс. OCR-наведений за скан", "policy.ocr_drops_max", 6, "int",
                    "анти-спам: больше = точнее, но дольше")
        self._s_section(f, "Тайминги тултипа (сек)")
        self._s_num(f, "settle грейд-скана", "tooltip.scan_hover_settle", 0.35, "float",
                    "пауза после наведения перед чтением. Слабый ПК → увеличить")
        self._s_num(f, "settle полного чтения", "tooltip.hover_settle", 1.1, "float")
        self._s_num(f, "увеличение картинки OCR", "tooltip.upscale", 2.0, "float")
        self._s_dropdown(f, "язык OCR", "ocr.lang", ["rus+eng", "rus", "eng"], "rus+eng",
                         "игра бывает на любом — rus+eng ловит оба")
        self._s_section(f, "Скролл инвентаря")
        self._s_num(f, "рядов за щелчок колеса (0=выкл)", "inventory.scroll_rows_per_notch", 0, "float")
        self._s_num(f, "макс. страниц скана", "inventory.max_scroll_pages", 6, "int")
        self._s_section(f, "Пороги (эксперт — не трогать без нужды)")
        self._s_num(f, "яркость ячейки куба", "cube_fill_threshold", 35.0, "float")
        self._s_num(f, "яркость ячейки инв/стэш", "slot_fill_threshold", 48.0, "float")
        self._s_num(f, "матч иконки Синтеза", "synth_icon_threshold", 0.62, "float")
        self._s_num(f, "матч кнопки попапа", "confirm_threshold", 0.7, "float")
        self._s_num(f, "матч баннеров панелей", "panel_match_threshold", 0.72, "float")

    # ── вкладка: Хуманлайк ──
    def _tab_hum(self, f):
        self._s_toggle(f, "быстрый режим (fast_mode)", "humanize.fast_mode", True,
                       "быстрые движения/паузы. Выкл → медленнее и «человечнее»")
        self._s_section(f, "Джиттер клика (px)")
        self._s_num(f, "база джиттера", "humanize.target_jitter_px", 6, "int")
        self._s_num(f, "доля от размера цели", "humanize.jitter_frac", 0.3, "float")
        self._s_num(f, "макс. джиттер", "humanize.jitter_max_px", 18, "int")
        self._s_section(f, "Движение курсора (сек)")
        self._s_num(f, "длит. мин", "humanize.move_duration_min", 0.18, "float")
        self._s_num(f, "длит. макс", "humanize.move_duration_max", 0.75, "float")
        self._s_num(f, "шанс овершута (0..1)", "humanize.overshoot_chance", 0.12, "float")
        self._s_num(f, "овершут px", "humanize.overshoot_px", 18, "int")
        self._s_section(f, "Клик (сек)")
        self._s_num(f, "удержание мин", "humanize.press_min", 0.03, "float")
        self._s_num(f, "удержание макс", "humanize.press_max", 0.1, "float")
        self._s_section(f, "Паузы между действиями (сек)")
        self._s_num(f, "мин", "humanize.between_clicks_min", 0.8, "float")
        self._s_num(f, "макс", "humanize.between_clicks_max", 3.5, "float")
        self._s_num(f, "шанс длинной паузы (0..1)", "humanize.long_pause_chance", 0.18, "float")
        self._s_num(f, "длинная мин", "humanize.long_pause_min", 3.0, "float")
        self._s_num(f, "длинная макс", "humanize.long_pause_max", 10.0, "float")
        self._s_section(f, "Fast-режим (сек)")
        self._s_num(f, "движ. мин", "humanize.fast_move_min", 0.05, "float")
        self._s_num(f, "движ. макс", "humanize.fast_move_max", 0.16, "float")
        self._s_num(f, "пауза мин", "humanize.fast_between_min", 0.12, "float")
        self._s_num(f, "пауза макс", "humanize.fast_between_max", 0.4, "float")
        self._s_num(f, "шанс длинной (fast)", "humanize.long_pause_chance_fast", 0.0, "float")

    # ── вкладка: Вежливость ──
    def _tab_pol(self, f):
        self._s_section(f, "Когда бот уступает тебе")
        self._s_hint(f, "Режим параллельный/напролом переключается на главном экране панели.")
        self._s_num(f, "старт цикла после простоя (сек)", "idle_start_seconds", 90, "int",
                    "бот начнёт, только если ты не трогал ПК столько секунд")
        self._s_num(f, "курсор уехал > px = ты вернулся", "cursor_grab_tol_px", 90, "int")
        self._s_num(f, "ждать покоя перед продолжением (сек)", "resume_idle_seconds", 10, "int")

    # ── вкладка: Почта ──
    def _tab_mail(self, f):
        self._s_section(f, "Почта (туда падают итемы / сундуки)")
        self._s_toggle(f, "✉ проверять почту", "state.mail_enabled", True, fg=T.EV["mail"])
        self._s_hint(f, "Период проверки почты — ползунком на вкладке «Поведение».")
        self._s_num(f, "ждать кулдаун кнопки «обновить» (сек)", "state.mail_refresh_wait", 14, "int",
                    "пауза, пока станет активна бесплатная награда. Намеренно НЕ ускоряется.")

    # ── вкладка: Язык / БД ──
    def _tab_lang(self, f):
        cfg = self._cfg
        self._s_section(f, "Язык базы знаний")
        try:
            import db_browser
            locales = list(db_browser.LOCALES)
            labels = [db_browser.LANG_LABELS.get(c, c) for c in locales]
        except Exception:
            db_browser = None
            locales, labels = ["ru-RU", "en-US"], ["Русский", "English"]
        self._lang_l2c = dict(zip(labels, locales))
        cur_main = cfg.get("lang_main", "ru-RU")
        cur_tr = cfg.get("lang_translate", "en-US")
        if cur_main not in locales:
            cur_main = locales[0]
        if cur_tr not in locales:
            cur_tr = locales[0]
        lbl = (db_browser.LANG_LABELS if db_browser else {}).get

        def _lang_om(var):
            om = tk.OptionMenu(f, var, *labels)
            om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                      relief="flat", bd=0, highlightthickness=0, font=self._font(8),
                      anchor="w", cursor="hand2")
            om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2,
                              activeforeground=T.MOON, font=self._font(8), bd=0)
            om.pack(fill="x", pady=1)

        # UI всегда английский — основной язык не выбирается; перевод ниже только для БД/имён
        self._lang_main_var = tk.StringVar(value=lbl("en-US", "English"))
        self._lang_tr_on = tk.BooleanVar(value=bool(cfg.get("translate_enabled", False)))
        tk.Checkbutton(f, text="показывать перевод вторым языком", variable=self._lang_tr_on,
                       bg=T.NIGHT, fg=T.EV["mail"], selectcolor=T.EDGE, activebackground=T.NIGHT,
                       activeforeground=T.INK, font=self._font(8), anchor="w").pack(fill="x")
        tk.Label(f, text="перевод", bg=T.NIGHT, fg=T.FAINT, font=self._font(8),
                 anchor="w").pack(anchor="w")
        self._lang_tr_var = tk.StringVar(value=lbl(cur_tr, cur_tr))
        _lang_om(self._lang_tr_var)

    # ── вкладка: Свой конфиг (наполняется в custom-модуле) ──
    def _tab_custom(self, f):
        self._build_custom_tab(f)

    def _build_custom_tab(self, f):
        for w in f.winfo_children():        # idempotent: можно перерисовать после сохранения
            w.destroy()
        self._custom_frame = f
        try:
            import custom
        except Exception as e:
            self._s_hint(f, f"модуль недоступен: {e}")
            return
        self._custom_mod = custom
        # ── сохранённые рутины ──
        self._s_section(f, "Сохранённые рутины")
        rts = custom.load_routines()["routines"]
        if not rts:
            self._s_hint(f, "пока нет — запиши свои действия или собери из шагов ниже")
        for r in rts:
            name = r.get("name", "?")
            row = tk.Frame(f, bg=T.PANEL); row.pack(fill="x", pady=1)
            ttl = name + ("  ⚠" if r.get("freedom") else "")
            tk.Label(row, text=ttl, bg=T.PANEL, fg=T.INK, font=self._font(8),
                     anchor="w").pack(side="left", padx=4, fill="x", expand=True)
            for sym, col, cb in (("✕", T.STOPC, lambda n=name: self._custom_delete(n)),
                                 ("✎", T.SUB, lambda rr=r: self._custom_edit(rr)),
                                 ("▶", T.GO, lambda n=name: self._start_custom(n))):
                lb = tk.Label(row, text=sym, bg=T.PANEL, fg=col, cursor="hand2",
                              font=self._font(10, True))
                lb.pack(side="right", padx=3)
                lb.bind("<Button-1>", lambda e, c=cb: c())
        # ── конструктор рутины (запись + ручные шаги) ──
        self._s_section(f, "Собрать / записать рутину")
        if not hasattr(self, "_pending") or self._pending is None:
            self._pending = {"name": "", "steps": [], "freedom": False,
                             "loop": True, "interval_min": 0.0, "interval_max": 0.0, "repeats": 0}
        nm = tk.Frame(f, bg=T.NIGHT); nm.pack(fill="x", pady=1)
        tk.Label(nm, text="имя", bg=T.NIGHT, fg=T.SUB, font=self._font(8)).pack(side="left")
        self._rt_name = tk.StringVar(value=self._pending.get("name", ""))
        tk.Entry(nm, textvariable=self._rt_name, bg=T.PANEL, fg=T.INK, insertbackground=T.MOON,
                 relief="flat", font=self._font(8), bd=0).pack(side="right", fill="x", expand=True, ipady=2, padx=(4, 0))
        # запись
        self._rec_lbl = tk.Label(f, text="", bg=T.NIGHT, fg=T.FAINT, font=self._font(7))
        self._rec_btn = tk.Label(f, text="● Записать действия (F9 — стоп)", bg=T.PANEL2, fg=T.STOPC,
                                 cursor="hand2", font=self._font(8, True), pady=4)
        self._rec_btn.pack(fill="x", pady=(2, 0))
        self._rec_btn.bind("<Button-1>", lambda e: self._toggle_record())
        self._rec_lbl.pack(anchor="w")
        self._s_hint(f, "во время записи делай действия в игре; F9 завершит. координаты "
                        "привяжутся к панелям автоматически.")
        # ручной шаг
        add = tk.Frame(f, bg=T.NIGHT); add.pack(fill="x", pady=(4, 1))
        self._hi_var = tk.StringVar(value=custom.HIGH_STEPS[0])
        om = tk.OptionMenu(add, self._hi_var, *custom.HIGH_STEPS)
        om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                  relief="flat", bd=0, highlightthickness=0, font=self._font(8), cursor="hand2")
        om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2,
                          activeforeground=T.MOON, font=self._font(8), bd=0)
        om.pack(side="left")
        tk.Label(add, text="＋ шаг", bg=T.PANEL, fg=T.GO, cursor="hand2", font=self._font(8, True),
                 padx=6, pady=2).pack(side="left", padx=4)
        add.winfo_children()[-1].bind("<Button-1>", lambda e: self._add_manual_step())
        # список шагов pending
        lw = tk.Frame(f, bg=T.EDGE); lw.pack(fill="x", pady=2)
        self._pend_lb = tk.Listbox(lw, bg="#120e22", fg=T.SUB, relief="flat", height=5,
                                   font=self._font(8), highlightthickness=0, bd=0,
                                   selectbackground=T.PANEL2, selectforeground=T.MOON)
        self._pend_lb.pack(fill="x", padx=2, pady=2)
        ctl = tk.Frame(f, bg=T.NIGHT); ctl.pack(fill="x")
        for sym, cb in (("▲", self._pend_up), ("▼", self._pend_down),
                        ("удалить", self._pend_del), ("очистить", self._pend_clear)):
            b = tk.Label(ctl, text=sym, bg=T.PANEL, fg=T.SUB, cursor="hand2",
                         font=self._font(8), padx=6, pady=2)
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, c=cb: c())
        # параметры рутины
        opt = tk.Frame(f, bg=T.NIGHT); opt.pack(fill="x", pady=(4, 0))
        self._rt_loop = tk.BooleanVar(value=self._pending.get("loop", True))
        tk.Checkbutton(opt, text="зациклить", variable=self._rt_loop, bg=T.NIGHT, fg=T.INK,
                       selectcolor=T.EDGE, activebackground=T.NIGHT, font=self._font(8)).pack(side="left")
        self._rt_freedom = tk.BooleanVar(value=self._pending.get("freedom", False))
        tk.Checkbutton(opt, text="⚠ свобода (без защит)", variable=self._rt_freedom,
                       command=self._freedom_warn, bg=T.NIGHT, fg=T.STOPC, selectcolor=T.EDGE,
                       activebackground=T.NIGHT, font=self._font(8)).pack(side="left", padx=6)
        iv = tk.Frame(f, bg=T.NIGHT); iv.pack(fill="x")
        tk.Label(iv, text="пауза цикла сек (мин/макс)", bg=T.NIGHT, fg=T.SUB,
                 font=self._font(8)).pack(side="left")
        self._rt_iv_min = tk.StringVar(value=str(self._pending.get("interval_min", 0.0)))
        self._rt_iv_max = tk.StringVar(value=str(self._pending.get("interval_max", 0.0)))
        for var in (self._rt_iv_min, self._rt_iv_max):
            tk.Entry(iv, textvariable=var, width=4, bg=T.PANEL, fg=T.INK, insertbackground=T.MOON,
                     relief="flat", font=self._font(8), bd=0, justify="right").pack(side="right", ipady=1, padx=1)
        tk.Label(f, text="💾 сохранить рутину", bg=T.GO, fg=T.GO_INK, cursor="hand2",
                 font=self._font(9, True), pady=5).pack(fill="x", pady=(4, 2))
        f.winfo_children()[-1].bind("<Button-1>", lambda e: self._save_routine())
        self._refresh_pending()

    # ── конструктор: операции со списком шагов ──
    def _refresh_pending(self):
        if not hasattr(self, "_pend_lb"):
            return
        self._pend_lb.delete(0, "end")
        for i, st in enumerate(self._pending["steps"]):
            self._pend_lb.insert("end", f"{i+1}. {self._step_label(st)}")

    @staticmethod
    def _step_label(st):
        k = st.get("kind")
        if k == "step":
            import custom
            return custom.HIGH_RU.get(st.get("action"), st.get("action", "?"))
        if k == "key":
            return f"клавиша {st.get('key')}"
        if k == "wheel":
            loc = st.get("panel") or ("окно" if "wx" in st else "экран")
            return f"колесо {st.get('notches')} @ {loc}"
        loc = st.get("panel") or ("окно" if "wx" in st else "экран")
        return f"клик {st.get('button','left')} @ {loc}"

    def _add_manual_step(self):
        act = self._hi_var.get()
        self._pending["steps"].append({"kind": "step", "action": act,
                                       "wait": 1.0 if act == "wait" else 0.3})
        self._refresh_pending()

    def _pend_sel(self):
        s = self._pend_lb.curselection()
        return s[0] if s else None

    def _pend_del(self):
        i = self._pend_sel()
        if i is not None:
            del self._pending["steps"][i]; self._refresh_pending()

    def _pend_clear(self):
        self._pending["steps"] = []; self._refresh_pending()

    def _pend_up(self):
        i = self._pend_sel()
        if i and i > 0:
            s = self._pending["steps"]; s[i-1], s[i] = s[i], s[i-1]
            self._refresh_pending(); self._pend_lb.selection_set(i-1)

    def _pend_down(self):
        i = self._pend_sel()
        if i is not None and i < len(self._pending["steps"]) - 1:
            s = self._pending["steps"]; s[i+1], s[i] = s[i], s[i+1]
            self._refresh_pending(); self._pend_lb.selection_set(i+1)

    def _freedom_warn(self):
        if self._rt_freedom.get():
            ok = messagebox.askyesno(
                "Полная свобода",
                "Кастомный кликер без защит может ПОТЕРЯТЬ ценные предметы и зайти в\n"
                "alchemy/delete/tribute. Бот будет кликать строго по записи.\n\n"
                "Ты берёшь риск на себя. Включить свободу?", icon="warning")
            if not ok:
                self._rt_freedom.set(False)

    def _save_routine(self):
        name = self._rt_name.get().strip()
        if not name:
            self._put("укажи имя рутины", T.EV["warn"]); return
        if not self._pending["steps"]:
            self._put("рутина пустая — добавь шаги или запиши", T.EV["warn"]); return
        try:
            iv_min = float(str(self._rt_iv_min.get()).replace(",", ".") or 0)
            iv_max = float(str(self._rt_iv_max.get()).replace(",", ".") or 0)
        except Exception:
            iv_min = iv_max = 0.0
        routine = {"name": name, "steps": self._pending["steps"],
                   "freedom": bool(self._rt_freedom.get()), "loop": bool(self._rt_loop.get()),
                   "interval_min": iv_min, "interval_max": iv_max, "repeats": 0}
        self._custom_mod.upsert_routine(routine)
        self._pending = None
        self._put(f"💾 рутина «{name}» сохранена", T.EV["ok"])
        self._build_custom_tab(self._custom_frame)   # перерисовать список

    def _custom_delete(self, name):
        if messagebox.askyesno("Удалить", f"Удалить рутину «{name}»?"):
            self._custom_mod.delete_routine(name)
            self._build_custom_tab(self._custom_frame)

    def _custom_edit(self, r):
        self._pending = {"name": r.get("name", ""), "steps": list(r.get("steps", [])),
                         "freedom": r.get("freedom", False), "loop": r.get("loop", True),
                         "interval_min": r.get("interval_min", 0.0),
                         "interval_max": r.get("interval_max", 0.0), "repeats": r.get("repeats", 0)}
        self._build_custom_tab(self._custom_frame)

    # ── запись ──
    def _toggle_record(self):
        if getattr(self, "_rec_evt", None) is not None:
            self._rec_evt.set(); return
        if self._alive():
            self._put("останови бота перед записью", T.EV["warn"]); return
        import threading as _th
        import custom
        self._rec_evt = _th.Event()
        self._rec_btn.config(text="■ Стоп записи (или F9)", fg=T.MOON)
        self._rec_lbl.config(text="● запись… делай действия в игре", fg=T.STOPC)

        def work():
            steps = custom.record(self._rec_evt, status=lambda n: LOG_Q.put(("__recn__", n)))
            LOG_Q.put(("__recdone__", steps))
        _th.Thread(target=work, daemon=True).start()

    def _on_record_done(self, steps):
        self._rec_evt = None
        if hasattr(self, "_rec_btn") and self._rec_btn.winfo_exists():
            self._rec_btn.config(text="● Записать действия (F9 — стоп)", fg=T.STOPC)
        if steps is None:
            if hasattr(self, "_rec_lbl") and self._rec_lbl.winfo_exists():
                self._rec_lbl.config(text="pynput не установлен — запись недоступна", fg=T.EV["warn"])
            return
        if self._pending is None:
            self._pending = {"name": "", "steps": [], "freedom": False, "loop": True,
                             "interval_min": 0.0, "interval_max": 0.0, "repeats": 0}
        self._pending["steps"].extend(steps)
        if hasattr(self, "_rec_lbl") and self._rec_lbl.winfo_exists():
            self._rec_lbl.config(text=f"записано шагов: {len(steps)} (добавлены в рутину)", fg=T.GO)
        self._refresh_pending()

    # ── запуск кастомной рутины ──
    def _start_custom(self, name):
        if self._alive():
            self._put("сначала останови текущее", T.EV["warn"]); return
        r = self._custom_mod.get_routine(name)
        if not r:
            return
        if r.get("freedom") and not messagebox.askyesno(
                "Свобода", f"Рутина «{name}» без защит — может потерять ценное.\nЗапустить?",
                icon="warning"):
            return
        try:
            farm.reload_config(); state.reload_config()
            import vision
            vision.reload_config()
        except Exception:
            pass
        self.stop_evt.clear()
        self._close_ov()
        self._put(f"▶ свой кликер: {name}", T.EV["ok"])
        self.worker = threading.Thread(target=self._run_custom, args=(r,), daemon=True)
        self.worker.start()
        self._running_ui(True)

    def _run_custom(self, r):
        try:
            import custom
            custom.play(r, log=lambda m: LOG_Q.put(m),
                        stat=lambda s: STAT_Q.put(s), stop_event=self.stop_evt)
        except Exception as e:
            LOG_Q.put(f"ОШИБКА: {e}")
        finally:
            STAT_Q.put(dict(farm.STATS, running=False, phase="стоп"))

    _HUD_COLORS = [("белый", "#ffffff"), ("золото", "#ffd95e"), ("бирюза", "#5ff2e6"),
                   ("зелёный", "#62d96b"), ("красный", "#ff5454"), ("розовый", "#ff7be0"),
                   ("сирень", "#b163ff"), ("серый", "#cfcfdc")]

    def _hud_colors(self, f):
        """Дропдауны цвета цифр и описания таймера (имя → hex, сохраняется в hud.color_*)."""
        h = self._cfg.get("hud", {})
        by_hex = {hx: nm for nm, hx in self._HUD_COLORS}
        names = [nm for nm, _ in self._HUD_COLORS]
        self._hud_top_var = tk.StringVar(value=by_hex.get(h.get("color_top", "#ffffff"), "белый"))
        self._hud_bot_var = tk.StringVar(value=by_hex.get(h.get("color_bottom", "#ffd95e"), "золото"))
        for lbl, var in (("цвет цифр", self._hud_top_var), ("цвет описания", self._hud_bot_var)):
            row = tk.Frame(f, bg=T.NIGHT); row.pack(fill="x", pady=2)
            tk.Label(row, text=lbl, bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                     anchor="w").pack(side="left")
            om = tk.OptionMenu(row, var, *names)
            om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                      relief="flat", bd=0, highlightthickness=0, font=self._font(10), cursor="hand2")
            om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2,
                              activeforeground=T.MOON, font=self._font(10), bd=0)
            om.pack(side="right")

    # ── вкладка: Stage hop (прыжки по стадиям) — English-only UI ──
    _HOP_DIFFS = ["any", "NORMAL", "NIGHTMARE", "HELL", "TORMENT"]

    def _tab_hop(self, f):
        import routehop
        h = self._cfg.get("hop", {}) or {}
        self._s_section(f, "Stage hop — jump between stages")
        self._s_hint(f, "Stage hop needs a one-time PORTAL calibration on YOUR window (the map "
                        "coordinates are window-specific). Without it the bot NEVER clicks blind — "
                        "hop just stays idle, farming is unaffected.")

        # ── PORTAL calibration (REQUIRED for hop) — live status + launcher ──
        self._s_section(f, "PORTAL calibration (required)")
        self._hop_cal_status = tk.Label(f, text="", bg=T.NIGHT, fg=T.FAINT, font=self._font(9),
                                        wraplength=HW - 78, justify="left", anchor="w")
        self._hop_cal_status.pack(anchor="w", pady=(0, 2))
        crow = tk.Frame(f, bg=T.NIGHT); crow.pack(fill="x", pady=(0, 2))
        tk.Button(crow, text="✦ calibrate PORTAL", command=self._hop_run_calibration, bg=T.PANEL,
                  fg=T.MOON, relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left")
        tk.Button(crow, text="↻ re-check", command=self._hop_refresh_cal_status, bg=T.PANEL,
                  fg=T.INK, relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left", padx=(6, 0))
        self._hop_refresh_cal_status()
        # режим: off / strategy / route
        self._hop_mode_var = tk.StringVar(value=("off" if not h.get("enabled")
                                                 else (h.get("mode") or "strategy").lower()))
        row = tk.Frame(f, bg=T.NIGHT); row.pack(fill="x", pady=(4, 2))
        tk.Label(row, text="mode", bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                 anchor="w").pack(side="left")
        self._hop_style(tk.OptionMenu(row, self._hop_mode_var, "off", "strategy", "route")).pack(side="right")
        self._s_hint(f, "off — no hopping  ·  strategy — auto chest-juggling by level  ·  route — your timed map below")

        # ── presets: ready community strategies + your saved routes ──
        self._s_section(f, "Presets")
        self._s_hint(f, "Ready-made community strategies + your own saved routes. Pick one and press "
                        "load to fill the fields below. Save the current route as a named preset of your own.")
        prow = tk.Frame(f, bg=T.NIGHT); prow.pack(fill="x", pady=2)
        tk.Label(prow, text="preset", bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                 anchor="w").pack(side="left")
        self._hop_preset_var = tk.StringVar()
        self._hop_preset_om = self._hop_style(tk.OptionMenu(prow, self._hop_preset_var, ""))
        self._hop_preset_om.pack(side="right")
        self._hop_refresh_presets()
        self._hop_preset_status = tk.Label(f, text="", bg=T.NIGHT, fg=T.FAINT, font=self._font(8),
                                           wraplength=HW - 78, justify="left", anchor="w")
        self._hop_preset_status.pack(anchor="w")
        pbrow = tk.Frame(f, bg=T.NIGHT); pbrow.pack(fill="x", pady=(2, 0))
        tk.Button(pbrow, text="load", command=self._hop_load_preset, bg=T.PANEL, fg=T.GO,
                  relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left")
        tk.Button(pbrow, text="✦ save as", command=self._hop_save_preset, bg=T.PANEL, fg=T.MOON,
                  relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left", padx=(6, 0))
        tk.Button(pbrow, text="delete", command=self._hop_delete_preset, bg=T.PANEL, fg=T.WARN,
                  relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left", padx=(6, 0))

        self._s_section(f, "Strategy preset (mode = strategy)")
        self._s_num(f, "hero level", "hop.hero_level", 80, "int",
                    "your roster level — bounds stage level (EXP penalty if a stage is too high)")
        cur_diff = (h.get("difficulty") or "any")
        self._hop_diff_var = tk.StringVar(value=cur_diff if cur_diff in self._HOP_DIFFS else "any")
        drow = tk.Frame(f, bg=T.NIGHT); drow.pack(fill="x", pady=2)
        tk.Label(drow, text="difficulty", bg=T.NIGHT, fg=T.SUB, font=self._font(9),
                 anchor="w").pack(side="left")
        self._hop_style(tk.OptionMenu(drow, self._hop_diff_var, *self._HOP_DIFFS)).pack(side="right")
        self._s_hint(f, "keep to one difficulty = fewer PORTAL clicks per hop")
        self._s_num(f, "max levels ahead", "hop.max_ahead", 8, "int",
                    "never farm a stage more than N levels above hero (EXP-penalty guard)")

        self._s_section(f, "Custom route (mode = route)")
        self._s_hint(f, "One stage per line:   3-3-9 / time: 235 sec\n"
                        "X-Y-Z = difficulty(1-4)-act(1-3)-stage(1-10). Give each stage enough time so the "
                        "pack fully farms it. Loops top→bottom forever.")
        txt = tk.Text(f, height=7, bg="#120e22", fg=T.INK, insertbackground=T.MOON, relief="flat",
                      bd=0, font=self._font(10), wrap="none", highlightthickness=1,
                      highlightbackground=T.EDGE, highlightcolor=T.MOON)
        txt.pack(fill="x", pady=(2, 2), ipady=3)
        stops, _ = routehop.parse_route_cfg(h.get("route", []))
        if stops:
            txt.insert("1.0", routehop.format_route(stops))
        self._hop_route_txt = txt
        self._hop_route_status = tk.Label(f, text="", bg=T.NIGHT, fg=T.FAINT, font=self._font(8),
                                          wraplength=HW - 78, justify="left", anchor="w")
        self._hop_route_status.pack(anchor="w")
        brow = tk.Frame(f, bg=T.NIGHT); brow.pack(fill="x", pady=(4, 0))
        tk.Button(brow, text="✓ check", command=self._hop_check_route, bg=T.PANEL, fg=T.INK,
                  relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left")
        tk.Button(brow, text="✦ fill preset", command=self._hop_fill_preset, bg=T.PANEL, fg=T.MOON,
                  relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left", padx=(6, 0))
        self._s_hint(f, "⚠ legit navigation only — never bypass chest cooldown by reconnecting (ban risk). "
                        "Mind the EXP penalty: don't route stages far above your level.")

    def _hop_style(self, om):
        om.config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2, activeforeground=T.MOON,
                  relief="flat", bd=0, highlightthickness=0, font=self._font(10), cursor="hand2")
        om["menu"].config(bg=T.PANEL, fg=T.INK, activebackground=T.PANEL2,
                          activeforeground=T.MOON, font=self._font(10), bd=0)
        return om

    def _hop_check_route(self):
        import routehop
        stops, errs = routehop.parse_route(self._hop_route_txt.get("1.0", "end"))
        if errs:
            self._hop_route_status.config(text="⚠ " + "  ·  ".join(errs[:3]), fg=T.WARN)
        elif not stops:
            self._hop_route_status.config(text="route empty — add lines like  3-3-9 / time: 235 sec", fg=T.FAINT)
        else:
            total = sum(s["dwell_sec"] for s in stops)
            self._hop_route_status.config(text=f"✓ {len(stops)} stages, full loop ~{total}s", fg=T.GO)

    def _hop_fill_preset(self):
        import routehop
        try:
            lvl = int(float(self._cfgvars["hop.hero_level"][1].get()))
        except Exception:
            lvl = int((self._cfg.get("hop", {}) or {}).get("hero_level", 80))
        diff = self._hop_diff_var.get()
        diff = None if diff in ("any", "") else diff
        stops = routehop.suggest_route(lvl, difficulty=diff, n=4, dwell_sec=240)
        self._hop_route_txt.delete("1.0", "end")
        self._hop_route_txt.insert("1.0", routehop.format_route(stops))
        self._hop_check_route()

    # ── PORTAL calibration status / launcher ──
    def _hop_refresh_cal_status(self):
        """Показать состояние калибровки PORTAL для текущего окна (ok/missing/mismatch)."""
        try:
            import stagenav
            st, detail = stagenav.calibration_status()
        except Exception as e:
            st, detail = "error", repr(e)
        col = {"ok": T.GO}.get(st, T.WARN)
        mark = "✓" if st == "ok" else "⚠"
        label = {"ok": "calibrated", "missing": "NOT calibrated",
                 "window_mismatch": "window changed — recalibrate",
                 "no_window": "old calibration — recalibrate"}.get(st, "status: " + st)
        self._hop_cal_status.config(text=f"{mark} {label}\n{detail}", fg=col)

    def _spawn_calibrator(self, script):
        """Запустить калибратор в отдельной ВИДИМОЙ консоли (интерактив: курсор + F8). (ok, msg).
        Явные кандидаты python.exe: venv проекта → рядом с sys.executable (под EXE sys.executable —
        это сам EXE, не python, поэтому раньше кнопка молчала)."""
        import subprocess
        cands = [os.path.join(HERE, ".venv", "Scripts", "python.exe"),
                 sys.executable.replace("pythonw.exe", "python.exe"),
                 os.path.join(os.path.dirname(sys.executable), "python.exe")]
        cons = next((c for c in cands
                     if os.path.exists(c) and "python" in os.path.basename(c).lower()), None)
        if not cons:
            return False, "python.exe не найден (venv не собран?)"
        path = os.path.join(HERE, script)
        if not os.path.exists(path):
            return False, f"нет файла {script}"
        try:
            subprocess.Popen([cons, path], cwd=HERE,
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            return True, "ok"
        except Exception as e:
            return False, repr(e)

    def _run_calibration(self):
        """Кнопка под START: сразу открыть пошаговый калибратор (лог + сундуки — единственное, что
        требует калибровки; панели/портал портативны). Скрипт в консоли ведёт: куда навести + F8."""
        ok, msg = self._spawn_calibrator("calibrate_records.py")
        if ok:
            self._calib_hint.config(
                text="Открылось окно калибровки — следуй подсказкам в нём (наведи курсор куда сказано "
                     "+ нажми F8). Закончишь — перезапусти панель, и всё заработает.", fg=T.MOON)
        else:
            self._calib_hint.config(text="⚠ не удалось запустить калибратор: " + msg, fg=T.WARN)

    def _hop_run_calibration(self):
        """Запустить calibrate_portal.py (интерактив: курсор+F8 по элементам PORTAL)."""
        ok, msg = self._spawn_calibrator("calibrate_portal.py")
        if ok:
            self._hop_cal_status.config(
                text="✦ calibration window opened — open PORTAL in game, hover each element, press "
                     "F8. When done, press ↻ re-check.", fg=T.MOON)
        else:
            self._hop_cal_status.config(text=f"⚠ could not launch calibrator: {msg}", fg=T.WARN)

    # ── Calibration — отдельный экран С ГЛАВНОГО (кнопка под START), не в настройках ──
    def _open_calibration(self):
        if self._ov is not None:
            return self._close_ov()
        ov = self._overlay("Calibration")
        try:
            stl = ttk.Style(self.root); stl.theme_use("clam")
            stl.configure("Night.Vertical.TScrollbar", troughcolor=T.NIGHT, background=T.EDGE,
                          bordercolor=T.NIGHT, arrowcolor=T.SUB, darkcolor=T.EDGE, lightcolor=T.EDGE)
        except Exception:
            pass
        area = tk.Frame(ov, bg=T.EDGE); area.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        canvas = tk.Canvas(area, bg=T.NIGHT, highlightthickness=0)
        sb = ttk.Scrollbar(area, orient="vertical", command=canvas.yview,
                           style="Night.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        holder = tk.Frame(canvas, bg=T.NIGHT)
        win = canvas.create_window((0, 0), window=holder, anchor="nw")
        holder.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self._wheel_bound = True
        self._calib_frame = holder
        self._calib_render()

    def _calib_render(self):
        f = self._calib_frame
        for w in f.winfo_children():
            w.destroy()
        import calibration
        self._s_section(f, "Calibration — how the bot sees the game")
        self._s_hint(f, "Banner-relative points are portable; window-fraction points are tied to YOUR "
                        "window size and must be calibrated once on this PC. Run each that isn't OK, "
                        "then re-check. The bot NEVER clicks on a non-OK calibration (no blind clicks).")
        try:
            rows = calibration.status_all()
            s = calibration.summary()
        except Exception as e:
            tk.Label(f, text=f"calibration error: {e!r}", bg=T.NIGHT, fg=T.WARN,
                     font=self._font(9)).pack(anchor="w")
            return
        if s["all_ok"]:
            head, col = "✓ everything calibrated", T.GO
        elif s["ready_basic"]:
            head, col = f"farm works · {len(s['missing']) + len(s['stale'])} more to calibrate", T.WARN
        else:
            head, col = "⚠ NOT ready — calibrate panel buttons first", T.WARN
        tk.Label(f, text=head, bg=T.NIGHT, fg=col, font=self._font(11, True)).pack(anchor="w", pady=(4, 4))
        for r in rows:
            ok = r["status"] == "ok"
            row = tk.Frame(f, bg=T.NIGHT); row.pack(fill="x", pady=(3, 0))
            tk.Label(row, text=("✓" if ok else "⚠"), bg=T.NIGHT, fg=(T.GO if ok else T.WARN),
                     font=self._font(11, True), width=2).pack(side="left")
            tk.Label(row, text=r["label"], bg=T.NIGHT, fg=T.INK, font=self._font(9), anchor="w",
                     wraplength=HW - 160, justify="left").pack(side="left", fill="x", expand=True)
            if not ok:
                tk.Button(row, text="calibrate", command=lambda sc=r["produces"]: self._calib_launch(sc),
                          bg=T.PANEL, fg=T.MOON, relief="flat", bd=0, font=self._font(8, True),
                          padx=8, pady=3, cursor="hand2").pack(side="right")
            self._s_hint(f, f"     {r['coord']} · {r['status']} — {r['detail']}")
        brow = tk.Frame(f, bg=T.NIGHT); brow.pack(fill="x", pady=(8, 0))
        tk.Button(brow, text="↻ re-check", command=self._calib_render, bg=T.PANEL, fg=T.INK,
                  relief="flat", bd=0, font=self._font(9, True), padx=10, pady=4,
                  cursor="hand2").pack(side="left")
        self._refresh_calib_bar()                     # синхронизировать кнопку на главном экране

    def _calib_launch(self, script):
        ok, msg = self._spawn_calibrator(script)
        try:
            self._put(f"calibration: {msg}", T.MOON if ok else T.WARN)
        except Exception:
            pass

    def _refresh_calib_bar(self):
        """Обновить кнопку калибровки на главном экране (под START): сколько точек не готово."""
        if not hasattr(self, "_calib_btn"):
            return
        try:
            import calibration
            s = calibration.summary()
        except Exception:
            return
        ok = not (s["missing"] or s["stale"])
        if s["all_ok"]:
            self._calib_btn.config(text="✓ calibrated — recalibrate", fg=T.GO)
            self._calib_hint.config(text="")
        else:
            n = len(s["missing"]) + len(s["stale"])
            self._calib_btn.config(text="⚙ Calibrate now (%d)" % n, fg=T.NIGHT, bg=T.MOON)
            self._calib_hint.config(
                text="%d point-set(s) need a one-time calibration on your window — tap to fix" % n)
        # ГЕЙТ START: пока есть некалиброванные точки — кнопка недоступна (нельзя фармить без калибровки)
        try:
            if getattr(self, "ready", False) and not self._alive():
                self.btn.config(state=("normal" if ok else "disabled"))
        except Exception:
            pass

    # ── presets (community + custom) ──
    def _hop_refresh_presets(self):
        """Перестроить список пресетов в дропдауне (community + кастомные из hop_presets.json)."""
        import hop_presets
        names = [p["name"] for p in hop_presets.all_presets()]
        menu = self._hop_preset_om["menu"]
        menu.delete(0, "end")
        for nm in names:
            menu.add_command(label=nm, command=lambda v=nm: self._hop_preset_var.set(v))
        if names and self._hop_preset_var.get() not in names:
            self._hop_preset_var.set(names[0])

    def _hop_load_preset(self):
        """Применить выбранный пресет к полям вкладки (mode/difficulty/max_ahead/route)."""
        import hop_presets
        import routehop
        name = self._hop_preset_var.get()
        p = hop_presets.get(name)
        if not p:
            self._hop_preset_status.config(text="select a preset first", fg=T.FAINT); return
        try:
            lvl = int(float(self._cfgvars["hop.hero_level"][1].get()))
        except Exception:
            lvl = int((self._cfg.get("hop", {}) or {}).get("hero_level", 80))
        diff = self._hop_diff_var.get()
        diff = None if diff in ("any", "") else diff
        patch = hop_presets.apply(p, lvl, diff)
        self._hop_mode_var.set(patch["mode"])
        if "max_ahead" in patch:
            self._cfgvars["hop.max_ahead"][1].set(str(patch["max_ahead"]))
        if patch.get("difficulty"):
            self._hop_diff_var.set(patch["difficulty"])
        if patch.get("route_stops") is not None:
            self._hop_route_txt.delete("1.0", "end")
            self._hop_route_txt.insert("1.0", routehop.format_route(patch["route_stops"]))
            self._hop_check_route()
        tag = "built-in" if name in hop_presets._COMMUNITY_NAMES else "custom"
        msg = f"loaded {tag} '{name}' → mode {patch['mode']}"
        if patch.get("warn"):
            msg += " — " + patch["warn"]
        self._hop_preset_status.config(text=msg, fg=T.WARN if patch.get("warn") else T.GO)

    def _hop_save_preset(self):
        """Сохранить текущий маршрут как именованный кастомный пресет."""
        import tkinter.simpledialog as simpledialog
        import hop_presets
        import routehop
        stops, errs = routehop.parse_route(self._hop_route_txt.get("1.0", "end"))
        if errs or not stops:
            self._hop_preset_status.config(text="fix the route first (press ✓ check)", fg=T.WARN); return
        name = simpledialog.askstring("Save preset", "Name this route:", parent=self.root)
        if not name:
            return
        ok, msg = hop_presets.add_user(name, stops)
        self._hop_preset_status.config(text=msg, fg=T.GO if ok else T.WARN)
        if ok:
            self._hop_refresh_presets()
            self._hop_preset_var.set(name.strip())

    def _hop_delete_preset(self):
        """Удалить выбранный кастомный пресет (community удалить нельзя)."""
        import hop_presets
        ok, msg = hop_presets.delete_user(self._hop_preset_var.get())
        self._hop_preset_status.config(text=msg, fg=T.GO if ok else T.WARN)
        if ok:
            self._hop_refresh_presets()

    def _reset_defaults(self):
        """Откатить все поля настроек к значениям по умолчанию (применится после «сохранить»)."""
        for path, (kind, var) in self._cfgvars.items():
            if path not in self._defaults:
                continue
            d = self._defaults[path]
            var.set(", ".join(str(x) for x in d) if kind == "list" else d)
        for ru, v in self._gvars.items():
            v.set(ru in DEFAULT_MERGE_GRADES)
        self._put("⚙ значения сброшены к умолчанию — нажми «сохранить»", T.MOON)

    def _save_settings(self):
        cfg = load_cfg()
        # generic-вары по путям
        for path, (kind, var) in self._cfgvars.items():
            try:
                raw = var.get()
                if kind == "bool":
                    val = bool(raw)
                elif kind == "int":
                    val = int(float(str(raw).strip()))
                elif kind == "float":
                    val = float(str(raw).replace(",", ".").strip())
                elif kind == "list":
                    val = [s.strip() for s in str(raw).split(",") if s.strip()]
                else:
                    val = str(raw)
                self._cfg_set(cfg, path, val)
            except Exception:
                pass   # битый ввод — оставить старое
        # мерж-грейды — рус-тиры из галок (отмечено = мержим). FORBIDDEN/ALLOWED выводятся в farm.
        if self._gvars:   # грейд-галки строятся только в Advanced; из простого экрана не трогаем
            chosen = [ru for ru in MERGE_GRADES if self._gvars[ru].get()]
            cfg["merge_grades"] = chosen if chosen else list(DEFAULT_MERGE_GRADES)
        cfg.pop("forbidden_merge_grades", None)   # устаревшие ключи — больше не нужны
        cfg.pop("allowed_merge_grades", None)
        cfg.pop("cycle_period_sec", None)
        # таймер: цвета (имя → hex)
        if hasattr(self, "_hud_top_var"):
            hexmap = {nm: hx for nm, hx in self._HUD_COLORS}
            cfg.setdefault("hud", {})["color_top"] = hexmap.get(self._hud_top_var.get(), "#ffffff")
            cfg.setdefault("hud", {})["color_bottom"] = hexmap.get(self._hud_bot_var.get(), "#ffd95e")
        # hop-режим (вкладка Stage hop): off/strategy/route + параметры + маршрут
        if hasattr(self, "_hop_mode_var"):
            mode = self._hop_mode_var.get()
            cfg.setdefault("hop", {})
            cfg["hop"]["enabled"] = (mode != "off")
            if mode in ("strategy", "route"):
                cfg["hop"]["mode"] = mode
            d = self._hop_diff_var.get()
            cfg["hop"]["difficulty"] = None if d in ("any", "") else d
            try:
                import routehop
                stops, _ = routehop.parse_route(self._hop_route_txt.get("1.0", "end"))
                cfg["hop"]["route"] = stops
            except Exception:
                pass
        # язык БД
        if hasattr(self, "_lang_main_var"):
            cfg["lang_main"] = self._lang_l2c.get(self._lang_main_var.get(), cfg.get("lang_main", "ru-RU"))
            cfg["lang_translate"] = self._lang_l2c.get(self._lang_tr_var.get(), cfg.get("lang_translate", "en-US"))
            cfg["translate_enabled"] = bool(self._lang_tr_on.get())
        save_cfg(cfg)
        self._close_ov()
        if self.hud:
            self.hud.reload()                 # масштаб/цвета таймера — сразу
        # переоткрыть БД, чтобы язык применился сразу
        if getattr(self, "_db", None) is not None and self._db.win.winfo_exists():
            try:
                self._db.win.destroy()
            except Exception:
                pass
            self._db = None
            self.root.after(150, self._open_db)
        # live-смена языка справки (если открыта)
        if self._help_win is not None:
            try:
                if self._help_win.win.winfo_exists():
                    new_lang = cfg.get("lang_main", "ru-RU")
                    self._help_win.set_language(new_lang)
            except Exception:
                pass
        self._put("⚙ настройки сохранены (применятся со СТАРТ)", T.EV["ok"])

    # ---------- управление ----------
    def toggle(self):
        if not self.ready:
            return
        self.stop() if self._alive() else self.start()

    def start(self):
        if self._alive():
            return
        if not self._calib_ready():                        # жёсткий гейт: без калибровки не фармим
            self._put("⚠ Сначала пройди калибровку — нажми «Calibrate now» под START", T.EV["warn"])
            try:
                self.btn.config(state="disabled")
            except Exception:
                pass
            self._refresh_calib_bar()
            return
        try:
            farm.reload_config(); state.reload_config()   # подхватить настройки
            import vision
            vision.reload_config()
        except Exception:
            pass
        self.stop_evt.clear()
        self._loot_n = 0
        self._start_ts = time.time()
        if hasattr(self, "_dash"):
            for _k in ("merge", "stages_ok", "stages_fail", "normal", "stage_boss", "act_boss"):
                if _k in self._dash:                         # guard: ключи дашборда поменялись
                    self._dash[_k].config(text="0")
        self._running_ui(True)
        self._session_on = True
        self._countdown(5)                                   # 5-4-3-2-1 в статус-баре, потом воркер

    def _countdown(self, n):
        """Видимый отсчёт перед стартом сессии (sysbar). STOP во время отсчёта — отмена."""
        if self.stop_evt.is_set() or not getattr(self, "_session_on", False):
            return
        if n > 0:
            if hasattr(self, "sysbar"):
                self.sysbar.config(text=t("cd_start", n=n))
            self._cd_after = self.root.after(1000, lambda: self._countdown(n - 1))
            return
        if hasattr(self, "sysbar"):
            self.sysbar.config(text=t("go_status"))
        self._put("☾ просыпаюсь…", T.EV["ok"])
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def stop(self):
        if not self._alive() and not getattr(self, "_session_on", False):
            return
        self._session_on = False                              # прервать отсчёт, если идёт
        if getattr(self, "_cd_after", None):
            try:
                self.root.after_cancel(self._cd_after)
            except Exception:
                pass
        self.stop_evt.set()            # воркер бросит текущий шаг (клики/паузы рвутся мгновенно)
        if self.hud:
            self.hud.stop()
        self._running_ui(False)        # UI сразу «готов» — без «засыпаю»/«укладываю спать»
        self._put("⏹ стоп", T.STOPC)

    def _run(self):
        try:
            farm2.run(mode="live", log_cb=lambda m: LOG_Q.put(m),
                      stat_cb=lambda s: STAT_Q.put(s), stop_event=self.stop_evt,
                      politeness=self.mode)
        except Exception as e:
            LOG_Q.put(f"ОШИБКА: {e}")
        finally:
            STAT_Q.put(dict(farm.STATS, running=False, phase="стоп"))

    def _running_ui(self, on):
        if on:
            self.btn.config(text=t("stop"), bg=T.STOPC, fg=T.STOP_INK, activebackground=T.STOPC)
            self.dot.itemconfig(self._oval, fill=T.GO)
            self.status.config(text=t("farming"), fg=T.GO)
        else:
            self.btn.config(text=t("start"), bg=T.GO, fg=T.GO_INK, activebackground=T.GO)
            self.dot.itemconfig(self._oval, fill=T.FAINT)
            self.status.config(text=t("ready"), fg=T.SUB)

    # ── карусель активности (текущий шаг бота + следующий по сценарию) ──
    # сценарий count-first цикла бота (см. farm2): осмотр -> оценка -> действие -> следующий проход
    SCENARIO = ["OCR scan inventory", "assess loot value", "synthesis (if enabled)",
                "save & sort stash", "open chests", "collect mail", "next pass"]
    _NEXT_MAP = (("count", "assess loot value"), ("scan", "assess loot value"),
                 ("synth", "save & sort stash"), ("merge", "save & sort stash"),
                 ("cube", "save & sort stash"), ("save", "open chests"),
                 ("sort", "open chests"), ("stash", "open chests"),
                 ("chest", "collect mail"), ("mail", "OCR scan inventory"),
                 ("pass", "OCR scan inventory"), ("warm", "OCR scan inventory"),
                 ("idle", "OCR scan inventory"), ("ready", "OCR scan inventory"))

    def _next_step(self, cur):
        c = (cur or "").lower()
        for k, v in self._NEXT_MAP:
            if k in c:
                return v
        return "next pass"

    def _activity_tick(self):
        """Каждые ~1.6с обновляет карусель: что сейчас + что дальше. Работает — реальный статус;
        простаивает — крутит превью сценария (что бот будет делать)."""
        try:
            if self._alive():                                  # фарм идёт — act_now пишет ядро
                self.act_now.config(fg=T.MOON)
                self.act_next.config(text="→ " + self._next_step(self.act_now.cget("text")))
            else:                                              # простой — карусель-превью сценария
                steps = self.SCENARIO
                i = self._act_i % len(steps)
                self.act_now.config(text=steps[i], fg=T.MOONDIM)
                self.act_next.config(text="→ " + steps[(i + 1) % len(steps)])
                self._act_i += 1
        except Exception:
            pass
        self.root.after(1600, self._activity_tick)

    def _drain(self):
        while True:
            try:
                item = LOG_Q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and item and item[0] == "__status__":
                self.status.config(text=item[1], fg=T.SUB)
                if hasattr(self, "sysbar"):
                    self.sysbar.config(text=item[1])
                continue
            if isinstance(item, tuple) and item and item[0] == "__ready__":
                self._set_ready(item[1]); continue
            if isinstance(item, tuple) and item and item[0] == "__recn__":
                if hasattr(self, "_rec_lbl") and self._rec_lbl.winfo_exists():
                    self._rec_lbl.config(text=f"● запись… шагов: {item[1]}", fg=T.STOPC)
                continue
            if isinstance(item, tuple) and item and item[0] == "__recdone__":
                self._on_record_done(item[1]); continue
            raw = item if isinstance(item, str) else str(item)
            pr = _pretty(raw)
            if pr:
                self._put(pr[0], pr[1], loot=_is_loot(raw))
        last = None
        while True:
            try:
                last = STAT_Q.get_nowait()
            except queue.Empty:
                break
        if last is not None:
            self._apply_stat(last)
        # МОДАЛКА от воркера: показать окно-просьбу, дождаться «Готово», разбудить воркер
        try:
            mtext = MODAL_Q.get_nowait()
        except queue.Empty:
            mtext = None
        if mtext is not None:
            try:
                messagebox.showinfo("GoodNightBot — настройка", mtext, parent=self.root)
            except Exception:
                pass
            try:
                farm.modal_done()
            except Exception:
                pass
        # (old cycle / time / loot tiles removed — now using synthesis/valuable/materials tiles)
        self.root.after(120, self._drain)

    def _calib_ready(self):
        """Все калибровки готовы для ЭТОГО окна? START разрешён только тогда — фарм без калибровки
        запрещён (требование: не давать пользоваться ботом, пока юзер не прошёл калибровку).
        При ошибке реестра не блокируем (fail-open, чтобы баг калибровки не запер бота навсегда)."""
        try:
            import calibration
            s = calibration.summary()
            return not (s["missing"] or s["stale"])
        except Exception:
            return True

    def _set_ready(self, win_found):
        self.ready = True
        self._running_ui(False)
        cal_ok = self._calib_ready()
        self.btn.config(state=("normal" if cal_ok else "disabled"))
        self._put("☾ готов" + ("" if win_found else " (открой игру)"),
                  T.EV["ok"] if win_found else T.EV["warn"])
        if not cal_ok:
            self._put("⚠ сначала калибровка — нажми «Calibrate now» под START (фарм заблокирован)", T.EV["warn"])
            self._refresh_calib_bar()
            return
        self._put("жми СТАРТ — тут пойдут события:", T.FAINT)
        self._put("дроп · синтез · тайник · почта · сундуки", T.FAINT)
        # авто-старт (на всю ночь): если включено в конфиге и игра найдена — стартуем сами
        try:
            if win_found and not getattr(self, "_autostarted", False):
                _c = load_cfg()
                if _c.get("autostart_on_ready"):
                    self._autostarted = True
                    self._set_mode(_c.get("autostart_mode", "auto"))   # auto = напролом
                    self.root.after(900, self.start)
        except Exception:
            pass

    def _update_pbar(self, s):
        """Тонкий прогресс-бар «до следующего действия»: заполняется по мере отсчёта."""
        if not hasattr(self, "pbar") or not self.pbar.winfo_exists():
            return
        w = self.pbar.winfo_width()
        if s.get("phase") == "ожидание" and s.get("next_in"):
            n = s.get("next_in")
            self._wait_max = max(self._wait_max, n)
            frac = 1 - (n / self._wait_max) if self._wait_max else 0
        else:
            self._wait_max = 0
            frac = 0
        try:
            self.pbar.coords(self._pbar_fill, 0, 0, int(w * frac), 4)
        except Exception:
            pass

    @staticmethod
    def _fmt_elapsed(sec):
        h, r = divmod(int(sec), 3600)
        m, s = divmod(r, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def _apply_stat(self, s):
        if hasattr(self, "_dash"):
            self._dash["merge"].config(text=str(s.get("merges", 0)))
            if "stages_ok" in self._dash:
                self._dash["stages_ok"].config(text=str(s.get("stages_ok", 0)))
            if "stages_fail" in self._dash:
                self._dash["stages_fail"].config(text=str(s.get("stages_fail", 0)))
            # сундуки по типу
            for _k, _sk in (("normal", "box_normal"), ("stage_boss", "box_stage"), ("act_boss", "box_act")):
                if _k in self._dash:
                    self._dash[_k].config(text=str(s.get(_sk, 0)))
        self._update_pbar(s)
        if s.get("phase") == "ожидание" and s.get("next_in"):
            act = i18n.ph(s.get("next_action", ""))
            ph = t("wait_act", act=act, n=s.get("next_in")) if act else t("wait", n=s.get("next_in"))
        else:
            ph = i18n.ph(s.get("phase", "—"))
        self.phase.config(text=ph)
        if hasattr(self, "sysbar"):
            self.sysbar.config(text=ph)            # системный статус-бар под кнопкой БД
        if self.hud:
            s2 = dict(s)                         # HUD: локализуем действие/фазу, но «ожидание»
            if s.get("next_action"):             # оставляем для логики отсчёта HUD
                s2["next_action"] = i18n.ph(s.get("next_action"))
            if s.get("phase") != "ожидание":
                s2["phase"] = i18n.ph(s.get("phase", ""))
            self.hud.update_stat(s2)
        if self.ready:
            self._running_ui(self._alive() and s.get("running", True) and not self.stop_evt.is_set())

    def _set_logtab(self, key):
        self.cur_logtab = key
        _all_frames = [self.log, self.log_loot, self.f_sessions]
        for _f in ("f_hero", "f_stash", "f_loot2"):
            if hasattr(self, _f):
                _all_frames.append(getattr(self, _f))
        for w in _all_frames:
            w.pack_forget()
        if key == "all":
            self.log.pack(fill="both", expand=True, padx=2, pady=2)
        elif key == "loot":
            self.log_loot.pack(fill="both", expand=True, padx=2, pady=2)
        elif key == "hero":
            self.f_hero.pack(fill="both", expand=True, padx=2, pady=2)
            self._refresh_data_tabs("hero")
        elif key == "stash":
            self.f_stash.pack(fill="both", expand=True, padx=2, pady=2)
            self._refresh_data_tabs("stash")
        elif key == "loot2":
            self.f_loot2.pack(fill="both", expand=True, padx=2, pady=2)
            self._refresh_data_tabs("loot2")
        else:
            self.f_sessions.pack(fill="both", expand=True, padx=2, pady=2)
            self._reload_sessions()
        for k, b in self.logtab_btns.items():
            on = k == key
            b.config(bg=(T.PANEL2 if on else T.PANEL), fg=(T.MOON if on else T.SUB))

    def _reload_sessions(self):
        """Заполнить дропдаун дат + показать выбранную/последнюю сессию."""
        ds = sessionlog.dates()
        menu = self._sess_om["menu"]
        menu.delete(0, "end")
        if not ds:
            self._sess_date.set("—")
            self._show_session(None)
            return
        for d in ds:
            menu.add_command(label=d, command=lambda dd=d: (self._sess_date.set(dd),
                                                            self._show_session(dd)))
        cur = self._sess_date.get()
        if cur not in ds:
            cur = ds[0]
            self._sess_date.set(cur)
        self._show_session(cur)

    def _show_session(self, day):
        """Показать журнал за дату: сводка + строки (лут с «Имя» — кликабельно в БД)."""
        w = self.log_sessions
        w.config(state="normal")
        w.delete("1.0", "end")
        if not day:
            w.insert("end", "пока пусто — сессии появятся после фарма")
            w.config(state="disabled")
            return
        rows = sessionlog.read(day)
        n_loot = sum(1 for r in rows if r.get("kind") == "loot")
        n_merge = sum(1 for r in rows if r.get("kind") == "merge")
        w.insert("end", f"{day}  ·  лут {n_loot}  ·  синтез {n_merge}\n\n")
        for r in rows:
            start = w.index("end-1c")
            w.insert("end", f"{r.get('t','')}  {r.get('text','')}\n")
            m = re.search(r"«([^»]+)»", r.get("text", ""))
            if m:
                lk = f"sl{w.index('end')}"
                w.tag_add(lk, start, "end-1c")
                w.tag_configure(lk, underline=True)
                w.tag_bind(lk, "<Button-1>", lambda e, nm=m.group(1): self._open_db_item(nm))
                w.tag_bind(lk, "<Enter>", lambda e: w.config(cursor="hand2"))
                w.tag_bind(lk, "<Leave>", lambda e: w.config(cursor=""))
        w.config(state="disabled")

    # ─────────────────────────────── HERO / STASH / LOOT2 tabs ──────────────────────────────────

    def _grade_color(self, grade):
        """Return hex color for a canonical Russian grade string (or fallback SUB)."""
        if not grade:
            return T.SUB
        g = (grade or "").lower().strip()
        return T.GRADE.get(g) or T.GRADE.get(T.GRADE_EN.get(g, ""), T.SUB)

    def _scrollable_frame(self, parent):
        """Create a Canvas+Scrollbar inside parent, return (canvas, inner_frame)."""
        wrap = tk.Frame(parent, bg=T.NIGHT)
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, bg=T.NIGHT, highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=T.NIGHT)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        def _on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        def _on_inner(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner)
        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return canvas, inner

    def _build_hero_tab(self, parent):
        """Build HERO tab frame with sub-tabs: Heroes list + Inventory list."""
        # Sub-tab buttons row
        sub_row = tk.Frame(parent, bg=T.PANEL)
        sub_row.pack(fill="x")
        self._hero_sub = tk.StringVar(value="inv")
        self._hero_sub_btns = {}
        for key, lk in (("heroes", "hero_tab_heroes"), ("inv", "hero_tab_inv")):
            b = tk.Label(sub_row, text=t(lk), bg=T.PANEL2 if key == "inv" else T.PANEL,
                         fg=T.MOON if key == "inv" else T.SUB,
                         padx=10, pady=3, cursor="hand2", font=self._font(9, True))
            b.pack(side="left", padx=(0, 2))
            b.bind("<Button-1>", lambda e, k=key: self._hero_show_sub(k))
            self._hero_sub_btns[key] = b

        # Content area
        self._hero_content = tk.Frame(parent, bg=T.NIGHT)
        self._hero_content.pack(fill="both", expand=True)
        self._hero_canvas = None
        self._hero_inner = None

    def _hero_show_sub(self, key):
        self._hero_sub.set(key)
        for k, b in self._hero_sub_btns.items():
            on = k == key
            b.config(bg=T.PANEL2 if on else T.PANEL, fg=T.MOON if on else T.SUB)
        self._populate_hero_content(key)

    def _populate_hero_content(self, key):
        """Repopulate hero content frame for 'heroes' or 'inv' sub-tab."""
        for w in self._hero_content.winfo_children():
            w.destroy()
        self._hero_canvas, inner = self._scrollable_frame(self._hero_content)
        try:
            import scan_model
            if key == "heroes":
                items = scan_model.get_heroes()
                if not items:
                    tk.Label(inner, text=t("hero_empty"), bg=T.NIGHT, fg=T.FAINT,
                             font=self._font(9)).pack(anchor="w", padx=8, pady=4)
                else:
                    for h in items:
                        nm = h.get("name") or "?"
                        lvl = h.get("level", "")
                        cls = h.get("class_name", "")
                        row = tk.Frame(inner, bg=T.NIGHT)
                        row.pack(fill="x", padx=4, pady=1)
                        tk.Label(row, text=nm, bg=T.NIGHT, fg=T.INK,
                                 font=self._font(9, True)).pack(side="left")
                        if cls:
                            tk.Label(row, text=f" · {cls}", bg=T.NIGHT, fg=T.SUB,
                                     font=self._font(8)).pack(side="left")
                        if lvl:
                            tk.Label(row, text=f" · lvl {lvl}", bg=T.NIGHT, fg=T.FAINT,
                                     font=self._font(8)).pack(side="left")
            else:  # inv
                items = scan_model.get_inventory()
                if not items:
                    tk.Label(inner, text=t("hero_empty"), bg=T.NIGHT, fg=T.FAINT,
                             font=self._font(9)).pack(anchor="w", padx=8, pady=4)
                else:
                    for slot in items:
                        if not slot.get("filled"):
                            continue
                        nm = slot.get("name") or "?"
                        grade = slot.get("grade") or ""
                        lvl = slot.get("level", "")
                        gc = self._grade_color(grade)
                        row = tk.Frame(inner, bg=T.NIGHT)
                        row.pack(fill="x", padx=4, pady=1)
                        tk.Label(row, text=nm, bg=T.NIGHT, fg=T.INK,
                                 font=self._font(9)).pack(side="left")
                        if grade:
                            tk.Label(row, text=f" · {grade}", bg=T.NIGHT, fg=gc,
                                     font=self._font(8)).pack(side="left")
                        if lvl:
                            tk.Label(row, text=f" · lvl {lvl}", bg=T.NIGHT, fg=T.FAINT,
                                     font=self._font(8)).pack(side="left")
        except Exception:
            tk.Label(inner, text=t("hero_empty"), bg=T.NIGHT, fg=T.FAINT,
                     font=self._font(9)).pack(anchor="w", padx=8, pady=4)

    def _build_stash_tab(self, parent):
        """Build STASH tab: sub-tab per stash tab number, grade-sorted item list."""
        self._stash_sub_row = tk.Frame(parent, bg=T.PANEL)
        self._stash_sub_row.pack(fill="x")
        self._stash_content = tk.Frame(parent, bg=T.NIGHT)
        self._stash_content.pack(fill="both", expand=True)
        self._stash_cur_tab = None
        self._stash_data = {}

    def _populate_stash_tab(self):
        """Repopulate stash sub-tabs from scan_model.get_stash()."""
        try:
            import scan_model
            self._stash_data = scan_model.get_stash()
        except Exception:
            self._stash_data = {}

        # Rebuild sub-tab buttons
        for w in self._stash_sub_row.winfo_children():
            w.destroy()
        self._stash_sub_btns = {}

        tab_keys = sorted(self._stash_data.keys()) if self._stash_data else []
        if not tab_keys:
            tk.Label(self._stash_sub_row, text=t("stash_empty"), bg=T.PANEL, fg=T.FAINT,
                     font=self._font(9)).pack(side="left", padx=8, pady=3)
            for w in self._stash_content.winfo_children():
                w.destroy()
            tk.Label(self._stash_content, text=t("stash_empty"), bg=T.NIGHT, fg=T.FAINT,
                     font=self._font(9)).pack(anchor="w", padx=8, pady=4)
            self._stash_cur_tab = None
            return

        first = tab_keys[0]
        if self._stash_cur_tab not in tab_keys:
            self._stash_cur_tab = first

        for tk_no in tab_keys:
            b = tk.Label(self._stash_sub_row, text=str(tk_no),
                         bg=T.PANEL2 if tk_no == self._stash_cur_tab else T.PANEL,
                         fg=T.MOON if tk_no == self._stash_cur_tab else T.SUB,
                         padx=10, pady=3, cursor="hand2", font=self._font(9, True))
            b.pack(side="left", padx=(0, 2))
            b.bind("<Button-1>", lambda e, n=tk_no: self._stash_show_tab(n))
            self._stash_sub_btns[tk_no] = b

        self._stash_render_content(self._stash_cur_tab)

    def _stash_show_tab(self, tab_no):
        self._stash_cur_tab = tab_no
        for n, b in getattr(self, "_stash_sub_btns", {}).items():
            on = n == tab_no
            b.config(bg=T.PANEL2 if on else T.PANEL, fg=T.MOON if on else T.SUB)
        self._stash_render_content(tab_no)

    def _stash_render_content(self, tab_no):
        for w in self._stash_content.winfo_children():
            w.destroy()
        _, inner = self._scrollable_frame(self._stash_content)
        slots = self._stash_data.get(tab_no, [])
        filled = [s for s in slots if s.get("filled")]
        if not filled:
            tk.Label(inner, text=t("stash_empty"), bg=T.NIGHT, fg=T.FAINT,
                     font=self._font(9)).pack(anchor="w", padx=8, pady=4)
            return
        for slot in filled:
            nm = slot.get("name") or "?"
            grade = slot.get("grade") or ""
            lvl = slot.get("level", "")
            gc = self._grade_color(grade)
            row = tk.Frame(inner, bg=T.NIGHT)
            row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=nm, bg=T.NIGHT, fg=T.INK,
                     font=self._font(9)).pack(side="left")
            if grade:
                tk.Label(row, text=f" · {grade}", bg=T.NIGHT, fg=gc,
                         font=self._font(8)).pack(side="left")
            if lvl:
                tk.Label(row, text=f" · lvl {lvl}", bg=T.NIGHT, fg=T.FAINT,
                         font=self._font(8)).pack(side="left")

    def _build_loot2_tab(self, parent):
        """Build LOOT2 drop-table tab with accordion groups per grade."""
        self._loot2_header = tk.Label(parent, text="", bg=T.NIGHT, fg=T.MOON,
                                      font=self._font(9, True), anchor="w", padx=6, pady=4)
        self._loot2_header.pack(fill="x")
        self._loot2_content = tk.Frame(parent, bg=T.NIGHT)
        self._loot2_content.pack(fill="both", expand=True)

    def _populate_loot2_tab(self):
        """Repopulate LOOT2 from loot_data.loot_for_stage(current_stage)."""
        try:
            import scan_model, loot_data, i18n as _i18n
            meta = scan_model.get_meta()
            stage = (meta or {}).get("stage") or ""
            locale = _i18n._lang()
            items = loot_data.loot_for_stage(stage, locale=locale) if stage else []
        except Exception:
            items = []
            stage = ""

        stage_txt = stage if stage else "—"
        self._loot2_header.config(text=f"{t('loot2_stage')}: {stage_txt}")

        for w in self._loot2_content.winfo_children():
            w.destroy()
        self._photo_refs = getattr(self, "_photo_refs", [])
        # Keep only fresh refs per repopulate; clear old ones
        self._photo_refs.clear()

        if not items:
            tk.Label(self._loot2_content, text=t("loot2_empty"), bg=T.NIGHT, fg=T.FAINT,
                     font=self._font(9)).pack(anchor="w", padx=8, pady=4)
            return

        _, inner = self._scrollable_frame(self._loot2_content)

        # Group by grade (keep grade order high→low as returned by loot_for_stage)
        from collections import OrderedDict
        groups = OrderedDict()
        for it in items:
            g = (it.get("grade") or "").upper()
            groups.setdefault(g, []).append(it)

        _GRADE_EN_COLORS = {
            "COMMON": T.GRADE.get("обычный", T.SUB),
            "UNCOMMON": T.GRADE.get("необычный", T.SUB),
            "RARE": T.GRADE.get("редкий", T.SUB),
            "LEGENDARY": T.GRADE.get("легендарный", T.SUB),
            "IMMORTAL": T.GRADE.get("бессмертный", T.SUB),
            "ARCANA": T.GRADE.get("аркана", T.SUB),
            "BEYOND": T.GRADE.get("запредельный", T.SUB),
            "CELESTIAL": T.GRADE.get("celestial", T.SUB),
            "DIVINE": T.GRADE.get("божественный", T.SUB),
            "COSMIC": T.GRADE.get("космический", T.SUB),
        }

        for grade_key, gitems in groups.items():
            gc = _GRADE_EN_COLORS.get(grade_key, T.SUB)
            hdr_text = grade_key.capitalize() if grade_key else "?"
            # Accordion header
            acc_wrap = tk.Frame(inner, bg=T.PANEL)
            acc_wrap.pack(fill="x", pady=2, padx=2)
            _state = {"open": True}
            body_frame = tk.Frame(acc_wrap, bg=T.NIGHT)

            def _make_toggle(bw, bf, st):
                def _toggle(e=None):
                    st["open"] = not st["open"]
                    bw.config(text=("▾ " if st["open"] else "▸ ") + bw.config("text")[-1][2:])
                    if st["open"]:
                        bf.pack(fill="x")
                    else:
                        bf.pack_forget()
                return _toggle

            head = tk.Label(acc_wrap,
                            text=f"▾ {hdr_text}  ({len(gitems)})",
                            bg=T.PANEL, fg=gc, font=self._font(9, True),
                            cursor="hand2", anchor="w", padx=8, pady=4)
            head.pack(fill="x")
            body_frame.pack(fill="x")

            toggler = _make_toggle(head, body_frame, _state)
            head.bind("<Button-1>", toggler)

            for it in gitems:
                nm = it.get("name") or "?"
                pct = it.get("pct")
                src = it.get("source") or ""
                icon_path = it.get("icon") or ""
                item_id = it.get("id")

                row = tk.Frame(body_frame, bg=T.NIGHT)
                row.pack(fill="x", padx=4, pady=1)

                # Sprite (guard missing/PIL absent)
                sprite_path = ""
                if item_id:
                    candidate = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "templates", "sprites", f"Item_{item_id}.png")
                    if os.path.exists(candidate):
                        sprite_path = candidate
                if not sprite_path and icon_path and os.path.exists(icon_path):
                    sprite_path = icon_path

                if sprite_path:
                    try:
                        try:
                            from PIL import Image, ImageTk as _ITk
                            img = Image.open(sprite_path).convert("RGBA")
                            img = img.resize((24, 24), Image.LANCZOS)
                            ph = _ITk.PhotoImage(img)
                        except Exception:
                            ph = tk.PhotoImage(file=sprite_path)
                            ph = ph.subsample(max(1, ph.width() // 24),
                                              max(1, ph.height() // 24))
                        self._photo_refs.append(ph)
                        lbl = tk.Label(row, image=ph, bg=T.NIGHT)
                        lbl.pack(side="left", padx=(0, 4))
                    except Exception:
                        pass

                tk.Label(row, text=nm, bg=T.NIGHT, fg=T.INK,
                         font=self._font(9)).pack(side="left")
                if pct is not None:
                    tk.Label(row, text=f"  {pct:.1f}%", bg=T.NIGHT, fg=T.FAINT,
                             font=self._font(8)).pack(side="left")
                if src:
                    tk.Label(row, text=f"  [{src}]", bg=T.NIGHT, fg=T.FAINT,
                             font=self._font(8)).pack(side="left")

    def _refresh_data_tabs(self, which=None):
        """Re-read models and repopulate the active data tab (or all if which is None)."""
        try:
            if which in (None, "hero"):
                sub = getattr(self, "_hero_sub", None)
                self._populate_hero_content(sub.get() if sub else "inv")
            if which in (None, "stash"):
                self._populate_stash_tab()
            if which in (None, "loot2"):
                self._populate_loot2_tab()
        except Exception:
            pass

    @staticmethod
    def _append(widget, tags, text, color):
        tag = "c" + (color or T.SUB).lstrip("#")
        if tag not in tags:
            widget.tag_configure(tag, foreground=color or T.SUB)
            tags[tag] = True
        widget.config(state="normal")
        widget.insert("end", text.rstrip() + "\n", tag)
        if int(widget.index("end-1c").split(".")[0]) > 160:
            widget.delete("1.0", "40.0")
        widget.see("end")
        widget.config(state="disabled")

    def _put(self, text, color, loot=False):
        ts = time.strftime("%H:%M:%S")
        disp = i18n.localize_log(text)                          # перевод ТОЛЬКО для показа
        self._append_general(f"{ts}  {disp}", color)            # общий — со временем, «Имя» кликабельно
        if loot:                                                # лут-вкладка — только дроп/лут
            self._append_loot(disp, color)
        # журнал сессий по датам (лут/мержи/раскладка/почта)
        low = text.lower()
        if loot:
            sessionlog.record("loot", text)
        elif "мерж" in low:
            sessionlog.record("merge", text)
        elif "тайник" in low or "разложил" in low:
            sessionlog.record("save", text)
        elif "почт" in low:
            sessionlog.record("mail", text)

    def _append_general(self, text, color):
        """Строка в ОБЩИЙ лог. Если есть «Имя» — делаем кликабельной ссылкой на предмет в БД."""
        w = self.log
        tag = "c" + (color or T.SUB).lstrip("#")
        if tag not in self._tags:
            w.tag_configure(tag, foreground=color or T.SUB)
            self._tags[tag] = True
        m = re.search(r"«([^»]+)»", text)
        name = m.group(1) if m else None
        w.config(state="normal")
        start = w.index("end-1c")
        w.insert("end", text.rstrip() + "\n", tag)
        if name:
            lk = f"gl{self._loot_n}"
            self._loot_n += 1
            w.tag_add(lk, start, "end-1c")
            w.tag_configure(lk, underline=True)
            w.tag_bind(lk, "<Button-1>", lambda e, nm=name: self._open_db_item(nm))
            w.tag_bind(lk, "<Enter>", lambda e: w.config(cursor="hand2"))
            w.tag_bind(lk, "<Leave>", lambda e: w.config(cursor=""))
        if int(w.index("end-1c").split(".")[0]) > 160:
            w.delete("1.0", "40.0")
        w.see("end")
        w.config(state="disabled")

    def _append_loot(self, text, color):
        """Лут-строка в отдельную вкладку + КЛИКАБЕЛЬНО: клик по строке с «Имя» открывает
        Базу знаний по этому предмету (связь лог↔БД)."""
        w = self.log_loot
        tag = "c" + (color or T.SUB).lstrip("#")
        if tag not in self._tags_loot:
            w.tag_configure(tag, foreground=color or T.SUB)
            self._tags_loot[tag] = True
        m = re.search(r"«([^»]+)»", text)
        name = m.group(1) if m else None
        w.config(state="normal")
        start = w.index("end-1c")
        w.insert("end", text.rstrip() + "\n", tag)
        if name:
            lk = f"lk{self._loot_n}"
            self._loot_n += 1
            w.tag_add(lk, start, "end-1c")
            w.tag_configure(lk, underline=True)
            w.tag_bind(lk, "<Button-1>", lambda e, nm=name: self._open_db_item(nm))
            w.tag_bind(lk, "<Enter>", lambda e: w.config(cursor="hand2"))
            w.tag_bind(lk, "<Leave>", lambda e: w.config(cursor=""))
        if int(w.index("end-1c").split(".")[0]) > 160:
            w.delete("1.0", "40.0")
        w.see("end")
        w.config(state="disabled")

    def _open_db_item(self, name):
        """Открыть Базу знаний по конкретному предмету (из клика по луту)."""
        try:
            import db_browser
            if getattr(self, "_db", None) is not None and self._db.win.winfo_exists():
                self._db.set_search(name)
                return
            self.root.update_idletasks()
            h = max(self.root.winfo_height(), 480)
            self._db = db_browser.open_browser(self.root, height=h, query=name)
        except Exception as e:
            LOG_Q.put(f"ОШИБКА: БД не открылась: {e}")

    def _quit(self):
        self._save_panel_geom()        # запомнить положение/высоту при закрытии
        self.stop_evt.set()
        self.root.after(250, self.root.destroy)


_LOCK_HANDLE = None   # держим хэндл мьютекса до конца процесса (освободится ОС при выходе)


def _single_instance(name="Local\\GoodNightBot_Panel_Mutex"):
    """True если это ЕДИНСТВЕННАЯ панель. На Windows — именованный мьютекс (канонично):
    если мьютекс уже существует, значит панель запущена (батник+крон могли стартовать разом)
    -> False, выходим. Namespace 'Local\\' — привилегий не требует (одна юзер-сессия).
    NB: socket-bind на Windows НЕ эксклюзивен по умолчанию, поэтому именно мьютекс.
    Хэндл держим в глобале; ОС освобождает его при завершении процесса."""
    global _LOCK_HANDLE
    try:
        import ctypes
        from ctypes import wintypes
        # use_last_error=True -> ctypes сохраняет код ошибки СРАЗУ после вызова (иначе
        # промежуточные вызовы ctypes затирают GetLastError — из-за этого guard не срабатывал).
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        h = k32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        ERROR_ALREADY_EXISTS = 183
        if not h:
            return True              # не смогли создать мьютекс — не блокируем запуск
        if err == ERROR_ALREADY_EXISTS:
            return False             # панель уже запущена
        _LOCK_HANDLE = h
        return True
    except Exception:
        return True   # не Windows / сбой — не блокируем запуск


def _maybe_autoupdate():
    """Тихая проверка обновления при старте (config update.auto=true). Неблокирующе."""
    try:
        if not load_cfg().get("update", {}).get("auto", False):
            return
        import updater
        threading.Thread(target=updater.auto, daemon=True).start()
    except Exception:
        pass


def main():
    os.chdir(HERE)
    if not _single_instance():
        return   # панель уже запущена — не плодим дубль (защита от крон/двойного клика)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    root = tk.Tk()
    Panel(root)
    _maybe_autoupdate()
    root.mainloop()


if __name__ == "__main__":
    main()
